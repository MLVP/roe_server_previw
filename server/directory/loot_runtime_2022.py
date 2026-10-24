"""Рантайм-генератор лута: заполняет всю карту по оригинальным точкам.

Точки берутся из map-data/*-entitypoints.json (ENTITYPOINTCONFIG оригинала),
предметы — только из поддерживаемых сервером пулов (modes/common/loot-pools.json).
Результат — каталог в схеме LootCatalog (те же поля entities/index/entity_uid),
который эндпоинт прогоняет через обычную LootCatalog.load.
"""
import json
from pathlib import Path
import random

SCHEMA = 1
INDEX_BASE = 170001
UID_BASE = 0x0CE0000000000
COMPANION_OFFSET_CM = 50

# Типы точек оригинала и их «богатство».
POINT_CLASSES = {
    'ENTITY_eLoot_level05': 'rich',
    'ENTITY_eLoot_level03': 'medium',
    'EU_LootBox': 'common',
}

# Шанс выпадения категории на точке (сумма < 1: остальное — пустая точка).
ROLLS = {
    'rich': ((0.55, 'weapon'), (0.15, 'ammo'), (0.10, 'medical'),
             (0.10, 'armor'), (0.06, 'throwable'), (0.04, 'attachment')),
    'medium': ((0.42, 'weapon'), (0.18, 'ammo'), (0.12, 'medical'),
               (0.10, 'armor'), (0.08, 'throwable'), (0.10, 'attachment')),
    'common': ((0.30, 'weapon'), (0.20, 'ammo'), (0.14, 'medical'),
               (0.08, 'armor'), (0.09, 'throwable'), (0.07, 'attachment')),
}

GUN_TIER = {'sniper': 1, 'ar': 1, 'smg': 1, 'shotgun': 1, 'lmg': 1, 'pistol': 3}
MEDICAL_WEIGHTS = ((70001, 5), (70002, 2), (70003, 1))
THROWABLE_WEIGHTS = ((50001, 3), (50002, 2), (50003, 1))
BANDAGE_QUANTITY = (1, 3)
THROWABLE_QUANTITY = (1, 2)


