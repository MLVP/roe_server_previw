"""Кастомные комнаты лобби 2022: подтверждённые раскладки 0x736F..0x737D.

Подтверждено (decrypted application plaintext до TCONN, регрессионные фикстуры):

* 0x7370 ROOM_LIST_RSP: u32 page, u32 page_count, u32 room_count, записи комнат.
  Запись: u64 room_id, u64 creator, string name, string password,
  u32 team_type, u32 perspective, u32 zone_id, u32 map_id,
  u32 max_actor, u32 cur_actor, u32 state. Строки: u32 длина (с NUL) + байты;
  пустая строка = 00000001 00. Ответ задерживается на 100 мс: панель
  XVersion RspRoomList отбрасывает ответы, пришедшие до готовности окна.
* 0x7372 CREATE_RSP: только u32 result, без эха идентификатора.
* Сразу после создания шлётся полный 0x737B ENTER_NTF: запись комнаты,
  u32 счётчик участников, записи участников. Локальный актёр входит только
  этим сообщением, НЕ через 0x737C OTHER_ENTER_NTF.
* 0x7373 REMOVE_REQ -> 0x7374 REMOVE_RSP (u32 0) -> 0x737B с room_id=0:
  нулевой id комнаты — ветка очистки модели/интерфейса.
* Выход 0x7377/0x7378/0x737D: форматы QUIT_RSP/QUIT_NTF НЕ подтверждены —
  остаётся лучшее предположение (quit_variants/quit_ntf_variants).

Формат записи участника (u64 uid, u32 len, имя+NUL, 12 слов) — предположение,
байты участника в фикстуру не попали (в пустом снимке счётчик 0).
"""
from __future__ import annotations

import struct

MAP_IDS = {16007: 'Europa', 10120: 'Dion', 16021: 'Vera'}
MODES = {1: 'Solo', 4: 'Squad'}
PERSPECTIVES = {1: 'TPS', 2: 'FPP'}
# Известная зона из фикстуры списка (zone 5 при map 16007); остальные карты
# не подтверждены и несут 0.
ZONE_IDS = {16007: 5}


def _string(body, offset, name):
    if offset + 4 > len(body):
        raise ValueError(f'{name}: обрезан заголовок длины')
    length = struct.unpack_from('>I', body, offset)[0]
    if length > 256 or offset + 4 + length > len(body):
        raise ValueError(f'{name}: недопустимая длина {length}')
    raw = body[offset + 4:offset + 4 + length]
    if length and not raw.endswith(b'\x00'):
        raise ValueError(f'{name}: строка без NUL')
    return raw.rstrip(b'\x00').decode('ascii', 'replace'), offset + 4 + length


def decode_create(body):
    """Тело 0x7371 -> поля запроса; ValueError на непроверенной раскладке."""
    if len(body) < 40:
        raise ValueError('Запрос создания комнаты короче 40 байт')
    first, second = struct.unpack_from('>II', body, 0)
    if first or second:
        raise ValueError('Не совпали нулевые поля запроса')
    uid = struct.unpack_from('>Q', body, 8)[0]
    offset = 16
    name, offset = _string(body, offset, 'имя комнаты')
    password, offset = _string(body, offset, 'пароль')
    if offset + 28 > len(body):
        raise ValueError('В запросе нет хвоста из семи слов')
    mode, perspective, unknown, map_id, max_players, tail_a, tail_b = struct.unpack_from('>7I', body, offset)
    offset += 28
    if offset != len(body):
        raise ValueError('Не согласована длина запроса')
    return {'uid': uid, 'name': name, 'password': password, 'mode': mode,
            'perspective': perspective, 'map_id': map_id, 'max_players': max_players,
            'mode_name': MODES.get(mode, str(mode)),
            'perspective_name': PERSPECTIVES.get(perspective, str(perspective)),
            'map_name': MAP_IDS.get(map_id, 'unknown'),
            'reserved': [unknown, tail_a, tail_b]}


def decode_room_list(body):
    """Тело 0x736F: u32 страница запроса списка комнат."""
    if len(body) != 4:
        raise ValueError('Список комнат: ожидались 4 байта')
    return {'page': struct.unpack_from('>I', body)[0]}


def decode_quit(body):
    """Тело 0x7377: u64 идентификатор покидаемой комнаты."""
    if len(body) != 8:
        raise ValueError('Выход из комнаты: ожидались 8 байт')
    return {'room_id': struct.unpack_from('>Q', body)[0]}


def decode_remove(body):
    """Тело 0x7373 REMOVE_REQ: раскладка запроса не подтверждена.

    Принимаем 1..16 байт и читаем первые 8 как room_id (4-байтовый вариант
    получает нулевую старшую половину), чтобы не ронять обработчик.
    """
    if not 0 < len(body) <= 16:
        raise ValueError('REMOVE_REQ: неожиданная длина %d' % len(body))
    padded = body if len(body) >= 8 else b'\x00' * (8 - len(body)) + body
    return {'room_id': struct.unpack_from('>Q', padded)[0], 'raw_length': len(body)}


