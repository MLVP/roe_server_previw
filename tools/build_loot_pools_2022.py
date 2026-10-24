"""Собирает modes/common/loot-pools.json для рантайм-генератора лута.

Пулы берутся только из id, поддерживаемых сервером (weapon_probe_2022 и
throwable_inventory_2022), соответствие оружие→калибр — из проверенного
каталога Dione (modes/dion/loot-pool61.json, поле ammo_by_gun).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server/directory'))
from weapon_probe_2022 import (AMMUNITION_WEIGHTS, ARMOR_DURABILITY, EQUIPMENT_SLOTS,
                               GUN_PROFILES, MEDICAL_PROFILES, SUPPORTED_ATTACHMENTS)
from throwable_inventory_2022 import THROWABLE_PROFILES

OUT = ROOT / 'modes/common/loot-pools.json'
DION_CATALOG = ROOT / 'modes/dion/loot-pool61.json'

# Пакеты патронов по проверенным количествам Dione (id патрона: патронов в паке).
AMMO_PACK_QUANTITIES = {30001: 90, 30002: 90, 30003: 70, 30004: 60,
                        30005: 50, 30006: 40, 30009: 10}

HELMETS = sorted(d for d in ARMOR_DURABILITY if 200100 <= d < 200200)
VESTS = sorted(d for d in ARMOR_DURABILITY if 201000 <= d < 201100)
BACKPACKS = sorted(d for d in EQUIPMENT_SLOTS if EQUIPMENT_SLOTS[d] == 11)


def main():
    catalog = json.loads(DION_CATALOG.read_text(encoding='utf-8-sig'))
    ammo_by_gun = {int(k): int(v) for k, v in catalog['ammo_by_gun'].items()}
    # USP45 и Glock17 в карте Dione не встречались; обе — 9 мм (как DE→.45 в той же карте).
    ammo_by_gun.setdefault(20001, 30003)
    ammo_by_gun.setdefault(20002, 30003)
    guns = sorted(GUN_PROFILES)
    unknown = [g for g in guns if g not in ammo_by_gun]
    if unknown:
        raise ValueError('нет калибра для оружия: %s' % unknown)
    pools = {
        'schema': 1,
        'guns': guns,
        'ammo_by_gun': {str(g): ammo_by_gun[g] for g in guns},
        'ammo': sorted(AMMUNITION_WEIGHTS),
        'ammo_pack_quantities': {str(k): v for k, v in sorted(AMMO_PACK_QUANTITIES.items())},
        'medical': sorted(MEDICAL_PROFILES),
        'throwables': sorted(THROWABLE_PROFILES),
        'helmets': HELMETS,
        'vests': VESTS,
        'backpacks': BACKPACKS,
        'attachments': sorted(SUPPORTED_ATTACHMENTS),
        'source': {
            'supported_ids': 'server/directory/weapon_probe_2022.py и throwable_inventory_2022',
            'ammo_by_gun': 'modes/dion/loot-pool61.json (ammo_by_gun; USP45/Glock17 — 9 мм по аналогии)',
            'ammo_pack_quantities': 'modes/dion/loot-pool61.json (ammo_quantities)',
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pools, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('записан', OUT)
    print('  оружия', len(pools['guns']), '| патронов', len(pools['ammo']),
          '| медицины', len(pools['medical']), '| гранат', len(pools['throwables']),
          '| шлемов', len(HELMETS), '| жилетов', len(VESTS), '| рюкзаков', len(BACKPACKS),
          '| прицелов', len(pools['attachments']))


if __name__ == '__main__':
    main()