def _gun_tier(definition):
    if definition >= 20000:
        return 'pistol'
    return {1: 'sniper', 2: 'ar', 3: 'smg', 4: 'shotgun', 6: 'lmg'}.get(definition // 100 % 10, 'ar')


def _weighted(rng, pairs):
    total = sum(weight for _, weight in pairs)
    roll = rng.uniform(0, total)
    for value, weight in pairs:
        if roll <= weight:
            return value
        roll -= weight
    return pairs[-1][0]


def _load_points(path):
    doc = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    counts = {}
    rows = []
    for row in doc['points']:
        point_class = POINT_CLASSES.get(row['archetype'])
        if point_class is None:
            continue
        counts[point_class] = counts.get(point_class, 0) + 1
        rows.append((point_class, row['position_cm']))
    if not rows:
        raise ValueError('в файле точек нет точек лута (eLoot_level*/LootBox)')
    return doc, rows, counts


def load_weights(path):
    """Конфиг шансов генерации: {"default": 1.0, "items": {"<id>": 0.1, ...}}.

    Вес — шанс появления предмета на точке (0.0..1.0). Компаньоны-патроны
    появившегося оружия вес не проверяют: оружие всегда идёт со своими паками.
    """
    if path is None:
        return {'default': 1.0, 'items': {}}
    doc = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    default = float(doc.get('default', 1.0))
    if not 0.0 <= default <= 1.0:
        raise ValueError('default должен быть 0.0..1.0')
    items = {}
    for key, value in (doc.get('items') or {}).items():
        weight = float(value)
        if not 0.0 <= weight <= 1.0:
            raise ValueError('вес предмета %s должен быть 0.0..1.0' % key)
        items[int(key)] = weight
    return {'default': default, 'items': items}


def build_catalog(points_path, pools_path, seed=None, max_entities=12000, weights_path=None):
    """Случайный, но детерминированный по seed каталог на всю карту."""
    doc, rows, class_counts = _load_points(points_path)
    pools = json.loads(Path(pools_path).read_text(encoding='utf-8-sig'))
    weights = load_weights(weights_path)
    if seed is None:
        seed = random.SystemRandom().randint(1, 2 ** 31 - 1)
    rng = random.Random(seed)
    max_entities = 12000 if max_entities is None else int(max_entities)
    if not 1 <= max_entities <= 50000:
        raise ValueError('max_entities должен быть 1..50000')

    def keep(item_id):
        # Вес 1.0 не тратит бросок rng: каталог без весов совпадает с прежним.
        weight = weights['items'].get(int(item_id), weights['default'])
        return weight >= 1.0 or rng.random() < weight

    guns = list(pools['guns'])
    gun_pairs = [(g, GUN_TIER[_gun_tier(g)]) for g in guns]
    ammo_by_gun = {int(k): int(v) for k, v in pools['ammo_by_gun'].items()}
    pack_quantities = {int(k): int(v) for k, v in pools['ammo_pack_quantities'].items()}
    ammo_pairs = [(a, pack_quantities.get(a, 50)) for a in pools['ammo']]
    helmet_pairs = [(h, h - 200099) for h in pools['helmets']]
    vest_pairs = [(v, v - 200999) for v in pools['vests']]
    backpacks = list(pools['backpacks'])
    attachments = list(pools['attachments'])

    entities, categories = [], {}
    rng.shuffle(rows)

    def emit(item_id, quantity, position, category):
        number = len(entities)
        if number >= max_entities:
            return False
        entities.append({
            'index': INDEX_BASE + number,
            'entity_uid': UID_BASE + (seed % 65536) * 65536 + number * 17 + 1,
            'item_id': int(item_id),
            'quantity': int(quantity),
            'position': [int(position[0]), int(position[1]), int(position[2])],
        })
        categories[category] = categories.get(category, 0) + 1
        return True

    for point_class, position in rows:
        if len(entities) >= max_entities:
            break
        roll = rng.random()
        picked = None
        for limit, category in ROLLS[point_class]:
            if roll <= limit:
                picked = category
                break
            roll -= limit
        if picked is None:
            continue
        x, y, z = position
        if picked == 'weapon':
            gun = _weighted(rng, gun_pairs)
            # Вес оружия решает, появится ли точка с ним; паки-компаньоны
            # после появления оружия идут всегда, без броска веса.
            if not keep(gun):
                continue
            caliber = ammo_by_gun[gun]
            packs = 1 if rng.random() < 0.2 else 2
            # Оружие появляется только вместе со своими паками: иначе у
            # последних точек у лимита оказалось бы оружие без патронов.
            if len(entities) + 1 + packs > max_entities:
                break
            if not emit(gun, 1, (x, y, z), 'weapon'):
                break
            for pack in range(packs):
                dx = COMPANION_OFFSET_CM if pack % 2 == 0 else -COMPANION_OFFSET_CM
                dy = COMPANION_OFFSET_CM if rng.random() < 0.5 else -COMPANION_OFFSET_CM
                emit(caliber, pack_quantities[caliber], (x + dx, y + dy, z), 'ammo')
        elif picked == 'ammo':
            caliber = _weighted(rng, ammo_pairs)
            if keep(caliber):
                emit(caliber, pack_quantities[caliber], (x, y, z), 'ammo')
        elif picked == 'medical':
            item = _weighted(rng, MEDICAL_WEIGHTS)
            quantity = rng.randint(*BANDAGE_QUANTITY) if item == 70001 else 1
            if keep(item):
                emit(item, quantity, (x, y, z), 'medical')
        elif picked == 'armor':
            if point_class == 'common' or rng.random() < 0.5:
                item = _weighted(rng, helmet_pairs) if rng.random() < 0.5 else _weighted(rng, vest_pairs)
            else:
                item = rng.choice(backpacks)
            if keep(item):
                emit(item, 1, (x, y, z), 'armor')
        elif picked == 'throwable':
            item = _weighted(rng, THROWABLE_WEIGHTS)
            if keep(item):
                emit(item, rng.randint(*THROWABLE_QUANTITY), (x, y, z), 'throwable')
        elif picked == 'attachment':
            item = rng.choice(attachments)
            if keep(item):
                emit(item, 1, (x, y, z), 'attachment')

    if not entities:
        raise ValueError('генератор не создал ни одного предмета')
    return {
        'map_id': int(doc.get('map_id') or 0),
        'radius_cm': 2000,
        'visible_limit': 128,
        'batch_limit': 16,
        'policy': 'runtime_random_full_map',
        'seed': seed,
        'max_entities': max_entities,
        'source_points': str(Path(points_path).name),
        'source_point_classes': class_counts,
        'generated_counts': categories,
        'weights_source': str(Path(weights_path).name) if weights_path else None,
        'weights_default': weights['default'],
        'ammo_by_gun': pools['ammo_by_gun'],
        'ammo_pack_quantities': pools['ammo_pack_quantities'],
        'generator_schema': SCHEMA,
        'entities': entities,
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Генерирует случайный каталог лута на всю карту')
    parser.add_argument('--points', type=Path, required=True, help='map-data/<map>-entitypoints.json')
    parser.add_argument('--pools', type=Path, required=True, help='modes/common/loot-pools.json')
    parser.add_argument('--out', type=Path, required=True, help='куда записать каталог')
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--max-entities', type=int, default=12000)
    parser.add_argument('--weights', type=Path,
                        help='modes/<map>/loot-weights.json с шансами генерации предметов')
    args = parser.parse_args(argv)
    config = build_catalog(args.points, args.pools, seed=args.seed,
                           max_entities=args.max_entities, weights_path=args.weights)
    args.out.write_text(json.dumps(config, ensure_ascii=False) + '\n', encoding='utf-8')
    print('seed', config['seed'], '| сущностей', len(config['entities']),
          '|', config['generated_counts'])


if __name__ == '__main__':
    main()
