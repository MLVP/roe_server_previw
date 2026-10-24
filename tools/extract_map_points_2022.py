"""Извлечение точек лута (ENTITYPOINTCONFIG.XML) из Common.sfc для карт ROE 2022.

Файл точек лежит в архиве SFC/Common.sfc как запись с LZ4-блоком:
[u32 packed][LZ4-данные][u32 raw_size]. Имён в архиве нет (индекс хранит хэши),
поэтому файлы опознаются по содержимому и проверке рельефа:

    python tools/extract_map_points_2022.py --map europa --out map-data
    python tools/extract_map_points_2022.py --map vera   --out map-data
    python tools/extract_map_points_2022.py --map dion   --out map-data
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import lz4.block as lz4

ROOT = Path(__file__).resolve().parents[1]
SFC = Path(r'F:\SteamLibrary\steamapps\common\Ring of Elysium\SFC\Common.sfc')
PROP = re.compile(r'\s+\[XlsProp\]="[^"]*"')

# Записи Common.sfc, опознанные по точкам и рельефу (см. docs/MAP-POINTS-20261023.md).
MAPS = {
    'dion': dict(map_id=16010, indexes=(1499, 1206, 3163, 3398), world='EU_ICELAND_4096'),
    'europa': dict(map_id=16007, indexes=(134, 879, 375, 615), world='EU_Killzone_4096'),
    'vera': dict(map_id=16021, indexes=(1013, 2787), world='EU_Desert_4096'),
}


def read_index(path: Path):
    data = path.read_bytes()
    if data[:4] != b'SFC\x1a':
        raise ValueError('не SFC архив')
    version, count = struct.unpack_from('<II', data, 4)
    offsets = [struct.unpack_from('<III', data, 12 + i * 12) for i in range(count)]
    return version, offsets, data


def entry_points(data, offsets, index):
    """Распаковка записи и разбор строк с InstanceID= в точки."""
    _, _, off = offsets[index]
    packed = struct.unpack_from('<I', data, off)[0]
    tail = off + 4 + packed
    raw_size = struct.unpack_from('<I', data, tail)[0]
    blob = lz4.decompress(data[off + 4:tail], uncompressed_size=raw_size)
    sha = hashlib.sha1(blob).hexdigest()
    text = blob.decode('utf-8', 'replace')
    points = []
    for number, line in enumerate(text.splitlines(), 1):
        if 'InstanceID=' not in line:
            continue
        try:
            row = ET.fromstring(PROP.sub('', line.strip())).attrib
        except ET.ParseError:
            continue
        def num(key):
            try:
                return int(float(row.get(key, 0)))
            except ValueError:
                return 0
        points.append(dict(instance_id=num('InstanceID'), type_id=num('TypeId'),
                           position_cm=[num('PosX'), num('PosY'), num('PosZ')],
                           direction=round(float(row.get('Direction', 0) or 0), 3),
                           archetype=row.get('C_BaseInstanceName', ''), source_line=number))
    return points, dict(index=index, offset=off, packed=packed, raw_size=raw_size, sha1=sha)


def ranges(points):
    xs = [p['position_cm'][0] for p in points]
    ys = [p['position_cm'][1] for p in points]
    zs = [p['position_cm'][2] for p in points]
    return dict(x=(min(xs), max(xs)), y=(min(ys), max(ys)), z=(min(zs), max(zs)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', choices=sorted(MAPS), required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'map-data')
    parser.add_argument('--with-variants', action='store_true',
                        help='также распарсить остальные варианты файла и показать пересечения')
    args = parser.parse_args(argv)
    spec = MAPS[args.map]
    version, offsets, data = read_index(SFC)
    main_points, main_src = entry_points(data, offsets, spec['indexes'][0])
    variants = []
    for index in spec['indexes']:
        points, src = entry_points(data, offsets, index)
        variants.append(dict(index=index, offset=src['offset'], sha1=src['sha1'],
                             raw_size=src['raw_size'], n=len(points),
                             ranges=ranges(points)))
    document = dict(
        map_id=spec['map_id'], map=args.map, world=spec['world'], units='cm',
        source=dict(archive='SFC/Common.sfc', entry=main_src, variants=variants,
                    file='DATA/SERVER/<world>/<level>/ENTITYPOINTCONFIG.XML (путь по данным Dione)'),
        extracted=__import__('datetime').datetime.now().strftime('%Y-%m-%d'),
        note='Имена в архиве не хранятся; файл опознан по точкам и рельефу карты.',
        ranges=ranges(main_points),
        type_counts=dict(sorted(Counter(p['type_id'] for p in main_points).items())),
        archetype_counts=dict(Counter(p['archetype'] for p in main_points).most_common(12)),
        count=len(main_points),
        points=main_points,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f'{args.map}-entitypoints.json'
    target.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('записано:', target, len(main_points), 'точек')
    print('  диапазоны:', document['ranges'])
    print('  варианты файла:', json.dumps(variants, ensure_ascii=False))
    if args.with_variants:
        seen = {tuple(p['position_cm']) for p in main_points}
        for other in spec['indexes'][1:]:
            points, _ = entry_points(data, offsets, other)
            keys = {tuple(p['position_cm']) for p in points}
            print(f'  idx {other}: n={len(points)}, пересечение с главным {len(seen & keys)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
