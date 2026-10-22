"""Разбор журнала пакетов лобби: время, направление, код, поля.

Журнал `packets.log` - одна строка на TCP-чанк:
`время<TAB>kind<TAB>направление<TAB>transport<TAB>remote<TAB>hex`.
Кадры в нём зашифрованы сессионным ключом, поэтому код и поля сообщений
извлекаются расшифровкой (ключ `private/candidate-001.key`).

Примеры:
  python tools/packet_log_view_2022.py rooms\\dion-1\\sessions\\<id>\\packets.log
  python tools/packet_log_view_2022.py <log> --tail 40 --direction server_to_client
  python tools/packet_log_view_2022.py <log> --code 0x2f0 --decrypt
  python tools/packet_log_view_2022.py <log> --summary
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from roe_protocol_2022 import FrameBuffer, dt_plain

# Известные коды сообщений лобби 2022.
CODES = {
    0x1f5e: 'client clock ack',
    0x1f5f: 'lobby clock',
    0x1f75: 'heartbeat',
    0x1b59: 'wardrobe state',
    0x2ef: 'lobby profile (name)',
    0x2f0: 'login hello (uid)',
    0x32b: 'ENTER_GAME_RSP (actor uid)',
    0x3783: 'client sync',
    0x3e80: 'wardrobe request',
    0x48a: 'wardrobe',
    0x54cd: 'session data',
    0x54df: 'wardrobe slot',
    0x54e2: 'wardrobe equip',
    0x6e29: 'match request',
    0x6e2a: 'match start',
    0x6e2b: 'match cancel',
    0x6e2c: 'match result',
    0x6e2d: 'MATCH_SYNC (match found)',
    0x6e35: 'MATCH_NOVICE_SYNC',
    0x701d: 'team CREATE_REQ',
    0x701e: 'team CREATE_RSP',
    0x702f: 'team PULL_INFO',
    0x7030: 'team PULL_INFO_RSP',
    0x71ae: 'team member',
    0x736f: 'account data',
    0x73a1: 'wardrobe list',
    0xd75: 'JOIN_INSTANCE_REQ',
    0xd76: 'JOIN_INSTANCE_RSP',
    0xd77: 'JOIN_INSTANCE notify',
    0xd78: 'join ack',
    0x4816: 'weather time',
    0x10d0: 'weather temperature',
    0x654b: 'vehicle spawn',
    0x654c: 'vehicle despawn',
    0x1249: 'friend search',
    0x130b: 'client hello',
    0x130f: 'client hello',
    0x1a37: 'client sync',
    0x1f74: 'client clock',
    0x02dd: 'leave session',
    0x7021: 'matchmaking list',
    0x702b: 'tab switch',
    0x703b: 'tab switch',
    0x7149: 'keepalive',
    0x7211: 'query',
    0x730d: 'bonus code',
    0x7371: 'custom session create',
}

# Поля запроса подбора 0x6e29: (режим, ?, перспектива, тип, карта).
MATCH_MODES = {1: 'Solo', 4: 'Squad'}
MATCH_PERSPECTIVE = {1: 'TPS', 2: 'FPP'}
MATCH_TYPES = {1: 'normal', 2: 'training'}
MATCH_MAPS = {16010: 'Dion', 16011: 'IceNight', 16007: 'Europa', 16021: 'Vera', 16023: 'Training'}


def match_request(body):
    """Разбор запроса подбора: режим, перспектива, тип, карта."""
    if len(body) < 20:
        return None
    values = struct.unpack_from('>5I', body, 0)
    return {
        'mode': MATCH_MODES.get(values[0], values[0]),
        'perspective': MATCH_PERSPECTIVE.get(values[2], values[2]),
        'type': MATCH_TYPES.get(values[3], values[3]),
        'map': MATCH_MAPS.get(values[4], values[4]),
        'map_id': values[4],
    }


def code_name(code):
    return CODES.get(code, '')


def decode_frame(direction, plain):
    """Код и заметные поля сообщения (без жёсткой проверки формата)."""
    row = {'code': None, 'uid': None, 'stamp': None, 'body': 0, 'note': '', 'raw': b''}
    if plain is None or len(plain) < 10:
        return row
    if direction == 'client_to_server':
        # [0:4] префикс транспорта, [4:8] длина, [8:10] код, [22:30] uid,
        # [30:34] тег кода. Строгий вид - только у сообщений после логина.
        row['code'] = struct.unpack_from('>H', plain, 8)[0]
        row['body'] = max(0, len(plain) - 34)
        row['raw'] = plain[34:]
        if row['code'] == 0x2f0 and len(plain) >= 46:
            row['note'] = f'login_id={struct.unpack_from(">I", plain, 42)[0]}'
        elif len(plain) >= 34 and struct.unpack_from('>I', plain, 4)[0] == len(plain) - 4 \
                and struct.unpack_from('>I', plain, 30)[0] == row['code']:
            value = struct.unpack_from('>Q', plain, 22)[0]
            if value >= 2**32:
                row['uid'] = value
            else:
                # У части сообщений (часы, PULL_INFO) здесь метка времени.
                row['note'] = f'stamp=0x{value:x}'
    else:
        # [0:4] метка времени, [4:6] код, [6:10] тег кода.
        row['stamp'] = struct.unpack_from('>I', plain, 0)[0]
        row['code'] = struct.unpack_from('>H', plain, 4)[0]
        row['body'] = max(0, len(plain) - 10)
        if row['code'] == 0x32b and len(plain) >= 30:
            row['note'] = f'actor_uid=0x{struct.unpack_from(">Q", plain, 22)[0]:x}'
    return row


def read_log(path):
    """Возвращает список (время, направление, hex) по строкам журнала."""
    rows = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        parts = line.split('\t')
        if len(parts) < 6:
            continue
        try:
            raw = bytes.fromhex(parts[5])
        except ValueError:
            continue
        rows.append((parts[0], parts[2], raw))
    return rows


def collect(path, key, direction_filter=None, code_filter=None, uid_filter=None):
    """Собирает кадры из чанков и расшифровывает сообщения."""
    buffers = {'client_to_server': FrameBuffer(), 'server_to_client': FrameBuffer()}
    out = []
    for timestamp, direction, raw in read_log(path):
        if direction_filter and direction != direction_filter:
            continue
        try:
            frames = buffers[direction].feed(raw)
        except ValueError:
            continue
        for frame in frames:
            plain = None
            if frame[2] == 0 and key:
                try:
                    plain = dt_plain(frame, key)
                except ValueError:
                    plain = None
            row = decode_frame(direction, plain)
            row.update(timestamp=timestamp, direction=direction, length=len(frame),
                       command=frame[2], flag=frame[3])
            if code_filter is not None and row['code'] != code_filter:
                continue
            if uid_filter is not None and row['uid'] != uid_filter:
                continue
            out.append(row)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('log', type=Path, help='файл packets.log')
    parser.add_argument('--key-file', type=Path, default=ROOT / 'private' / 'candidate-001.key')
    parser.add_argument('--tail', type=int, default=60, help='сколько последних сообщений показать (0 - все)')
    parser.add_argument('--direction', choices=('client_to_server', 'server_to_client'))
    parser.add_argument('--code', type=lambda value: int(value, 0), help='только этот код сообщения')
    parser.add_argument('--uid', type=lambda value: int(value, 0), help='только сообщения с этим uid')
    parser.add_argument('--decrypt', action='store_true', help='показать расшифрованное тело сообщения')
    parser.add_argument('--summary', action='store_true', help='только сводка по кодам')
    parser.add_argument('--json', action='store_true', help='вывод в JSON')
    args = parser.parse_args(argv)
    if not args.log.is_file():
        print(f'Файл не найден: {args.log}', file=sys.stderr)
        return 2
    key = args.key_file.read_bytes() if args.key_file.is_file() else b''
    if len(key) != 16:
        key = b''
    rows = collect(args.log, key, args.direction, args.code, args.uid)
    if args.summary:
        counts = {}
        for row in rows:
            counts[row['code']] = counts.get(row['code'], 0) + 1
        summary = [{'code': (hex(code) if code is not None else None),
                    'name': code_name(code) if code is not None else '',
                    'count': count} for code, count in sorted(counts.items(), key=lambda item: -item[1])]
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            for item in summary:
                print(f"{item['code'] or '-':>8}  {item['count']:>6}  {item['name']}")
        return 0
    if args.tail:
        rows = rows[-args.tail:]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        code = row['code']
        print(f"{row['timestamp']}  {row['direction']:<17}  "
              f"{(hex(code) if code is not None else '-'):>8}  "
              f"{row['length']:>5} B  {code_name(code) if code is not None else ''}")
        if row['uid']:
            print(f"{'':29}  uid=0x{row['uid']:x}")
        if row.get('note'):
            print(f"{'':29}  {row['note']}")
        if row['code'] == 0x6e29:
            request = match_request(row.get('raw', b''))
            if request:
                print(f"{'':29}  режим={request['mode']} перспектива={request['perspective']} "
                      f"тип={request['type']} карта={request['map']} ({request['map_id']})")
        if args.decrypt and row.get('plain'):
            print(f"{'':29}  {row['plain']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
