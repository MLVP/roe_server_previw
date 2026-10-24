"""Перебор начального TEA-ключа CK по известной паре шифротекст/ключ.

Кадр `0x01` (CHGSKEY/CK) лобби содержит TEA-зашифрованный session key.
Начальный ключ, которым клиент расшифровывает этот кадр, лежит константой
в клиентском модуле транспорта. Здесь он ищется перебором 16-байтных окон
образца: если TEA-decrypt(private/lobby-ck.bin, окно) даёт
private/candidate-001.key, окно и есть начальный ключ.

Примеры:
  python tools/tea_ck_scan_2022.py --file "F:\\SteamLibrary\\...\\ProtocalHandler_x64.dll"
  python tools/tea_ck_scan_2022.py --file ... --mode be32 --align 1
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
import sys

DELTA = 0x9E3779B9
MASK = 0xFFFFFFFF


def tea_decrypt(data: bytes, key: bytes, mode: str) -> bytes:
    """TEA-decrypt блока 8 байт; режимы: be16/be32/le16/xtea16/xtea32."""
    rounds = 32 if mode.endswith('32') else 16
    little = mode.startswith('le')
    xtea = mode.startswith('xtea')
    words = list(struct.unpack('>4I', key))
    if little:
        words = words[::-1]
    k0, k1, k2, k3 = words
    out = bytearray()
    for index in range(0, len(data), 8):
        v0, v1 = struct.unpack_from('>2I', data, index)
        y, z = v0, v1
        total = (DELTA * rounds) & MASK
        for _ in range(rounds):
            if xtea:
                z = (z - ((((y << 4) ^ (y >> 5)) + y) ^ ((total + k3) & MASK))) & MASK
                total = (total - DELTA) & MASK
                y = (y + ((((z << 4) ^ (z >> 5)) + z) ^ ((total + k0) & MASK))) & MASK
            else:
                z = (z - ((((y << 4) + k2) ^ (y + total) ^ ((y >> 5) + k3)) & MASK)) & MASK
                total = (total - DELTA) & MASK
                y = (y + ((((z << 4) + k0) ^ (z + total) ^ ((z >> 5) + k1)) & MASK)) & MASK
        if little:
            y, z = z, y
        out += struct.pack('>2I', y, z)
    return bytes(out)


def scan(cipher: bytes, plain: bytes, data: bytes, mode: str, align: int) -> list[int]:
    hits = []
    # Первый блок как дешёвый предфильтр, дальше - полная проверка.
    head = plain[:8]
    for offset in range(0, len(data) - 15, align):
        window = data[offset:offset + 16]
        if tea_decrypt(cipher[:8], window, mode) != head:
            continue
        if tea_decrypt(cipher, window, mode) == plain:
            hits.append(offset)
    return hits


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--file', type=Path, action='append', required=True, help='образец для перебора')
    parser.add_argument('--ck', type=Path, default=Path(__file__).resolve().parents[1] / 'private' / 'lobby-ck.bin')
    parser.add_argument('--key-file', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'private' / 'candidate-001.key')
    parser.add_argument('--mode', default='be16', choices=('be16', 'be32', 'le16', 'xtea16', 'xtea32'))
    parser.add_argument('--align', type=int, default=4, help='шаг окна: 1 - каждый байт, 4/8 - по выравниванию')
    args = parser.parse_args(argv)

    cipher = args.ck.read_bytes()
    plain = args.key_file.read_bytes()
    if len(cipher) != 32 or len(plain) != 16:
        print('Нужны 32 байта CK и 16 байт ожидаемого ключа', file=sys.stderr)
        return 2
    for path in args.file:
        if not path.is_file():
            print(f'Нет файла: {path}', file=sys.stderr)
            continue
        data = path.read_bytes()
        print(f'{path.name}: {len(data)} байт, режим {args.mode}, шаг {args.align}', flush=True)
        hits = scan(cipher, plain, data, args.mode, max(1, args.align))
        for offset in hits:
            print(f'  СОВПАДЕНИЕ offset=0x{offset:x} key={data[offset:offset + 16].hex()}')
        if not hits:
            print('  совпадений нет')
    return 0


if __name__ == '__main__':
    sys.exit(main())
