"""Спаун машин по оригинальным точкам карты (map-data/*-vehiclepoints.json).

164-байтовый ground vehicle spawn (0x654B) собирается из проверенного
Jeep102-прототипа сцены: меняются UID, configuration (102 jeep / 109
snowmotor — случайно на точку), позиция из точки и quaternion из Direction
(форма проверена original_jeeps: Direction 270 → (0,0,-√.5,√.5)).
Точки выбираются случайно, сид задаётся явно для воспроизводимости.
"""
import copy
import json
import math
import random
import struct
from pathlib import Path

CONFIGURATIONS = (102, 109)
UID_BASE = 0x5040000200001


def _response_body(response):
    try:
        if 'payload_file' in response:
            return Path(response['payload_file']).read_bytes()
        return bytes.fromhex(response.get('payload_hex') or '')
    except (OSError, ValueError):
        return None  # например @wire-прототипы, недоступные из JSON сцены


def _load_prototype(scene):
    for rule in scene:
        for response in rule.get('responses', []):
            if int(response.get('command', '0x0'), 0) != 0x654b:
                continue
            body = _response_body(response)
            if body is not None and len(body) == 164 and struct.unpack_from('>I', body, 8)[0] == 102:
                return body
    return None


def _yaw_quaternion(direction_degrees):
    """Проверенная интерпретация Direction (original_jeeps: 270 → (0,0,-√.5,√.5))."""
    half = math.radians(float(direction_degrees) - 360.0) / 2.0
    return (0.0, 0.0, math.sin(half), math.cos(half))


def _known_uids(scene):
    known = set()
    for rule in scene:
        for response in rule.get('responses', []):
            if int(response.get('command', '0x0'), 0) != 0x654b:
                continue
            body = _response_body(response)
            if body is not None and len(body) >= 8:
                known.add(struct.unpack_from('>Q', body)[0])
    return known


def spawn_vehicles_from_points(scene, points_path, count, seed=None,
                               configurations=CONFIGURATIONS):
    """Добавляет к сцене count машин в случайные оригинальные точки карты."""
    if type(count) is not int or not 0 < count <= 500:
        raise ValueError('vehicle count: 1..500')
    if not configurations or any(type(c) is not int or not 0 < c < 1000 for c in configurations):
        raise ValueError('configurations: непустой список id 1..999')
    doc = json.loads(Path(points_path).read_text(encoding='utf-8-sig'))
    points = doc.get('points') or []
    if not points:
        raise ValueError('в файле точек нет машин')
    count = min(count, len(points))
    result = copy.deepcopy(scene)
    prototype = _load_prototype(result)
    if prototype is None:
        raise ValueError('нет проверенной Jeep102/164 fixture в сцене')
    rng = random.Random(seed)
    known = _known_uids(result)
    replies = []
    for offset, row in enumerate(rng.sample(points, count)):
        uid = UID_BASE + offset
        while uid in known:
            uid += count
        known.add(uid)
        body = bytearray(prototype)
        struct.pack_into('>Q', body, 0, uid)
        struct.pack_into('>I', body, 8, rng.choice(configurations))
        struct.pack_into('>3i', body, 20, *(int(v) for v in row['position_cm']))
        struct.pack_into('>4f', body, 33, *_yaw_quaternion(row.get('direction', 0)))
        replies.append(dict(command='0x654b', payload_hex=body.hex()))
    result.append(dict(trigger='0x1f49', after_selection=True,
                       batch_responses=True, responses=replies))
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Ставит машины в оригинальные точки карты')
    parser.add_argument('--scene', type=Path, required=True, help='modes/<map>/config/scene-cycle.json')
    parser.add_argument('--points', type=Path, required=True, help='map-data/<map>-vehiclepoints.json')
    parser.add_argument('--count', type=int, required=True, help='1..500')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    scene = json.loads(args.scene.read_text(encoding='utf-8-sig'))
    result = spawn_vehicles_from_points(scene, args.points, args.count, seed=args.seed)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('машин добавлено:', len(result[-1]['responses']))


if __name__ == '__main__':
    main()
