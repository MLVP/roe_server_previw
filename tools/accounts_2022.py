"""Локальный реестр пользователей ROE 2022.

Данные хранятся в ``accounts/<name>/``:
- ``account.json`` — имя, ник, synthetic actor UID, дата создания;
- ``cosmetics.json`` — состояние выбора внешности (формат LocalCosmetics).

Это не оригинальная авторизация и не Steam-аккаунт. UID синтетический,
нужен только для разделения локальных профилей в эмуляторе.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ROOT = ROOT / 'accounts'
_env_root = os.environ.get('ROE_ACCOUNTS_DIR')
ACCOUNTS_ROOT = Path(_env_root).expanduser() if _env_root else _DEFAULT_ROOT
if not ACCOUNTS_ROOT.is_absolute():
    ACCOUNTS_ROOT = (ROOT / ACCOUNTS_ROOT).resolve()
else:
    ACCOUNTS_ROOT = ACCOUNTS_ROOT.resolve()

DEFAULT_ACTOR_UID = 0x515BB1E1DD242C
MAX_NICKNAME_BYTES = 63
_NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z')
_RESERVED = {'con', 'prn', 'aux', 'nul'} | {
    prefix + str(number) for prefix in ('com', 'lpt') for number in range(1, 10)
}
_LOCK = threading.RLock()


class AccountError(ValueError):
    pass


class AccountExists(AccountError):
    pass


class AccountNotFound(AccountError):
    pass


def validate_name(name):
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise AccountError('Имя: 1..32 ASCII букв/цифр, _ и -, начало буква/цифра')
    canonical = name.lower()
    if canonical in _RESERVED:
        raise AccountError('Имя является зарезервированным именем Windows')
    return canonical


def validate_nickname(nickname):
    if not isinstance(nickname, str) or not nickname:
        raise AccountError('Ник: непустая строка')
    if '\x00' in nickname or any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in nickname):
        raise AccountError('Ник: запрещены управляющие символы и NUL')
    encoded = nickname.encode('utf-8')
    if len(encoded) > MAX_NICKNAME_BYTES:
        raise AccountError(f'Ник: не более {MAX_NICKNAME_BYTES} байт UTF-8')
    return nickname


def _path_for(name):
    canonical = validate_name(name)
    return ACCOUNTS_ROOT / canonical


def _account_file(name):
    return _path_for(name) / 'account.json'


def _cosmetics_file(name):
    return _path_for(name) / 'cosmetics.json'


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.tmp-', suffix='.json', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def default_cosmetics_state():
    """Пустое состояние выбора; каталог владения берётся из config/cosmetics.json."""
    return {
        'gun_skins': {},
        'avatar': [0, 0, 0, 0, 0],
        'avatar_applied': False,
        'accessory_selection': [],
    }


def derive_uid(name):
    """Детерминированный synthetic UID в диапазоне, проверенном локальным стендом."""
    canonical = validate_name(name)
    if canonical == 'default':
        return DEFAULT_ACTOR_UID
    digest = hashlib.sha256(('roe-local-2022:' + canonical).encode('ascii')).digest()
    uid = 0x515BB100000000 | (int.from_bytes(digest[:4], 'big') & 0xFFFFFFFC)
    if uid == DEFAULT_ACTOR_UID:
        uid ^= 4
    return uid


def _as_uid(value):
    if isinstance(value, bool):
        raise AccountError('actor_uid: нужно целое или hex-строка')
    if isinstance(value, int):
        uid = value
    elif isinstance(value, str):
        text = value.strip().lower()
        try:
            uid = int(text, 16) if text.startswith('0x') else int(text)
        except ValueError as error:
            raise AccountError('actor_uid: неверное число') from error
    else:
        raise AccountError('actor_uid: нужно целое или hex-строка')
    if not 0 < uid < 2 ** 64:
        raise AccountError('actor_uid: нужен ненулевой U64')
    return uid


def _load_raw(name):
    path = _account_file(name)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise AccountError(f'Повреждён account.json для {name}: {error}') from error
    if not isinstance(value, dict):
        raise AccountError(f'account.json для {name} должен быть объектом')
    return value


def _normalize(name, value):
    canonical = validate_name(name)
    nickname = validate_nickname(value.get('nickname', canonical if canonical != 'default' else 'Player'))
    uid = _as_uid(value.get('actor_uid', derive_uid(canonical)))
    return {
        'version': 1,
        'name': canonical,
        'nickname': nickname,
        'actor_uid': uid,
        'created_at': value.get('created_at') or _now(),
        'updated_at': value.get('updated_at') or _now(),
        'cosmetics': 'cosmetics.json',
        'session_key_policy': value.get('session_key_policy', 'udp-per-connection'),
        'notes': value.get('notes', ''),
    }


def _public(record):
    result = dict(record)
    result['actor_uid_hex'] = hex(record['actor_uid'])
    result['state_file'] = str(_cosmetics_file(record['name']))
    return result


def load_account(name):
    """Вернуть запись или None. UID приводится к int, пути — абсолютные."""
    canonical = validate_name(name)
    with _LOCK:
        raw = _load_raw(canonical)
    if raw is None:
        return None
    return _public(_normalize(canonical, raw))


def load_account_at(root, name):
    """Прочитать account.json из явного корня (не меняя глобальный ACCOUNTS_ROOT)."""
    canonical = validate_name(name)
    root = Path(root).expanduser().resolve()
    path = root / canonical / 'account.json'
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise AccountError(f'Повреждён account.json для {canonical}: {error}') from error
    if not isinstance(value, dict):
        raise AccountError(f'account.json для {canonical} должен быть объектом')
    record = _public(_normalize(canonical, value))
    record['state_file'] = str(root / canonical / 'cosmetics.json')
    return record


def list_accounts():
    with _LOCK:
        if not ACCOUNTS_ROOT.is_dir():
            return []
        names = []
        for entry in ACCOUNTS_ROOT.iterdir():
            if entry.is_dir() and (entry / 'account.json').is_file():
                try:
                    names.append(validate_name(entry.name))
                except AccountError:
                    continue
        return [load_account(name) for name in sorted(names)]


def _used_uids(except_name=None):
    used = {}
    for record in list_accounts():
        if except_name is not None and record['name'] == validate_name(except_name):
            continue
        used[record['actor_uid']] = record['name']
    return used


def register_account(name, nickname=None, actor_uid=None, overwrite=False,
                     reset_cosmetics=False):
    """Создать (или обновить) локального пользователя.

    ``overwrite`` меняет account.json, но не стирает cosmetics.json без
    ``reset_cosmetics``. Возвращает публичную запись.
    """
    canonical = validate_name(name)
    if nickname is None:
        nickname = 'Player' if canonical == 'default' else canonical
    nickname = validate_nickname(nickname)
    directory = _path_for(canonical)
    with _LOCK:
        exists = directory.exists()
        if exists and not overwrite:
            raise AccountExists(f'Пользователь {canonical} уже зарегистрирован')
        if actor_uid is None:
            uid = derive_uid(canonical)
            used = _used_uids(except_name=canonical)
            while uid in used:
                uid = (uid + 4) & 0xFFFFFFFFFFFFFFFC
                if uid == 0:
                    raise AccountError('Не удалось подобрать свободный UID')
        else:
            uid = _as_uid(actor_uid)
            used = _used_uids(except_name=canonical)
            if uid in used:
                raise AccountError(f'UID {hex(uid)} уже занят пользователем {used[uid]}')
        directory.mkdir(parents=True, exist_ok=True)
        if not reset_cosmetics and not _cosmetics_file(canonical).exists():
            _atomic_write_json(_cosmetics_file(canonical), default_cosmetics_state())
        elif reset_cosmetics:
            _atomic_write_json(_cosmetics_file(canonical), default_cosmetics_state())
        previous = _load_raw(canonical) if exists else None
        now = _now()
        value = {
            'version': 1,
            'name': canonical,
            'nickname': nickname,
            'actor_uid': hex(uid),
            'created_at': (previous or {}).get('created_at', now),
            'updated_at': now,
            'cosmetics': 'cosmetics.json',
            'session_key_policy': (previous or {}).get('session_key_policy', 'udp-per-connection'),
            'notes': (previous or {}).get('notes', ''),
        }
        _atomic_write_json(_account_file(canonical), value)
        return load_account(canonical)


def update_account(name, nickname=None, actor_uid=None, notes=None):
    canonical = validate_name(name)
    with _LOCK:
        raw = _load_raw(canonical)
        if raw is None:
            raise AccountNotFound(f'Пользователь {canonical} не найден')
        if nickname is not None:
            raw['nickname'] = validate_nickname(nickname)
        if actor_uid is not None:
            uid = _as_uid(actor_uid)
            used = _used_uids(except_name=canonical)
            if uid in used:
                raise AccountError(f'UID {hex(uid)} уже занят пользователем {used[uid]}')
            raw['actor_uid'] = hex(uid)
        if notes is not None:
            if not isinstance(notes, str) or len(notes) > 1024:
                raise AccountError('notes: строка до 1024 символов')
            raw['notes'] = notes
        raw['updated_at'] = _now()
        _atomic_write_json(_account_file(canonical), raw)
        return load_account(canonical)


def delete_account(name, allow_default=False):
    canonical = validate_name(name)
    if canonical == 'default' and not allow_default:
        raise AccountError('Пользователя default нельзя удалить без allow_default')
    directory = _path_for(canonical)
    with _LOCK:
        if not directory.is_dir() or not _account_file(canonical).is_file():
            raise AccountNotFound(f'Пользователь {canonical} не найден')
        shutil.rmtree(directory)
    return canonical


def summary(record):
    if record is None:
        return None
    return {
        'name': record['name'],
        'nickname': record['nickname'],
        'actor_uid': record['actor_uid_hex'],
        'state_file': record['state_file'],
        'created_at': record['created_at'],
    }
