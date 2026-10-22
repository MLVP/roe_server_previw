"""Патч публичного имени в ENTER_ROOM_RSP (profile.base.m014).

Поле — строка с BE32 длиной и завершающим NUL. При изменении длины все
последующие поля сдвигаются; decoder снова проверяется после патча.
"""
import argparse
import struct
import sys
from pathlib import Path

from roe_room_2023 import decode_enter_room_response


MAX_NAME_BYTES = 127


def patch_room_nickname(payload, nickname):
    """Вернуть payload с заменой profile.base.m014; пустой ник — без изменений."""
    payload = bytes(payload)
    if nickname is None or nickname == '':
        return payload
    if not isinstance(nickname, str) or '\x00' in nickname:
        raise ValueError('Ник: непустая строка без NUL')
    encoded = nickname.encode('utf-8')
    if not 1 <= len(encoded) <= MAX_NAME_BYTES:
        raise ValueError(f'Ник: 1..{MAX_NAME_BYTES} байт UTF-8')
    fields = {field['name']: field for field in decode_enter_room_response(payload)['fields']}
    field = fields.get('profile.base.m014')
    if field is None:
        raise ValueError('В room payload нет profile.base.m014')
    length_at = field['offset'] - 4
    if length_at < 0:
        raise ValueError('Некорректное смещение длины profile.base.m014')
    old_length = struct.unpack_from('>I', payload, length_at)[0]
    if old_length != field['length'] or old_length < 1:
        raise ValueError('Не совпала длина profile.base.m014')
    if payload[field['offset'] + old_length - 1] != 0:
        raise ValueError('profile.base.m014 не завершён NUL')
    new = encoded + b'\x00'
    result = (payload[:length_at] + struct.pack('>I', len(new)) + new
              + payload[field['offset'] + old_length:])
    decode_enter_room_response(result)
    return result


def main():
    parser = argparse.ArgumentParser(description='Патч ника в room-template')
    parser.add_argument('room', type=Path, help='Исходный ENTER_ROOM_RSP payload')
    parser.add_argument('nickname', help='Новый ник')
    parser.add_argument('--output', type=Path, help='Куда записать; по умолчанию stdout-hex')
    args = parser.parse_args()
    result = patch_room_nickname(args.room.read_bytes(), args.nickname)
    if args.output:
        args.output.write_bytes(result)
        print(f'{args.output}: {len(result)} байт')
    else:
        print(result.hex())
    return 0


if __name__ == '__main__':
    sys.exit(main())
