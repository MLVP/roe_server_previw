"""Создаёт ярлык Windows для локального клиента ROE.

    lnroeuser -uid [uid] -f [game folder] -o [shortcut path]

Пример:
  lnroeuser -uid 1512837187 -f "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Ring of Elysium" ^
            -o "%USERPROFILE%\\Desktop\\ROE alice.lnk"

Ярлык запускает Europa_Client.exe с `-uid=<uid>` (uid игрока),
`-server=<адрес лобби>` и рабочей папкой = папка игры. Ничего в файлах
игры не меняется.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER = '127.0.0.1:8001'
CLIENT_EXE = 'Europa_Client.exe'


def build_arguments(uid, server, language='en', publisher='garena'):
    return f'-language={language} -{publisher} -uid={uid} -server={server}'


def create_shortcut(target, arguments, working_directory, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # The values go through the environment: PowerShell would split paths with
    # spaces when they are passed as command line arguments.
    environment = dict(os.environ)
    environment['ROE_LNK_PATH'] = str(output)
    environment['ROE_LNK_TARGET'] = str(target)
    environment['ROE_LNK_ARGS'] = arguments
    environment['ROE_LNK_WD'] = str(working_directory)
    script = ('$ws = New-Object -ComObject WScript.Shell; '
              '$sc = $ws.CreateShortcut($env:ROE_LNK_PATH); '
              '$sc.TargetPath = $env:ROE_LNK_TARGET; '
              '$sc.Arguments = $env:ROE_LNK_ARGS; '
              '$sc.WorkingDirectory = $env:ROE_LNK_WD; '
              '$sc.IconLocation = $env:ROE_LNK_TARGET + ",0"; '
              '$sc.Description = "Ring of Elysium local"; '
              '$sc.Save()')
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
        capture_output=True, text=True, encoding='utf-8', errors='replace', env=environment)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or 'powershell failed').strip())
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-uid', required=True, help='uid игрока (users/registry.json)')
    parser.add_argument('-f', '--folder', required=True, help='папка игры с Europa_Client.exe')
    parser.add_argument('-o', '--output', required=True, help='путь к ярлыку (.lnk)')
    parser.add_argument('-s', '--server', default=DEFAULT_SERVER, help='адрес лобби host:port')
    parser.add_argument('-language', default='en')
    parser.add_argument('--no-garena', action='store_true', help='не добавлять -garena')
    args = parser.parse_args(argv)
    try:
        uid = int(str(args.uid), 0)
    except ValueError:
        print('Ошибка: -uid должен быть числом', file=sys.stderr)
        return 2
    folder = Path(args.folder).expanduser()
    executable = folder / CLIENT_EXE
    if not executable.is_file():
        print(f'Ошибка: нет {executable}', file=sys.stderr)
        return 2
    arguments = build_arguments(uid, args.server, args.language,
                                'steam' if args.no_garena else 'garena')
    output = create_shortcut(executable, arguments, folder, Path(args.output).expanduser())
    print(json.dumps({'shortcut': str(output), 'target': str(executable),
                      'arguments': arguments, 'working_directory': str(folder),
                      'uid': uid, 'server': args.server}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
