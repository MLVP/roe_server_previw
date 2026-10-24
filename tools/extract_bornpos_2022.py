"""Извлекает таблицы высадки (BlockBornPosTable) и точки техники в map-data/."""
import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import lz4.block as lz4
from sfc_reader_2022 import read_index

ROOT = Path(__file__).resolve().parents[1]
SFC = Path(r'F:\SteamLibrary\steamapps\common\Ring of Elysium\SFC\Common.sfc')
ITEM = re.compile(r'<m_Items\s+([^/>]*)/>')
ATTR = re.compile(r'(\w+)="([^"]*)"')

BORN = {  # карта -> запись Common.sfc (определено: map_id / имя объекта + мир)
    'dion': (4045, 16010, 'Data.Table.BlockBornPosTable map_id=16010'),
    'europa': (3306, 16007, 'Data.Table.BlockBornPosTable map_id=16009 (тот же мир EU_KillZone_4096, уровень 001)'),
    'vera': (3203, 16021, 'Data.Server.EU_Desert_4096.BlockBornPosTable (без map_id, мир Desert_001)'),
}


def entry(data, offsets, idx):
    off = offsets[idx]
    packed = struct.unpack_from('<I', data, off)[0]
    tail = off + 4 + packed
    size = struct.unpack_from('<I', data, tail)[0]
    return lz4.decompress(data[off + 4:tail], uncompressed_size=size), off, size


def read_born():
    version, offsets, data = read_index(SFC)
    out = {}
    for key, (idx, map_id, note) in BORN.items():
        blob, off, size = entry(data, offsets, idx)
        text = blob.decode('utf-8', 'replace')
        cells = []
        for attrs in ITEM.findall(text):
            d = dict(ATTR.findall(attrs))
            if 'BlockX' not in d:
                continue
            cells.append(dict(cell=[int(d['BlockX']), int(d['BlockY'])],
                              position_cm=[int(d['PosX']), int(d['PosY'])],
                              blacklisted=bool(int(d.get('BlackList', 0) or 0))))
        free = [c for c in cells if not c['blacklisted']]
        out[key] = dict(map_id=map_id, source=note,
                        archive='SFC/Common.sfc', index=idx, offset=off, bytes=size,
                        grid_cells=len(cells), usable=len(free),
                        cell_range=[min(c['cell'][0] for c in cells), max(c['cell'][0] for c in cells),
                                    min(c['cell'][1] for c in cells), max(c['cell'][1] for c in cells)],
                        position_range=[min(c['position_cm'][0] for c in cells), max(c['position_cm'][0] for c in cells),
                                        min(c['position_cm'][1] for c in cells), max(c['position_cm'][1] for c in cells)],
                        cells=cells)
    return out


def vehicle_points():
    out = {}
    for key, map_id in (('dion', 16010), ('europa', 16007), ('vera', 16021)):
        doc = json.loads((ROOT / 'map-data' / f'{key}-entitypoints.json').read_text(encoding='utf-8'))
        rows = [p for p in doc['points'] if 'vehicle' in p['archetype'].lower() or 'boat' in p['archetype'].lower()]
        arch = Counter(p['archetype'] for p in rows)
        types = Counter(p['type_id'] for p in rows)
        out[key] = dict(map_id=map_id, count=len(rows),
                        archetypes=dict(arch), type_ids=dict(types),
                        position_range=[min(p['position_cm'][0] for p in rows), max(p['position_cm'][0] for p in rows),
                                        min(p['position_cm'][1] for p in rows), max(p['position_cm'][1] for p in rows),
                                        min(p['position_cm'][2] for p in rows), max(p['position_cm'][2] for p in rows)],
                        source=f"map-data/{key}-entitypoints.json (фильтр по архетипу)",
                        points=rows)
    return out


def main():
    born = read_born()
    for key, doc in born.items():
        path = ROOT / 'map-data' / f'{key}-bornpos.json'
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print('записан', path.name, '| ячеек', doc['grid_cells'], '| свободных', doc['usable'],
              '| range', doc['cell_range'], doc['position_range'])
    veh = vehicle_points()
    for key, doc in veh.items():
        path = ROOT / 'map-data' / f'{key}-vehiclepoints.json'
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print('записан', path.name, '| точек', doc['count'], '|', doc['archetypes'])
    # поддержка выбора точки в сервере
    sys.path.insert(0, str(ROOT / 'tools'))
    from map_profiles_2022 import has_local_profile
    for map_id in (16010, 16007, 16021, 16009):
        print('has_local_profile(%d) =' % map_id, has_local_profile(map_id))


if __name__ == '__main__':
    main()
