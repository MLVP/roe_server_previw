"""Генератор ярлыка клиента: аргументы запуска и содержимое .lnk."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))

import lnroeuser


class ShortcutTests(unittest.TestCase):
    def test_arguments_contain_uid_and_server(self):
        arguments = lnroeuser.build_arguments(1000, '127.0.0.1:8001')
        self.assertIn('-uid=1000', arguments)
        self.assertIn('-server=127.0.0.1:8001', arguments)
        self.assertIn('-garena', arguments)
        self.assertIn('-language=en', arguments)

    def test_steam_publisher_flag_can_be_disabled(self):
        arguments = lnroeuser.build_arguments(1, '127.0.0.1:8001', publisher='steam')
        self.assertIn('-steam', arguments)
        self.assertNotIn('-garena', arguments)

    def test_shortcut_file_is_created(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root/'game'
            game.mkdir()
            (game/'Europa_Client.exe').write_bytes(b'MZ')
            output = root/'ROE alice.lnk'
            lnroeuser.create_shortcut(game/'Europa_Client.exe', '-uid=1000', game, output)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