def decode_change_pos(body):
    """Тело 0x7381: u32 позиция в списке слотов (наблюдено 0x200, 0x300)."""
    if len(body) != 4:
        raise ValueError('Смена позиции: ожидались 4 байта')
    return {'position': struct.unpack_from('>I', body)[0]}


def encode_create_response(result=0):
    """0x7372 CREATE_RSP: подтверждённая раскладка — только u32 result."""
    return struct.pack('>I', int(result))


def encode_result_response(result=0):
    """Короткий ответ с одним u32 результатом (REMOVE_RSP и др.)."""
    return struct.pack('>I', int(result))


def encode_echo_response(body):
    """Общий ответ запроса-эха: u32 result=0 и тело запроса."""
    return struct.pack('>I', 0) + body


def encode_room_record(room, include_password=False):
    """Запись комнаты для 0x7370/0x737B (подтверждённая раскладка).

    Пароль по умолчанию не отдаётся в чужой список (пустая строка); в полный
    снимок собственной комнаты передаётся фактический.
    """
    name = (room.get('name') or '').encode('ascii', 'replace') + b'\x00'
    password_raw = (room.get('password') or '') if include_password else ''
    password = password_raw.encode('ascii', 'replace') + b'\x00'
    map_id = room.get('map_id', 0)
    return (struct.pack('>QQ', room.get('id', 0), room.get('owner', 0))
            + struct.pack('>I', len(name)) + name
            + struct.pack('>I', len(password)) + password
            + struct.pack('>7I', room.get('team_type', room.get('mode', 1)),
                          room.get('perspective', 1),
                          room.get('zone_id', ZONE_IDS.get(map_id, 0)),
                          map_id,
                          room.get('max_players', 60),
                          room.get('players', 0),
                          room.get('state', 1)))


def encode_room_list_response(rooms=(), page=0, page_count=1):
    """0x7370 ROOM_LIST_RSP: page, page_count, room_count, записи комнат."""
    rooms = list(rooms)
    body = struct.pack('>III', int(page), int(page_count), len(rooms))
    for room in rooms:
        body += encode_room_record(room)
    return body


def _member_record(uid, name):
    """Запись участника (предположение): u64 uid, u32 len, имя с NUL, 12 слов."""
    data = (name or 'Player').encode('ascii', 'replace') + b'\x00'
    return struct.pack('>QI', uid, len(data)) + data + struct.pack('>12I', *([0] * 8 + [1, 0, 1, 0]))


def encode_enter_ntf(room, uid, nickname=''):
    """Полный 0x737B ENTER_NTF: комната + один участник (локальный актёр)."""
    members = max(1, int(room.get('players', 1) or 1))
    record = encode_room_record(dict(room, players=members), include_password=True)
    return record + struct.pack('>I', members) + _member_record(uid, nickname)


def encode_enter_ntf_empty():
    """Проверенный пустой снимок 0x737B: room_id=0 чистит окно комнаты."""
    record = encode_room_record({'id': 0, 'owner': 0, 'name': '', 'password': '',
                                 'team_type': 0, 'perspective': 0, 'zone_id': 0,
                                 'map_id': 0, 'max_players': 0, 'players': 0,
                                 'state': 0},
                                include_password=True)
    return record + struct.pack('>I', 0)


# Выход 0x7377/0x7378/0x737D не подтверждён: клиент повторяет запрос, пока
# не поймёт. (u32 result0 + u64 id1) и (u64 id0 + u32 result1) дают одинаковые
# байты, поэтому ниже только байтово разные кандидаты.
def quit_variants(client_room, our_room):
    # Результат читается как u32 по смещению 0 (значение 1 даёт "Server
    # ErrorCode: 1"), а 4-байтовый ответ клиент повторяет запросом - ему нужен
    # эхо-идентификатор, поэтому 12 байт идут первыми.
    our_room = our_room or client_room
    return (
        struct.pack('>I', 0) + struct.pack('>Q', client_room),  # результат + id клиента
        struct.pack('>I', 0) + struct.pack('>Q', our_room),     # результат + наш id
        struct.pack('>I', 0),                                   # только результат
    )


def quit_ntf_variants(room_id, uid):
    """Варианты 0x737D (выход подтверждён): клиент закрывает окно. Непроверено."""
    return (
        struct.pack('>QQ', room_id, uid),              # id комнаты + uid
        struct.pack('>QQI', room_id, uid, 0),          # + результат
        struct.pack('>Q', room_id),                    # только id комнаты
        struct.pack('>QIQ', 0, 0, uid),                # ноль, ноль, uid
    )
