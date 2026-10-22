"""Проверка публичного состава: лицензия, ключи, отсутствие C# в сервере."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = 'search_'


class PackagingTests(unittest.TestCase):
    def test_lobby_ck_is_external_and_size_checked(self):
        # Сторонний процесс удалён, лобби перенесено на Python: CK обязан
        # лежать только в private/ и нигде не быть встроен в код.
        ck = ROOT/'private/lobby-ck.bin'
        self.assertTrue(ck.is_file())
        self.assertEqual(ck.stat().st_size, 32)
        payload = ck.read_bytes().hex()
        for path in ROOT.rglob('*'):
            if not path.is_file() or 'private' in path.parts:
                continue
            if path.suffix.lower() not in ('.py', '.ps1', '.cs', '.txt', '.md', '.json', '.dat'):
                continue
            text = path.read_text(encoding='utf-8-sig', errors='replace')
            self.assertNotIn(payload, text, 'встроенный CK payload: ' + str(path))

    def test_no_csharp_in_server_code(self):
        # C# остался только в справочнике search_ (протокол), в сервере его нет.
        sources = [path for path in ROOT.rglob('*.cs')
                   if '.tools' not in path.parts and not path.parts[len(ROOT.parts):len(ROOT.parts)+1] == (REFERENCE,)]
        self.assertEqual(sources, [], 'C# в серверном коде не нужен: ' + str(sources[:3]))
        self.assertEqual([path for path in ROOT.rglob('*.csproj') if '.tools' not in path.parts], [])

    def test_mit_notice_is_kept(self):
        # Уведомление MIT обязано остаться в проекте, даже если справочник
        # с исходниками на C# удалён.
        rights = (ROOT/'RIGHTS.md').read_text(encoding='utf-8')
        self.assertIn('MIT License', rights)
        self.assertIn('blip-rgb', rights)
        license_path = ROOT/REFERENCE/'Ring-of-Elysium-Lobby-Emulator/LICENSE'
        if license_path.is_file():
            text = license_path.read_text(encoding='utf-8')
            self.assertIn('MIT License', text)
            self.assertIn('blip-rgb', text)

    def test_only_fixed_local_pair_is_explicitly_allowed(self):
        text = (ROOT/'.gitignore').read_text()
        self.assertIn('!private/candidate-001.key', text)
        self.assertIn('!private/lobby-ck.bin', text)
        self.assertEqual((ROOT/'private/candidate-001.key').stat().st_size, 16)
        self.assertEqual((ROOT/'private/lobby-ck.bin').stat().st_size, 32)
        self.assertIn('private/*', text)
