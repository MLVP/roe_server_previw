"""Менеджер пользователей локального сервера.

Создаёт папку пользователя и два идентификатора:

  * uid       - 32-битный id, который клиент объявляет в логине
                (аргумент `-uid=` клиента и ключ реестра). Генерируется
                случайно;
  * actor_uid - 64-битная игровая личность, которую сервер выдаёт в
                ENTER_GAME_RSP (0x32b) и которая дальше идёт по всей сессии.

Структура:
  accounts/<name>/account.json     аккаунт (совпадает с accounts_2022, тот же
                                    actor_uid, поэтому лаунчер и косметика
                                    работают с тем же профилем);
  accounts/<name>/cosmetics.json   внешний вид;
  users/<name>/user.json           профиль пользователя (оба id);
  users/registry.json              реестр uid -> профиль, его читает
                                    объединённый сервис лобби.

Примеры:
  .tools\\python\\python.exe tools\\roe_user_manager.py add alice --nickname Alice
  .tools\\python\\python.exe tools\\roe_user_manager.py list
  .tools\\python\\python.exe tools\\roe_user_manager.py show alice
  .tools\\python\\python.exe tools\\roe_user_manager.py remove alice
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
USERS = ROOT / 'users'
REGISTRY = USERS / 'registry.json'
ACCOUNTS = ROOT / 'accounts'
NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z')
UID_MIN = 1000
UID_MAX = 0x7fffffff
ACTOR_UID_BASE = 0x515BB100000000
COSMETICS_TEMPLATE = ACCOUNTS / 'awp' / 'cosmetics.json'


def validate_name(name):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError('имя пользователя: 1..32 символов [A-Za-z0-9_-]')
    return name.lower()


def load_registry():
    if not REGISTRY.is_file():
        return {}
    data = json.loads(REGISTRY.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('registry.json должен быть объектом')
    return data


def save_registry(registry):
    USERS.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def new_uid(used):
    """Случайный uid в свободном диапазоне."""
    while True:
        value = secrets.randbelow(UID_MAX - UID_MIN) + UID_MIN
        if value not in used:
            return value


def next_ids(registry):
    used_uids = {int(row['uid']) for row in registry.values()
                 if isinstance(row, dict) and 'uid' in row}
    used_actor = {int(str(row['actor_uid']), 0) for row in registry.values()
                  if isinstance(row, dict) and 'actor_uid' in row}
    uid = new_uid(used_uids)
    # actor_uid: узнаваемая база 0x515BB1 + случайные 32 бита.
    actor_uid = ACTOR_UID_BASE + secrets.randbelow(1 << 32)
    while actor_uid in used_actor:
        actor_uid = ACTOR_UID_BASE + secrets.randbelow(1 << 32)
    return uid, actor_uid


def user_folder(name):
    return USERS / validate_name(name)


def account_folder(name):
    return ACCOUNTS / validate_name(name)


def write_account(name, nickname, actor_uid):
    folder = account_folder(name)
    folder.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    account = {
        'version': 1,
        'name': name,
        'nickname': nickname,
        'actor_uid': hex(actor_uid),
        'created_at': now,
        'updated_at': now,
        'cosmetics': 'cosmetics.json',
        'session_key_policy': 'udp-per-connection',
        'notes': '',
    }
    (folder / 'account.json').write_text(json.dumps(account, ensure_ascii=False, indent=2) + '\n',
                                         encoding='utf-8')
    cosmetics = folder / 'cosmetics.json'
    if not cosmetics.is_file():
        if COSMETICS_TEMPLATE.is_file():
            shutil.copyfile(COSMETICS_TEMPLATE, cosmetics)
        else:
            cosmetics.write_text(json.dumps({}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return account


def add_user(args):
    name = validate_name(args.name)
    registry = load_registry()
    uid, actor_uid = next_ids(registry)
    if args.uid is not None:
        uid = int(args.uid)
        if any(row.get('uid') == uid for row in registry.values() if isinstance(row, dict)):
            raise ValueError(f'uid {uid} уже занят')
    if args.actor_uid is not None:
        actor_uid = int(str(args.actor_uid), 0)
    nickname = args.nickname or name
    folder = user_folder(name)
    if (folder / 'user.json').is_file() and not args.force:
        raise ValueError(f'пользователь {name} уже существует (--force перезаписывает)')
    account = write_account(name, nickname, actor_uid)
    account_path = account_folder(name)
    try:
        account_reference = str(account_path.relative_to(ROOT)).replace('\\', '/')
    except ValueError:
        account_reference = str(account_path)
    profile = {
        'version': 1,
        'name': name,
        'nickname': nickname,
        'uid': uid,
        'actor_uid': hex(actor_uid),
        'created_at': account['created_at'],
        'account': account_reference,
        'cosmetics': 'cosmetics.json',
    }
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'user.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n',
                                      encoding='utf-8')
    registry[str(uid)] = {'name': name, 'nickname': nickname,
                          'uid': uid, 'actor_uid': hex(actor_uid)}
    save_registry(registry)
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


def list_users(args):
    registry = load_registry()
    rows = sorted(registry.items(), key=lambda item: int(item[0]))
    if not rows:
        print('пользователей нет')
        return 0
    print(f"{'uid':>12}  {'actor_uid':>18}  {'name':<16} nickname")
    for uid, row in rows:
        print(f"{uid:>12}  {row.get('actor_uid', ''):>18}  {row.get('name', ''):<16} {row.get('nickname', '')}")
    return 0


def show_user(args):
    name = validate_name(args.name)
    path = user_folder(name) / 'user.json'
    if not path.is_file():
        raise ValueError(f'пользователь {name} не найден')
    print(path.read_text(encoding='utf-8'))
    return 0


def remove_user(args):
    name = validate_name(args.name)
    folder = user_folder(name)
    if not folder.is_dir():
        raise ValueError(f'пользователь {name} не найден')
    registry = load_registry()
    registry = {key: row for key, row in registry.items()
                if not (isinstance(row, dict) and row.get('name') == name)}
    save_registry(registry)
    shutil.rmtree(folder, ignore_errors=True)
    shutil.rmtree(account_folder(name), ignore_errors=True)
    print(f'удалён {name}')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add', help='создать пользователя')
    add.add_argument('name')
    add.add_argument('--nickname')
    add.add_argument('--uid', type=int, help='задать uid вручную; по умолчанию случайный')
    add.add_argument('--actor-uid')
    add.add_argument('--force', action='store_true')
    add.set_defaults(func=add_user)
    listing = sub.add_parser('list', help='показать реестр')
    listing.set_defaults(func=list_users)
    show = sub.add_parser('show', help='показать профиль')
    show.add_argument('name')
    show.set_defaults(func=show_user)
    remove = sub.add_parser('remove', help='удалить пользователя')
    remove.add_argument('name')
    remove.set_defaults(func=remove_user)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as error:
        print('Ошибка: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
