"""Чтение SFC-архивов клиента (SFC/TableBin.sfc, Cache/Data/world/*.sfc).

Формат: магия `SFC` + версия + число записей, затем 12-байтные записи
индекса и область данных. Каждая запись данных начинается с u32 размера
упакованного блоба, дальше идёт LZ4-блоб (для xml/binary) и 4 байта
выравнивания.

Инструмент только читает файлы клиента, ничего в них не меняет.

    .tools\\python\\python.exe tools\\sfc_reader_2022.py --list <file.sfc>
    .tools\\python\\python.exe tools\\sfc_reader_2022.py --extract <file.sfc> <index> <out.bin>
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

try:
    import lz4.block as lz4
except Exception:  # pragma: no cover - lz4 comes with the bundled Python
    lz4 = None

MAGIC = b'SFC\x1a'


def read_index(path):
    """Returns (count, records) where a record is (offset, packed, raw_size)."""
    data = Path(path).read_bytes()
    if data[:4] != MAGIC:
        raise ValueError('not an SFC archive')
    version, count = struct.unpack_from('<II', data, 4)
    offsets = []
    for index in range(count):
        base = 12 + index * 12
        offsets.append(struct.unpack_from('<I', data, base + 8)[0])
    return version, offsets, data


def read_entry(data, offset):
    """Returns the raw (decompressed) bytes of the entry at `offset`."""
    (packed,) = struct.unpack_from('<I', data, offset)
    blob = data[offset + 4:offset + 4 + packed]
    if packed == 0:
        return b''
    try:
        return lz4.decompress(blob, uncompressed_size=0) if lz4 else blob
    except Exception:
        pass
    try:
        return lz4.decompress(blob) if lz4 else blob
    except Exception:
        return blob


def entry_name(blob, limit=200):
    """The XML tables start with <NewObj ObjName="...">; the binary ones with a name."""
    head = blob[:4096]
    marker = b'ObjName="'
    position = head.find(marker)
    if position >= 0:
        end = head.find(b'"', position + len(marker))
        if end > 0:
            return head[position + len(marker):end].decode('utf-8', 'replace')
    return ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--extract', type=int, metavar='INDEX')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--limit', type=int, default=200)
    args = parser.parse_args()
    version, offsets, data = read_index(args.archive)
    print(f'{args.archive}: version {version}, {len(offsets)} entries', file=sys.stderr)
    if args.extract is not None:
        offset = offsets[args.extract]
        blob = read_entry(data, offset)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_bytes(blob)
            print(f'entry {args.extract}: {len(blob)} bytes -> {args.out}', file=sys.stderr)
        else:
            sys.stdout.buffer.write(blob)
        return 0
    for index, offset in enumerate(offsets[:args.limit]):
        blob = read_entry(data, offset)
        name = entry_name(blob)
        kind = 'xml' if blob[:5] == b'<?xml' or b'<NewObj' in blob[:64] else 'binary'
        print(f'{index:6} off={offset:9} size={len(blob):9} {kind:6} {name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
