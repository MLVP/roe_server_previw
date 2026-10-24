"""Разбор захватов pkttext: поток лобби, кадры, коды сообщений.

Файлы в `some_RE_data/pcap/*.pkt.txt` - построчный hex от WPP/протокольного
анализатора: каждая строка один кадр Ethernet, колонки `dir= flow= l4= ... hex=`.
Поток лобби (`flow=lobby`) собирается заново по TCP seq, кадры нарезаются
по заголовку протокола (см. roe_protocol_2022.FrameBuffer).

Примеры:
  python tools/pkttext_lobby_2022.py <capture.pkt.txt>
  python tools/pkttext_lobby_2022.py <capture.pkt.txt> --code 0x7371 --hex
  python tools/pkttext_lobby_2022.py <capture.pkt.txt> --summary
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from packet_log_view_2022 import CODES, decode_frame


def parse_line(line):
    """(dir, flow, l4, payload_bytes, meta) одной строки захвата."""
    if 'dir=' not in line or 'hex=' not in line:
        return None
    fields = {}
    for chunk in line.split()[1:]:
        if '=' in chunk:
            key, value = chunk.split('=', 1)
            fields[key] = value
    hex_part = line.split('hex=', 1)[1].strip()
    try:
        raw = bytes.fromhex(hex_part)
    except ValueError:
        return None
    return dict(direction=fields.get('dir'), flow=fields.get('flow'), l4=fields.get('l4'),
                ts=float(fields.get('t', '0') or 0), n=int(fields.get('n', '0') or 0),
                raw=raw, fields=fields)


def tcp_payload(frame):
    """(seq, ack, payload, src_port, dst_port) Ethernet/IPv4/TCP или None."""
    if len(frame) < 54:
        return None
    if struct.unpack_from('>H', frame, 12)[0] != 0x0800:
        return None
    ip = 14
    version_ihl = frame[ip]
    if version_ihl >> 4 != 4:
        return None
    ihl = (version_ihl & 0xF) * 4
    protocol = frame[ip + 9]
    if protocol != 6:
        return None
    total = struct.unpack_from('>H', frame, ip + 2)[0]
    src = '.'.join(str(value) for value in frame[ip + 12:ip + 16])
    dst = '.'.join(str(value) for value in frame[ip + 16:ip + 20])
    tcp = ip + ihl
    if tcp + 20 > len(frame):
        return None
    src_port, dst_port, seq, ack = struct.unpack_from('>HHII', frame, tcp)
    offset = (frame[tcp + 12] >> 4) * 4
    payload = frame[tcp + offset:ip + total]
    return dict(seq=seq, ack=ack, payload=payload, src_port=src_port, dst_port=dst_port,
                src=src, dst=dst)


def read_streams(path, flow='lobby'):
    """Кадры одного потока, собранные по TCP seq: список кортежей (dir, payload)."""
    chunks = {'c2s': [], 's2c': []}
    meta = {}
    with path.open(encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if f'flow={flow}' not in line:
                continue
            row = parse_line(line)
            if not row or row['l4'] != 'tcp':
                continue
            parsed = tcp_payload(row['raw'])
            if not parsed or not parsed['payload']:
                continue
            direction = 'c2s' if row['direction'] == 'c2s' else 's2c'
            meta.setdefault(direction, (parsed['src'], parsed['src_port'], parsed['dst'], parsed['dst_port']))
            chunks[direction].append((parsed['seq'], row['ts'], parsed['payload']))
    out = []
    for direction, rows in chunks.items():
        rows.sort(key=lambda item: item[0])
        merged = bytearray()
        cursor = None
        for seq, ts, payload in rows:
            if cursor is None:
                cursor = seq
            if seq > cursor:
                # пропущенные байты - граница кадра; продолжаем дальше
                out.append((direction, bytes(merged), ts))
                merged = bytearray()
                cursor = seq
            offset = cursor - seq
            if offset < 0:
                continue
            merged.extend(payload[offset:])
            cursor = seq + len(payload)
        if merged:
            out.append((direction, bytes(merged), rows[-1][1]))
    out.sort(key=lambda item: item[2])
    return out, meta


def cut_frames(payload, prefix=None):
    """Нарезает поток на кадры протокола: [0:4] длина/префикс, [4:8] длина, [8:10] код."""
    frames = []
    index = 0
    while index + 10 <= len(payload):
        declared = struct.unpack_from('>I', payload, index + 4)[0]
        length = None
        if declared == len(payload) - index - 4:
            length = len(payload) - index
        elif declared + 4 <= len(payload) - index:
            length = declared + 4
        if not length or length < 10 or length > 1 << 20:
            break
        frames.append(payload[index:index + length])
        index += length
    return frames, index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('capture', type=Path, help='файл *.pkt.txt')
    parser.add_argument('--flow', default='lobby', help='поток захвата (lobby, http, scene)')
    parser.add_argument('--code', type=lambda value: int(value, 0), help='только этот код')
    parser.add_argument('--summary', action='store_true', help='сводка по кодам')
    parser.add_argument('--hex', dest='show_hex', action='store_true', help='тело сообщения в hex')
    parser.add_argument('--json', action='store_true', help='вывод в JSON')
    args = parser.parse_args(argv)

    streams, meta = read_streams(args.capture, args.flow)
    rows = []
    for direction, blob, ts in streams:
        frames, consumed = cut_frames(blob)
        tail = blob[consumed:]
        for frame in frames:
            row = decode_frame(direction, frame)
            row.update(stream=direction, length=len(frame), ts=ts)
            rows.append(row)
        if tail and tail != b'\x00' * len(tail):
            rows.append({'stream': direction, 'code': None, 'length': len(tail), 'ts': ts,
                         'note': f'unparsed tail {len(tail)}B', 'raw': tail[:64]})
    if args.code is not None:
        rows = [row for row in rows if row.get('code') == args.code]
    if args.summary:
        counts = {}
        for row in rows:
            key = (row.get('stream'), row.get('code'))
            counts[key] = counts.get(key, 0) + 1
        summary = [{'stream': key[0], 'code': hex(key[1]) if key[1] is not None else None,
                    'name': CODES.get(key[1], '') if key[1] is not None else '',
                    'count': count} for key, count in sorted(counts.items(), key=lambda item: -item[1])]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f'streams: {meta}')
    for row in rows:
        code = row.get('code')
        label = CODES.get(code, '') if isinstance(code, int) else row.get('note', '')
        print(f"{row.get('stream','?'):>4}  {(hex(code) if isinstance(code,int) else '-'):>8}  "
              f"{row.get('length','?'):>6} B  {label}")
        if row.get('note') and not isinstance(code, int):
            print(f"      {row['note']}")
        if args.show_hex and row.get('raw'):
            print('      ' + row['raw'].hex())
    return 0


if __name__ == '__main__':
    sys.exit(main())
