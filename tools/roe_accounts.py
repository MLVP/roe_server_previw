"""Управление локальными пользователями ROE-local-fork.

Примеры:
  python tools/roe_accounts.py register alice --nickname Alice
  python tools/roe_accounts.py list
  python tools/roe_accounts.py launch alice
  python tools/roe_accounts.py serve --port 8099
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import accounts_2022 as accounts


ROOT = Path(__file__).resolve().parents[1]


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_register(args):
    record = accounts.register_account(
        args.name, nickname=args.nickname, actor_uid=args.uid,
        overwrite=args.overwrite, reset_cosmetics=args.reset_cosmetics)
    print_json(accounts.summary(record))
    return 0


def cmd_list(args):
    records = accounts.list_accounts()
    if args.json:
        print_json([accounts.summary(record) for record in records])
        return 0
    if not records:
        print('Пользователей нет. Зарегистрируйте: roe_accounts.py register <name>')
        return 0
    print(f'{ "name":<20} { "nickname":<20} { "actor_uid":<20} created_at')
    for record in records:
        print(f'{record["name"]:<20} {record["nickname"]:<20} {record["actor_uid_hex"]:<20} {record["created_at"]}')
    return 0


def cmd_show(args):
    record = accounts.load_account(args.name)
    if record is None:
        print(f'Пользователь {args.name} не найден', file=sys.stderr)
        return 1
    print_json(accounts.summary(record))
    return 0


def cmd_update(args):
    record = accounts.update_account(args.name, nickname=args.nickname,
                                     actor_uid=args.uid, notes=args.notes)
    print_json(accounts.summary(record))
    return 0


def cmd_delete(args):
    if not args.yes:
        answer = input(f'Удалить {args.name} вместе с cosmetics.json? [y/N] ')
        if answer.strip().lower() not in ('y', 'yes', 'д', 'да'):
            print('Отменено')
            return 1
    accounts.delete_account(args.name, allow_default=args.force)
    print(f'Удалён {args.name}')
    return 0


def cmd_launch(args):
    record = accounts.load_account(args.name)
    if record is None:
        print(f'Пользователь {args.name} не найден; сначала register', file=sys.stderr)
        return 1
    launcher = Path(args.launcher) if args.launcher else ROOT / 'play.cmd'
    if not launcher.is_file():
        print(f'Нет launcher: {launcher}', file=sys.stderr)
        return 1
    extra = list(args.extra)
    dry_run = args.dry_run
    if '--dry-run' in extra:
        extra.remove('--dry-run')
        dry_run = True
    command = ['cmd.exe', '/c', 'call', str(launcher), '-Profile', record['name']] + extra
    if dry_run:
        print(' '.join(command))
        return 0
    if os.name != 'nt':
        print('Запуск клиента рассчитан на Windows; используйте play.cmd вручную', file=sys.stderr)
        return 1
    return subprocess.call(command, cwd=str(ROOT))


def cmd_serve(args):
    from account_service import serve
    room = None
    if args.room:
        from room_control_2022 import RoomControl
        room = RoomControl(mode=args.room_mode, room_id=args.room_id, api_port=args.room_api_port,
                           client=args.room_client, profile=args.room_profile)
    return serve(args.host, args.port, allow_delete=args.allow_delete, room=room)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    register = sub.add_parser('register', help='Создать локального пользователя')
    register.add_argument('name')
    register.add_argument('--nickname')
    register.add_argument('--uid', help='Явный UID (decimal или 0xhex); по умолчанию из имени')
    register.add_argument('--overwrite', action='store_true', help='Обновить account.json')
    register.add_argument('--reset-cosmetics', action='store_true', help='Сбросить cosmetics.json')
    register.set_defaults(func=cmd_register)

    listing = sub.add_parser('list', help='Показать пользователей')
    listing.add_argument('--json', action='store_true')
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser('show', help='Показать пользователя')
    show.add_argument('name')
    show.set_defaults(func=cmd_show)

    update = sub.add_parser('update', help='Изменить ник/UID/заметки')
    update.add_argument('name')
    update.add_argument('--nickname')
    update.add_argument('--uid')
    update.add_argument('--notes')
    update.set_defaults(func=cmd_update)

    delete = sub.add_parser('delete', help='Удалить пользователя')
    delete.add_argument('name')
    delete.add_argument('--force', action='store_true', help='Разрешить удаление default')
    delete.add_argument('--yes', action='store_true', help='Без интерактивного подтверждения')
    delete.set_defaults(func=cmd_delete)

    launch = sub.add_parser('launch', help='Запустить play.cmd с профилем')
    launch.add_argument('name')
    launch.add_argument('--launcher', help='Путь к play.cmd/run-roe-2022.cmd')
    launch.add_argument('--dry-run', action='store_true')
    launch.add_argument('extra', nargs=argparse.REMAINDER, help='Дополнительные параметры launcher')
    launch.set_defaults(func=cmd_launch)

    serve = sub.add_parser('serve', help='HTTP-сервис регистрации и игровая комната')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8099)
    serve.add_argument('--allow-delete', action='store_true')
    serve.add_argument('--room', action='store_true', help='поднять игровую комнату (лобби+game)')
    serve.add_argument('--room-mode', default='dion')
    serve.add_argument('--room-id', default='dion-1')
    serve.add_argument('--room-api-port', type=int, default=18080)
    serve.add_argument('--room-client', help='папка клиента 2022 для комнаты')
    serve.add_argument('--room-profile', default='default')
    serve.set_defaults(func=cmd_serve)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except accounts.AccountError as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
