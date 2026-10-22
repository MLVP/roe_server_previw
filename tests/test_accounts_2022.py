"""Локальный реестр пользователей: изоляция, UID, ник, cosmetics.json."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import accounts_2022 as accounts
from local_account_2022 import local_account


class AccountsTests(unittest.TestCase):
    def setUp(self):
        self._old_root = accounts.ACCOUNTS_ROOT
        self._tmp = tempfile.TemporaryDirectory()
        accounts.ACCOUNTS_ROOT = Path(self._tmp.name)

    def tearDown(self):
        accounts.ACCOUNTS_ROOT = self._old_root
        self._tmp.cleanup()

    def test_register_list_show_delete(self):
        alice = accounts.register_account('alice', nickname='Alice')
        self.assertEqual(alice['nickname'], 'Alice')
        self.assertEqual(alice['actor_uid'] & 3, 0)
        self.assertTrue((accounts.ACCOUNTS_ROOT / 'alice' / 'account.json').is_file())
        self.assertTrue((accounts.ACCOUNTS_ROOT / 'alice' / 'cosmetics.json').is_file())
        self.assertEqual([r['name'] for r in accounts.list_accounts()], ['alice'])
        self.assertEqual(accounts.load_account('ALICE')['nickname'], 'Alice')
        accounts.delete_account('alice')
        self.assertIsNone(accounts.load_account('alice'))

    def test_duplicate_and_overwrite(self):
        first = accounts.register_account('alice', nickname='Alice')
        with self.assertRaises(accounts.AccountExists):
            accounts.register_account('alice')
        second = accounts.register_account('alice', nickname='Alice2', overwrite=True)
        self.assertEqual(second['actor_uid'], first['actor_uid'])
        self.assertEqual(second['nickname'], 'Alice2')
        self.assertEqual(second['created_at'], first['created_at'])

    def test_uids_are_unique_and_collisions_bump(self):
        first = accounts.register_account('alice')
        second = accounts.register_account('bob')
        self.assertNotEqual(first['actor_uid'], second['actor_uid'])
        # Явный занятый UID запрещён.
        with self.assertRaises(accounts.AccountError):
            accounts.register_account('carol', actor_uid=first['actor_uid'])

    def test_local_account_uses_explicit_registry_only(self):
        record = accounts.register_account('alice', nickname='Alice')
        found = local_account(ROOT / 'runtime', 'alice', accounts_root=accounts.ACCOUNTS_ROOT)
        self.assertTrue(found['registered'])
        self.assertEqual(found['actor_uid'], record['actor_uid'])
        self.assertEqual(found['nickname'], 'Alice')
        fallback = local_account(ROOT / 'runtime', 'alice')
        self.assertFalse(fallback['registered'])
        self.assertNotEqual(fallback['state_file'], record['state_file'])

    def test_invalid_names_nicknames_and_uids(self):
        for name in ('', '../a', 'a/b', '.a', 'con', 'имя', 'a' * 33, None):
            with self.subTest(name=name), self.assertRaises(accounts.AccountError):
                accounts.register_account(name)
        for nickname in ('', 'a\x00b', 'a\nb', 'x' * 64):
            with self.subTest(nickname=nickname), self.assertRaises(accounts.AccountError):
                accounts.register_account('alice', nickname=nickname)
        for uid in (0, -1, 2 ** 64, True, 'nope'):
            with self.subTest(uid=uid), self.assertRaises(accounts.AccountError):
                accounts.register_account('alice', actor_uid=uid)

    def test_default_is_not_deleted_without_flag(self):
        accounts.register_account('default', nickname='Player')
        with self.assertRaises(accounts.AccountError):
            accounts.delete_account('default')
        accounts.delete_account('default', allow_default=True)
        self.assertIsNone(accounts.load_account('default'))

    def test_load_account_at_explicit_root(self):
        record = accounts.register_account('alice', nickname='Alice')
        loaded = accounts.load_account_at(accounts.ACCOUNTS_ROOT, 'alice')
        self.assertEqual(loaded['actor_uid'], record['actor_uid'])
        self.assertEqual(loaded['state_file'],
                         str(accounts.ACCOUNTS_ROOT / 'alice' / 'cosmetics.json'))
        self.assertIsNone(accounts.load_account_at(Path(self._tmp.name) / 'missing', 'alice'))


if __name__ == '__main__':
    unittest.main()
