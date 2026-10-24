"""Аргументы рантайм-лута должны быть в парсере лаунчера windows_launch.py.

Регрессия: в один из запусков комната падала на старте с
'error: unrecognized arguments: --loot-generation ...', потому что новые
--loot-* ключи mode.json добавили только в эндпоинт, а не в лаунчер.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'tools' / 'windows_launch.py'
OPTIONS = ('--loot-generation', '--loot-points', '--loot-pools',
           '--loot-max-entities', '--loot-seed', '--loot-weights',
           '--vehicle-points', '--vehicle-count', '--vehicle-configs')


def run_launcher(*argv):
    return subprocess.run([sys.executable, '-X', 'utf8', '-B', str(LAUNCHER), *argv],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=120)


class LauncherRuntimeArgsTests(unittest.TestCase):
    def test_help_declares_runtime_loot_options(self):
        result = run_launcher('--help')
        out = (result.stdout or '') + (result.stderr or '')
        self.assertEqual(result.returncode, 0, out[-400:])
        for option in OPTIONS:
            self.assertIn(option, out)

    def test_runtime_mode_requires_points_and_pools(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_launcher('--client', str(Path(folder) / 'no-client'),
                                  '--services-only', '--loot-generation', 'runtime')
        out = (result.stdout or '') + (result.stderr or '')
        # Аргументы распознаны, иначе argparse жалуется раньше нашей проверки.
        self.assertNotIn('unrecognized arguments', out, out[-400:])
        self.assertIn('loot-generation runtime требует --loot-points', out)

    def test_mode_files_referenced_by_modes_exist(self):
        for mode in ('dion', 'europa', 'vera'):
            args = json.loads((ROOT / 'modes' / mode / 'mode.json')
                              .read_text(encoding='utf-8'))['launcher_args']
            generation = args[args.index('--loot-generation') + 1]
            self.assertEqual(generation, 'runtime', mode)
            for option in ('--loot-points', '--loot-pools'):
                value = args[args.index(option) + 1]
                resolved = (ROOT / 'modes' / mode / value)
                self.assertTrue(resolved.is_file(), '%s: %s' % (mode, resolved))


if __name__ == '__main__':
    unittest.main()
