"""Build a 16-bit raw heightmap from recovered world/spawn points.

Input formats accepted:
  {"points": [[grid_x, grid_y, x, y, z], ...]}
  {"points": [[x, y, z], ...]}
  {"points": [{"x": ..., "y": ..., "z": ...}, ...]}

The default output is a full 4096x4096 little-endian uint16 raster.  A coarse
nearest-point grid is upscaled to keep the operation fast without numpy.
"""
from __future__ import annotations

import argparse
from array import array
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_points(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    rows = data.get('points') if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError('points must be an array')
    result = []
    for row in rows:
        if isinstance(row, dict):
            try:
                x, y, z = float(row['x']), float(row['y']), float(row['z'])
            except (KeyError, TypeError, ValueError):
                continue
            cell = [row.get('gx'), row.get('gy')]
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            x, y, z = float(row[2]), float(row[3]), float(row[4])
            cell = [row[0], row[1]]
        elif isinstance(row, (list, tuple)) and len(row) >= 3:
            x, y, z = float(row[0]), float(row[1]), float(row[2])
            cell = None
        else:
            continue
        if not all(math.isfinite(value) for value in (x, y, z)):
            continue
        result.append({'cell': cell, 'x': x, 'y': y, 'z': z})
    if not result:
        raise ValueError('no usable points')
    return (data.get('map_id') if isinstance(data, dict) else None), result


def parse_pair(value, name):
    if not value:
        return None
    parts = value.split(',')
    if len(parts) != 2:
        raise ValueError(f'{name} must be x,y')
    return float(parts[0]), float(parts[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--points', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--size', type=int, default=4096)
    parser.add_argument('--coarse', type=int, default=256,
                        help='nearest-point grid resolution; 0 for sparse point raster')
    parser.add_argument('--fill-radius', type=int, default=2,
                        help='pixel radius used in sparse mode')
    parser.add_argument('--margin', type=float, default=1000.0)
    parser.add_argument('--origin', help='override x,y origin')
    parser.add_argument('--extent', help='override x,y extent')
    parser.add_argument('--z-min', type=float)
    parser.add_argument('--z-max', type=float)
    parser.add_argument('--no-data', type=int, default=0)
    args = parser.parse_args()

    if not 16 <= args.size <= 16384:
        parser.error('size must be 16..16384')
    if args.coarse < 0:
        parser.error('coarse must be >= 0')
    if args.fill_radius < 0:
        parser.error('fill-radius must be >= 0')
    if not 0 <= args.no_data <= 65535:
        parser.error('no-data must fit uint16')

    map_id, points = load_points(args.points)
    min_x = min(point['x'] for point in points)
    max_x = max(point['x'] for point in points)
    min_y = min(point['y'] for point in points)
    max_y = max(point['y'] for point in points)
    origin = parse_pair(args.origin, 'origin')
    extent = parse_pair(args.extent, 'extent')
    if origin is None:
        origin = (min_x - args.margin, min_y - args.margin)
    if extent is None:
        extent = (max_x - origin[0] + args.margin, max_y - origin[1] + args.margin)
    if extent[0] <= 0 or extent[1] <= 0:
        raise ValueError('extent must be positive')
    z_min = min(point['z'] for point in points) if args.z_min is None else args.z_min
    z_max = max(point['z'] for point in points) if args.z_max is None else args.z_max
    if z_max < z_min:
        raise ValueError('z-max must be >= z-min')

    def height_value(z):
        if z_max == z_min:
            return 32768
        value = int(round((z - z_min) / (z_max - z_min) * 65535))
        return max(0, min(65535, value))

    values = array('H', [args.no_data]) * (args.size * args.size)
    size = args.size
    ox, oy = origin
    ex, ey = extent

    if args.coarse <= 0:
        for point in points:
            px = int((point['x'] - ox) / ex * (size - 1) + 0.5)
            py = int((point['y'] - oy) / ey * (size - 1) + 0.5)
            if not (0 <= px < size and 0 <= py < size):
                continue
            value = height_value(point['z'])
            radius = args.fill_radius
            for yy in range(max(0, py - radius), min(size, py + radius + 1)):
                for xx in range(max(0, px - radius), min(size, px + radius + 1)):
                    if (xx - px) ** 2 + (yy - py) ** 2 <= radius * radius:
                        values[yy * size + xx] = value
        mode = 'sparse'
    else:
        coarse = min(size, args.coarse)
        for cy in range(coarse):
            y0 = cy * size // coarse
            y1 = (cy + 1) * size // coarse
            if y1 <= y0:
                continue
            sample_y = oy + (cy + 0.5) * ey / coarse
            for cx in range(coarse):
                x0 = cx * size // coarse
                x1 = (cx + 1) * size // coarse
                if x1 <= x0:
                    continue
                sample_x = ox + (cx + 0.5) * ex / coarse
                nearest = min(points, key=lambda point: (point['x'] - sample_x) ** 2 + (point['y'] - sample_y) ** 2)
                value = height_value(nearest['z'])
                row = array('H', [value]) * (x1 - x0)
                for py in range(y0, y1):
                    start = py * size + x0
                    values[start:start + (x1 - x0)] = row
        mode = 'coarse-nearest'

    out = args.out.expanduser()
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(values.tobytes())
    metadata = {
        'format': 'raw',
        'dtype': 'uint16',
        'endian': 'little',
        'size': [size, size],
        'bytes': out.stat().st_size,
        'mode': mode,
        'coarse': args.coarse,
        'fill_radius': args.fill_radius,
        'map_id': map_id,
        'source': str(Path(args.points).resolve()),
        'source_points': len(points),
        'origin': [ox, oy],
        'extent': [ex, ey],
        'z_range': [z_min, z_max],
        'no_data': args.no_data,
        'row_order': 'min_y_to_max_y',
    }
    out.with_suffix(out.suffix + '.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'out': str(out), **metadata}, ensure_ascii=False))


if __name__ == '__main__':
    main()
