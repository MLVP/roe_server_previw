"""Два одновременных lobby TCP-клиента: только публичные заголовки, без ключей.

Проверяет объединённый сервис лобби (127.0.0.1:8001): базовые ответы
IT/SA/DT отдаёт сам процесс, отдельный сервер на C# больше не нужен.
"""
import argparse
import datetime
import json
from pathlib import Path
import socket
import struct
import time


def header(client, size):
    result = b''
    while len(result) < size:
        part = client.recv(size-len(result))
        if not part:
            raise ValueError('Lobby закрыл соединение до заголовка')
        result += part
    if result[:2] != b'\x55\x0e':
        raise ValueError('Не тот публичный magic lobby')
    return result


def two_clients(port, profile=False):
    request = (bytes.fromhex('550e0000')+struct.pack('>II',12,0) if profile else
               bytes.fromhex('550e0300')+struct.pack('>I',37)+bytes(29))
    size = 12 if profile else 8
    rows = []
    # Первый сокет остаётся открытым, пока второй получает ответ.
    with socket.create_connection(('127.0.0.1',port),timeout=2) as first:
        with socket.create_connection(('127.0.0.1',port),timeout=2) as second:
            for index, client in enumerate((first,second)):
                started = time.monotonic()
                client.sendall(request)
                h = header(client,size)
                total = struct.unpack_from('>I',h,4)[0]
                if profile:
                    total += struct.unpack_from('>I',h,8)[0]
                if (h[2],total) != ((0,2316) if profile else (8,45)):
                    raise ValueError('Неожиданный формат replay-ответа lobby')
                rows.append(dict(client=index,command=h[2],packet_size=total,
                                 seconds=time.monotonic()-started))
                # Payload остаётся в сокете: не читаем key/cipher/profile.
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8001)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Неверный TCP-порт')
    args.output.mkdir(parents=True,exist_ok=True)
    result = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  handshake=two_clients(args.port),initial_profile_headers=two_clients(args.port,True),
                  read_payload=False,read_key=False,two_games_verified=False)
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Два соединения обслужены независимо; заголовки8/45 и0/2316 подтверждены.')


if __name__ == '__main__':main()
