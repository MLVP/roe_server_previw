"""Собирает каталог лута и сцену с машинами в точке спавна.

Пример (точка, найденная игроком в Kill Zone):

    .tools\\python\\python.exe tools\\build_spawn_loot_2022.py ^
        --center 360047 366722 40173 --count 64 ^
        --catalog modes\\europa\\loot-killzone-64.json ^
        --scene modes\\europa\\config\\scene-cycle.json

Координаты: X, Y (плоскость) и Z (высота) в порядке игровых координат.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
VEHICLE_TEMPLATE = 'b3f90e45b2ddf557f0d2ae4cf8308314f0e861903ab0d4b2a202e6bcfe856e3f'


def load_items(source):
    data = json.loads(Path(source).read_text(encoding='utf-8-sig'))
    return [int(entity['item_id']) for entity in data['entities']]


def build_catalog(source, center, count, step, map_id, radius_cm, output):
    items = load_items(source)
    if not items:
        raise SystemExit('source catalog is empty')
    x0, y0, z0 = center
    entities = []
    index = 170000
    uid_base = 0x50400002000000
    column = 0
    row = 0
    for number in range(count):
        item_id = items[number % len(items)]
        if row % 2 == 0:
            position = [x0 + column * step, y0 + row * step, z0]
        else:
            position = [x0 + (column + 1) * step, y0 + row * step, z0]
        entities.append({
            'index': index,
            'entity_uid': uid_base + number,
            'item_id': item_id,
            'quantity': 1,
            'position': position,
        })
        index += 1
        column += 1
        if column >= 8:
            column = 0
            row += 1
    catalog = {
        'map_id': map_id,
        'radius_cm': radius_cm,
        'visible_limit': 128,
        'batch_limit': 16,
        'policy': 'local_spawn_grid',
        'original_positions_verified': False,
        'original_algorithm_verified': False,
        'native_all_definition_inventory_verified': True,
        'native_mixed_layout_verified': False,
        'grenade_hand_throw_effect_verified': False,
        'native_windows_verified': False,
        'native_mixed_catalog_loaded': True,
        'native_all_mixed_pickups_verified': False,
        'native_mixed_pickup_control_definition': 10201,
        'spawn_center': [x0, y0, z0],
        'entities': entities,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return catalog


def build_scene(scene_source, center, vehicles, output, map_id):
    wires = json.loads((ROOT / 'config' / 'wire.json').read_text(encoding='utf-8'))
    prototype = bytearray(bytes.fromhex(wires[VEHICLE_TEMPLATE]['hex']))
    if len(prototype) != 164:
        raise SystemExit('vehicle template is not 164 bytes')
    x0, y0, z0 = center
    replies = []
    for number, (configuration, offset) in enumerate(vehicles):
        body = bytearray(prototype)
        struct.pack_into('>Q', body, 0, 0x50400003000000 + number)
        struct.pack_into('>I', body, 8, configuration)
        struct.pack_into('>3i', body, 20, x0 + offset, y0, z0)
        replies.append(dict(command='0x654b', payload_hex=bytes(body).hex()))
    scene = json.loads(Path(scene_source).read_text(encoding='utf-8-sig'))
    scene = [rule for rule in scene
             if not any(int(response['command'], 0) == 0x654b
                        and 'local_spawn_vehicles' in response.get('origin', '')
                        for response in rule.get('responses', []))]
    scene.append({
        'trigger': '0x1f49',
        'after_selection': True,
        'batch_responses': True,
        'origin': 'local_spawn_vehicles',
        'responses': replies,
    })
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scene, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--center', type=int, nargs=3, required=True,
                        metavar=('X', 'Y', 'Z'), help='spawn point: X, Y (plane), Z (height)')
    parser.add_argument('--count', type=int, default=64)
    parser.add_argument('--step', type=int, default=35)
    parser.add_argument('--radius-cm', type=int, default=2000)
    parser.add_argument('--map-id', type=int, default=16007)
    parser.add_argument('--source-catalog', default=str(ROOT / 'modes' / 'dion' / 'loot-pool61.json'))
    parser.add_argument('--catalog', default=str(ROOT / 'modes' / 'europa' / 'loot-killzone-64.json'))
    parser.add_argument('--scene-source', default=str(ROOT / 'config' / 'scene-cycle.json'))
    parser.add_argument('--scene', default=str(ROOT / 'modes' / 'europa' / 'config' / 'scene-cycle.json'))
    parser.add_argument('--vehicles', default='102:300,109:-300',
                        help='vehicle configurations with X offsets, comma separated')
    args = parser.parse_args()
    vehicles = []
    for row in args.vehicles.split(','):
        if not row.strip():
            continue
        configuration, offset = row.split(':')
        vehicles.append((int(configuration), int(offset)))
    catalog = build_catalog(args.source_catalog, tuple(args.center), args.count, args.step,
                             args.map_id, args.radius_cm, args.catalog)
    scene = build_scene(args.scene_source, tuple(args.center), vehicles, args.scene, args.map_id)
    print(json.dumps({'ok': True, 'center': args.center, 'items': len(catalog['entities']),
                      'vehicles': len(vehicles), 'scene_rules': len(scene),
                      'catalog': args.catalog, 'scene': args.scene}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
