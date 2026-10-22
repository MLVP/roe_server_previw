"""Собирает таблицу item_id -> название в docs/.

Источники:
  * analysis/game_tables/items_master.csv   - мастер-таблица предметов (11539 строк)
  * analysis/game_tables/items_europa.csv   - европейский набор предметов
  * analysis/game_tables/loot_item_catalog.csv - лут-поверхности по картам
  * конфиги репозитория: modes/*/loot-pool61.json, config/loot-pool61.json,
    config/loot-test-quarter.json, стартовый лут из config/weapon-*.json

Запуск:
    .tools\\python\\python.exe tools\\build_item_table_2022.py
    .tools\\python\\python.exe tools\\build_item_table_2022.py --tables D:\\game_tables
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLES = Path(r'F:\ROERevive\analysis\game_tables')
DOCS = ROOT / 'docs'
MAP_ID = 16010


def read_csv(path):
    if not path.is_file():
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def usable(value):
    return isinstance(value, str) and value.strip() and value.strip() != '????'


def collect_repo_ids():
    """item_id, которые реально использует сервер."""
    used = {}

    def note(item_id, source):
        used.setdefault(int(item_id), set()).add(source)

    catalogs = [ROOT / 'config' / 'loot-pool61.json', ROOT / 'config' / 'loot-test-quarter.json']
    catalogs.extend(sorted(ROOT.glob('modes/*/loot-pool61.json')))
    for path in catalogs:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        for entity in data.get('entities', []):
            note(entity['item_id'], path.relative_to(ROOT).as_posix())

    wires = {}
    wire_path = ROOT / 'config' / 'wire.json'
    if wire_path.is_file():
        wires = {token: bytes.fromhex(record['hex'])
                 for token, record in json.loads(wire_path.read_text(encoding='utf-8')).items()}

    for path in sorted(ROOT.glob('config/weapon-*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        entities = []
        loot = data.get('loot')
        if isinstance(loot, dict) and 'entity_file' in loot:
            entities.append(loot['entity_file'])
        for row in data.get('additional_loot', []) or []:
            entities.append(row.get('entity_file'))
        for reference in entities:
            token = str(reference).split('/')[-1]
            body = wires.get(token)
            if body and len(body) >= 67:
                note(struct.unpack_from('>I', body, 63)[0], path.relative_to(ROOT).as_posix())
        for item_id in data.get('starting_equipment', []) or []:
            note(item_id, path.relative_to(ROOT).as_posix())
    return used


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tables', type=Path, default=DEFAULT_TABLES)
    parser.add_argument('--out-csv', type=Path, default=DOCS / 'items-2022.csv')
    parser.add_argument('--out-md', type=Path, default=DOCS / 'ITEMS-2022.md')
    args = parser.parse_args()

    master = {row['item_id']: row for row in read_csv(args.tables / 'items_master.csv')}
    europa = {row['item_id']: row for row in read_csv(args.tables / 'items_europa.csv')}
    surface = {row['item_id']: row for row in read_csv(args.tables / 'loot_item_catalog.csv')}
    used = collect_repo_ids()

    ids = {int(key) for key in master} | {int(key) for key in europa}
    ids |= {int(key) for key in surface} | set(used)
    rows = []
    for item_id in sorted(ids):
        key = str(item_id)
        m = master.get(key, {})
        e = europa.get(key, {})
        s = surface.get(key, {})
        name = next((value for value in (m.get('display_name'), e.get('display_name'),
                                         s.get('item_name'), m.get('simplified_name'))
                     if usable(value)), None)
        if not name:
            name = m.get('id_name') or e.get('id_name') or key
        maps = s.get('maps', '')
        rows.append({
            'item_id': item_id,
            'name': name,
            'short_name': m.get('simplified_name') or e.get('simplified_name') or '',
            'id_name': m.get('id_name') or e.get('id_name') or '',
            'category': m.get('category') or e.get('category') or '',
            'subcategory': m.get('subcategory') or e.get('subcategory') or '',
            'quality': m.get('quality') or e.get('quality') or '',
            'equip_type': m.get('equip_type') or e.get('equip_type') or '',
            'in_server_loot': 'yes' if item_id in used else '',
            'server_sources': ';'.join(sorted(used.get(item_id, ()))),
            'in_map_loot_surface': 'yes' if str(MAP_ID) in maps.split(';') else '',
            'maps': maps,
        })

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        '# Items 2022 - item_id -> name',
        '',
        f'Generated by `tools/build_item_table_2022.py` from `{args.tables}` and the repository',
        'loot catalogs. CSV version: `docs/items-2022.csv`.',
        '',
        f'- rows: {len(rows)}',
        f'- item ids used by the server loot: {len(used)}',
        f'- item ids in the map {MAP_ID} loot surface: {sum(1 for row in rows if row["in_map_loot_surface"])}',
        '',
        '## Item ids used by the server loot',
        '',
        '| item_id | name | short | id_name | quality | source |',
        '|---|---|---|---|---|---|',
    ]
    for row in rows:
        if not row['in_server_loot']:
            continue
        lines.append(f'| {row["item_id"]} | {row["name"]} | {row["short_name"]} | {row["id_name"]} | '
                     f'{row["quality"]} | {row["server_sources"]} |')
    lines += [
        '',
        '## Loot surface of map 16010',
        '',
        '| item_id | name | short | id_name | in server loot |',
        '|---|---|---|---|---|',
    ]
    for row in rows:
        if not row['in_map_loot_surface']:
            continue
        lines.append(f'| {row["item_id"]} | {row["name"]} | {row["short_name"]} | {row["id_name"]} | '
                     f'{row["in_server_loot"] or "-"} |')
    args.out_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps({'ok': True, 'rows': len(rows), 'server_loot_ids': len(used),
                      'csv': str(args.out_csv), 'md': str(args.out_md)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
