"""Патч id карты в payload ENTER_ROOM (profile.base.m644, u32).

Комната комнаты приходит в клиент из room-template; для режима europa туда
нужно положить 16011, иначе клиент и сервер будут считать карту разной.
"""
from __future__ import annotations

import struct

from roe_room_2023 import decode_enter_room_response


def patch_room_map(payload, map_id):
    """Возвращает payload с новым profile.base.m644; структура не меняется."""
    payload = bytes(payload)
    if type(map_id) is not int or not 0 < map_id < 2 ** 32:
        raise ValueError('map id must be a positive U32')
    fields = {field['name']: field for field in decode_enter_room_response(payload)['fields']}
    field = fields.get('profile.base.m644')
    if field is None:
        raise ValueError('no profile.base.m644 in the room payload')
    result = bytearray(payload)
    struct.pack_into('>I', result, field['offset'], map_id)
    decode_enter_room_response(bytes(result))
    return bytes(result)
