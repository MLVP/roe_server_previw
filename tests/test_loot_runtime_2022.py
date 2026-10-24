"""Рантайм-генератор лута: детерминизм, пулы, лимиты и схема каталога."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server/directory'))
from loot_runtime_2022 import build_catalog
from loot_catalog_2022 import LootCatalog

DION_POINTS = ROOT / 'map-data' / 'dion-entitypoints.json'
EUROPA_POINTS = ROOT / 'map-data' / 'europa-entitypoints.json'
VERA_POINTS = ROOT / 'map-data' / 'vera-entitypoints.json'
POOLS = ROOT / 'modes' / 'common' / 'loot-pools.json'


def pools_doc():
    return json.loads(POOLS.read_text(encoding='utf-8'))


class RuntimeLootTests(unittest.TestCase):
    def test_same_seed_same_catalog_different_seed_differs(self):
        first = build_catalog(DION_POINTS, POOLS, seed=1234, max_entities=400)
        second = build_catalog(DION_POINTS, POOLS, seed=1234, max_entities=400)
        other = build_catalog(DION_POINTS, POOLS, seed=1235, max_entities=400)
        self.assertEqual(first['entities'], second['entities'])
        self.assertNotEqual(first['entities'], other['entities'])
        self.assertEqual(first['seed'], 1234)

    def test_only_supported_ids_and_quantity_rules(self):
        pools = pools_doc()
        allowed = (set(pools['guns']) | set(pools['ammo']) | set(pools['medical'])
                   | set(pools['throwables']) | set(pools['helmets']) | set(pools['vests'])
                   | set(pools['backpacks']) | set(pools['attachments']))
        stackable = set(pools['ammo']) | set(pools['medical']) | set(pools['throwables'])
        for points in (DION_POINTS, EUROPA_POINTS, VERA_POINTS):
            with self.subTest(points=points.name):
                config = build_catalog(points, POOLS, seed=7, max_entities=600)
                indexes, uids = set(), set()
                for entity in config['entities']:
                    self.assertIn(entity['item_id'], allowed)
                    self.assertTrue(1 <= entity['quantity'] <= 100)
                    if entity['item_id'] not in stackable:
                        self.assertEqual(entity['quantity'], 1)
                    self.assertNotIn(entity['index'], indexes)
                    self.assertNotIn(entity['entity_uid'], uids)
                    indexes.add(entity['index'])
                    uids.add(entity['entity_uid'])

    def test_cap_respected_and_ammo_companions_near_weapons(self):
        config = build_catalog(DION_POINTS, POOLS, seed=99, max_entities=200)
        self.assertLessEqual(len(config['entities']), 200)
        self.assertGreater(len(config['entities']), 0)
        pools = pools_doc()
        ammo_by_gun = {int(k): v for k, v in pools['ammo_by_gun'].items()}
        weapons = [e for e in config['entities'] if e['item_id'] in pools['guns']]
        self.assertTrue(weapons)
        for weapon in weapons:
            companions = [e for e in config['entities']
                          if e['item_id'] == ammo_by_gun[weapon['item_id']]
                          and max(abs(a - b) for a, b in zip(e['position'], weapon['position'])) <= 50]
            self.assertTrue(companions, 'у оружия %s нет патронов рядом' % weapon['item_id'])

    def test_full_map_fills_all_point_classes(self):
        config = build_catalog(EUROPA_POINTS, POOLS, seed=5, max_entities=50000)
        classes = config['source_point_classes']
        self.assertGreater(classes.get('common', 0), 1000)
        self.assertGreater(classes.get('rich', 0), 100)
        self.assertGreater(classes.get('medium', 0), 50)
        self.assertGreater(len(config['entities']), 3000)
        generated = config['generated_counts']
        for category in ('weapon', 'ammo', 'medical', 'armor', 'throwable', 'attachment'):
            self.assertGreater(generated.get(category, 0), 0, category)

    def test_generated_catalog_passes_server_loader(self):
        config = build_catalog(VERA_POINTS, POOLS, seed=3, max_entities=500)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'runtime.json'
            path.write_text(json.dumps(config, ensure_ascii=False) + '\n', encoding='utf-8')
            catalog = LootCatalog.load(path, bytes(100))
        self.assertEqual(len(catalog.items), len(config['entities']))
        self.assertEqual(catalog.radius, 2000)
        self.assertEqual(catalog.visible_limit, 128)
        self.assertEqual(catalog.batch_limit, 16)

    def test_rejects_empty_points_and_bad_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'empty.json'
            path.write_text(json.dumps({'map_id': 1, 'points': [
                {'archetype': 'ENTITY_eLoot_vehicle01', 'position_cm': [1, 2, 3]}]}), encoding='utf-8')
            with self.assertRaises(ValueError):
                build_catalog(path, POOLS, seed=1)
        with self.assertRaises(ValueError):
            build_catalog(DION_POINTS, POOLS, seed=1, max_entities=0)


if __name__ == '__main__':
    unittest.main()
