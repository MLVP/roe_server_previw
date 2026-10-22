"""Менеджер пользователей: оба идентификатора, папка и реестр."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))

import roe_user_manager as manager


class UserManagerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.original = (manager.USERS, manager.REGISTRY, manager.ACCOUNTS, manager.COSMETICS_TEMPLATE)
        manager.USERS = self.root/'users'
        manager.REGISTRY = manager.USERS/'registry.json'
        manager.ACCOUNTS = self.root/'accounts'
        manager.COSMETICS_TEMPLATE = self.root/'accounts/awp/cosmetics.json'

    def tearDown(self):
        (manager.USERS, manager.REGISTRY, manager.ACCOUNTS,
         manager.COSMETICS_TEMPLATE) = self.original
        self.folder.cleanup()

    def add(self, name, **kwargs):
        values = dict(name=name, nickname=None, uid=None, actor_uid=None, force=False)
        values.update(kwargs)
        return manager.add_user(type('Args', (), values)())

    def registry(self):
        return json.loads(manager.REGISTRY.read_text(encoding='utf-8'))

    def test_add_creates_both_ids_and_user_folder(self):
        self.add('alice')
        registry = self.registry()
        self.assertEqual(len(registry), 1)
        uid, row = next(iter(registry.items()))
        self.assertEqual(row['name'], 'alice')
        self.assertEqual(row['uid'], int(uid))
        self.assertEqual(int(row['actor_uid'], 16) >> 32, manager.ACTOR_UID_BASE >> 32)
        profile = json.loads((manager.USERS/'alice'/'user.json').read_text(encoding='utf-8'))
        self.assertEqual(profile['uid'], int(uid))
        self.assertEqual(profile['actor_uid'], row['actor_uid'])
        account = json.loads((manager.ACCOUNTS/'alice'/'account.json').read_text(encoding='utf-8'))
        self.assertEqual(account['actor_uid'], row['actor_uid'])

    def test_uid_is_generated_randomly(self):
        self.add('alice')
        self.add('bob')
        self.add('carol')
        registry = self.registry()
        uids = {row['uid'] for row in registry.values()}
        self.assertEqual(len(uids), 3)
        for value in uids:
            self.assertTrue(manager.UID_MIN <= value <= manager.UID_MAX)

    def test_second_user_gets_distinct_actor_uid(self):
        self.add('alice')
        self.add('bob')
        registry = self.registry()
        actors = {row['actor_uid'] for row in registry.values()}
        self.assertEqual(len(actors), 2)

    def test_explicit_uid_is_kept(self):
        self.add('carol', uid=4242)
        registry = self.registry()
        self.assertIn('4242', registry)
        self.assertEqual(registry['4242']['uid'], 4242)

    def test_duplicate_uid_is_rejected(self):
        self.add('carol', uid=4242)
        with self.assertRaises(ValueError):
            self.add('dave', uid=4242)

    def test_remove_cleans_folder_and_registry(self):
        self.add('alice')
        args = type('Args', (), dict(name='alice'))()
        manager.remove_user(args)
        self.assertFalse((manager.USERS/'alice').exists())
        self.assertFalse((manager.ACCOUNTS/'alice').exists())
        self.assertEqual(self.registry(), {})

    def test_invalid_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.add('bad name')


if __name__ == '__main__':
    unittest.main()
