"""Проверка игрового тракта лобби без клиента: логин, подбор, отмена.

Скрипт говорит с объединённым сервисом лобби (127.0.0.1:8001) по тому же
протоколу, что и клиент: IT -> SA -> DT (логин) -> запрос подбора (0x6e29)
-> отмена (0x6e2b). Проверяет ответы сервера: 0x6e2a, 0x6e2c и уведомление
о комнате 0xd77.

  python tools/lobby_flow_check_2022.py --uid 611567691
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from roe_protocol_2022 import MAGIC, decrypt, encrypt

KEY = (ROOT / 'private' / 'candidate-001.key').read_bytes()
MAGIC = b'\x55\x0e'


def frame(plain):
    cipher = encrypt(plain, KEY)
    return MAGIC + b'\x00\x04' + struct.pack('>II', 12, len(cipher)) + cipher


def login_hello(uid):
    # Login_Hello_v3: [8:10] код, [32:34] код повторно, [34:38] длина,
    # [42:46] login-id клиента.
    plain = bytearray(59)
    plain[0:4] = b'\x00\x00\x7b\xcd'
    plain[4:8] = (len(plain) - 4).to_bytes(4, 'big')
    plain[8:10] = (0x2f0).to_bytes(2, 'big')
    plain[32:34] = (0x2f0).to_bytes(2, 'big')
    plain[34:38] = (136).to_bytes(4, 'big')
    plain[42:46] = int(uid).to_bytes(4, 'big')
    return frame(bytes(plain))


def message(code, body=b'', actor_uid=0):
    plain = bytearray(34 + len(body))
    plain[0:4] = b'\x00\x00\x58\x27'
    plain[4:8] = (len(plain) - 4).to_bytes(4, 'big')
    plain[8:10] = struct.pack('>H', code)
    plain[22:30] = struct.pack('>Q', actor_uid)
    plain[30:34] = struct.pack('>I', code)
    plain[34:] = body
    return frame(bytes(plain))


def read_frames(sock, timeout=1.0):
    sock.settimeout(timeout)
    data = b''
    frames = []
    while True:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        while len(data) >= 12:
            if data[:2] != MAGIC:
                data = b''
                break
            head, body = struct.unpack_from('>II', data, 4)
            if len(data) < head + body:
                break
            frames.append(data[:head + body])
            data = data[head + body:]
    return frames


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--uid', type=int, required=True, help='uid клиента (login id)')
    parser.add_argument('--actor-uid', type=lambda v: int(v, 0), default=0)
    parser.add_argument('--timeout', type=float, default=8.0)
    args = parser.parse_args(argv)

    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        sock.sendall(bytes.fromhex('550e0300') + (37).to_bytes(4, 'big') + bytes(29))
        sock.sendall(bytes.fromhex('550e0904') + (45).to_bytes(4, 'big') + bytes(37))
        sock.sendall(login_hello(args.uid))
        frames = read_frames(sock, args.timeout)
        codes = []
        for item in frames:
            if len(item) < 12 or item[2] != 0:
                continue
            plain = decrypt(item[12:], KEY)
            if plain is None or len(plain) < 10:
                continue
            codes.append(struct.unpack_from('>H', plain, 4)[0])
        print('welcome codes:', [hex(code) for code in codes])
        if 0x32b not in codes:
            print('FAIL: нет ENTER_GAME_RSP')
            return 2

        # Запрос подбора: (тип, ?, ?, ?, id карты) - 20 байт.
        body = struct.pack('>5I', 1, 1, 1, 1, 0)
        sock.sendall(message(0x6e29, body, args.actor_uid))
        seen = []
        frames = read_frames(sock, args.timeout)
        for item in frames:
            if len(item) < 12 or item[2] != 0:
                continue
            plain = decrypt(item[12:], KEY)
            if plain is None or len(plain) < 10:
                continue
            seen.append(struct.unpack_from('>H', plain, 4)[0])
        print('match answer codes:', [hex(code) for code in seen])
        if 0x6e2a not in seen:
            print('FAIL: нет ответа на запрос подбора (0x6e2a)')
            return 2

        # Уведомление о комнате приходит вместе с MATCH_SYNC.
        deadline = time.time() + args.timeout
        while time.time() < deadline and 0xd77 not in seen:
            frames = read_frames(sock, 1.0)
            for item in frames:
                if len(item) < 12 or item[2] != 0:
                    continue
                plain = decrypt(item[12:], KEY)
                if plain is None or len(plain) < 10:
                    continue
                seen.append(struct.unpack_from('>H', plain, 4)[0])
        print('join notification (0xd77):', 0xd77 in seen)
        if 0xd77 not in seen:
            print('FAIL: нет уведомления о комнате')
            return 2

        # Отмена подбора.
        sock.sendall(message(0x6e2b, b'\x00', args.actor_uid))
        frames = read_frames(sock, args.timeout)
        got = []
        for item in frames:
            if len(item) < 12 or item[2] != 0:
                continue
            plain = decrypt(item[12:], KEY)
            if plain is None or len(plain) < 10:
                continue
            got.append(struct.unpack_from('>H', plain, 4)[0])
        print('cancel answer codes:', [hex(code) for code in got])
        if 0x6e2c not in got:
            print('FAIL: нет ответа на отмену (0x6e2c)')
            return 2
    print('OK: логин, подбор, уведомление о комнате и отмена работают.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
