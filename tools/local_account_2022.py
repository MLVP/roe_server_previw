"""Именованные локальные профили; идентичность не является оригинальной авторизацией.

Зарегистрированные пользователи читаются из ``accounts/<name>/account.json``
(см. accounts_2022.py). Для незарегистрированных имён сохранён прежний
детерминированный UID и путь ``runtime/local-accounts/<name>``.
"""
from pathlib import Path
import re

from accounts_2022 import (
    DEFAULT_ACTOR_UID,
    AccountError,
    derive_uid,
    load_account_at,
)

_RESERVED = {'con', 'prn', 'aux', 'nul'} | {
    prefix + str(number) for prefix in ('com', 'lpt') for number in range(1, 10)
}


def local_account(runtime, name='default', accounts_root=None):
    """Возвращает устойчивый public UID, ник и путь; не создаёт файлы/сокеты.

    ``accounts_root`` включает явный реестр (launcher передаёт ROOT/'accounts').
    Без него сохраняется историческое поведение для тестов и lan_tunnel.
    """
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}', name):
        raise ValueError('Profile:1..32 ASCII букв/цифр, _ и -, начало буква/цифра')
    canonical = name.lower()
    if canonical in _RESERVED:
        raise ValueError('Profile: имя устройства Windows запрещено')
    try:
        record = load_account_at(accounts_root, canonical) if accounts_root is not None else None
    except AccountError as error:
        raise ValueError(str(error)) from error
    if record is not None:
        return dict(name=canonical, actor_uid=record['actor_uid'],
                    state_file=record['state_file'], nickname=record['nickname'],
                    registered=True)
    runtime = Path(runtime)
    if canonical == 'default':
        state = runtime / 'local-account/cosmetics.json'
        uid = DEFAULT_ACTOR_UID
        nickname = 'Player'
    else:
        state = runtime / 'local-accounts' / canonical / 'cosmetics.json'
        uid = derive_uid(canonical)
        nickname = canonical
    return dict(name=canonical, actor_uid=uid, state_file=str(state),
                nickname=nickname, registered=False)
