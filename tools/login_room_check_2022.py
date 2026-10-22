"""Первый рабочий тест: логин-сервер поднимает комнату, клиент входит в игру.

Сценарий:
  1. поднимается логин-сервер (tools/roe_accounts.py serve --room);
  2. логин-сервер сам создаёт и запускает игровую комнату
     (server/room_manager.py -> лобби+прокси 8001, game endpoint 18001);
  3. по желанию запускается настоящий клиент 2022 (Europa_Client.exe);
  4. тест ждёт, пока endpoint подтвердит вход в комнату
     (событие enter_room_response), и печатает вердикт.

    .tools\\python\\python.exe tools\\login_room_check_2022.py --launch-client

Без --launch-client проверяется только запуск: комната поднимается, её API
отвечает, в пакетном логе видны данные клиента.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.tools' / 'python' / 'python.exe'
LOG = ROOT / 'rooms' / 'login-room-check.log'


def log(message):
    line = f'[{time.strftime("%H:%M:%S")}] {message}'
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as stream:
        stream.write(line + '\n')


def port_free(port, kind='tcp'):
    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_STREAM if kind == 'tcp' else socket.SOCK_DGRAM)
    try:
        sock.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def http_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def wait_login(base, deadline):
    while time.time() < deadline:
        try:
            return http_json(base + '/health', timeout=5)
        except Exception:
            time.sleep(1)
    return None


def wait_room_ready(base, deadline):
    while time.time() < deadline:
        try:
            health = http_json(base + '/health', timeout=5)
        except Exception:
            time.sleep(1)
            continue
        room = (health or {}).get('room') or {}
        state = room.get('room') or {}
        if state.get('ready'):
            return health
        time.sleep(1)
    return None


def find_client(explicit):
    if explicit:
        path = Path(explicit)
        return path if path.is_dir() else None
    marker = ROOT / '.tools' / 'client-path.txt'
    if marker.is_file():
        value = marker.read_text(encoding='utf-8-sig').strip()
        if value and Path(value).is_dir():
            return Path(value)
    return None


def launch_client(client):
    executable = client / 'Europa_Client.exe'
    if not executable.is_file():
        raise SystemExit(f'нет клиента: {executable}')
    process = subprocess.Popen(
        [str(executable), '-language=en', '-garena', '-uid=1', '-server=127.0.0.1:8001'],
        cwd=str(client))
    log(f'клиент запущен: pid={process.pid} {client}')
    return process


def session_log(session_dir, name):
    path = Path(session_dir) / name
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--login-port', type=int, default=8099)
    parser.add_argument('--room-api-port', type=int, default=18080)
    parser.add_argument('--mode', default='dion')
    parser.add_argument('--room-id', default='login-check')
    parser.add_argument('--profile', default='default')
    parser.add_argument('--client', help='папка клиента 2022')
    parser.add_argument('--launch-client', action='store_true',
                        help='запустить настоящий клиент и дождаться входа в комнату')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()

    for port, kind in ((args.login_port, 'tcp'), (8001, 'tcp'), (18001, 'udp')):
        if not port_free(port, kind):
            log(f'FAIL: порт {port} занят; остановите старый сервер')
            return 2

    client = find_client(args.client)
    if args.launch_client and client is None:
        log('FAIL: не найдена папка клиента (укажите --client)')
        return 2

    base = f'http://127.0.0.1:{args.login_port}'
    command = [str(PY), '-B', '-u', str(ROOT / 'tools' / 'roe_accounts.py'), 'serve',
               '--room', '--port', str(args.login_port),
               '--room-api-port', str(args.room_api_port), '--room-mode', args.mode,
               '--room-id', args.room_id, '--room-profile', args.profile]
    if client is not None:
        command.extend(['--room-client', str(client)])
    log('логин-сервер: ' + ' '.join(command))
    server = subprocess.Popen(command, cwd=str(ROOT))
    game = None
    try:
        deadline = time.time() + 90
        health = wait_login(base, deadline)
        if health is None:
            log('FAIL: логин-сервер не отвечает')
            return 3
        log(f'логин-сервер отвечает: {base}/health')
        room = (health.get('room') or {}).get('room') or {}
        log(f'комната: state={room.get("state")} ready={room.get("ready")} '
            f'session={room.get("session_id")}')
        deadline = time.time() + args.timeout
        health = wait_room_ready(base, deadline)
        if health is None:
            log('FAIL: комната не поднялась')
            return 4
        room = (health.get('room') or {}).get('room') or {}
        session_dir = room.get('session_dir')
        log(f'комната готова: session={room.get("session_id")} dir={session_dir}')

        if args.launch_client:
            game = launch_client(client)

        entered = False
        deadline = time.time() + (args.timeout if args.launch_client else 20)
        while time.time() < deadline:
            text = session_log(session_dir, 'endpoint.log')
            if 'enter_room_response' in text:
                entered = True
                break
            time.sleep(1)
        proxy_log = session_log(session_dir, 'proxy.log')
        packets = session_log(session_dir, 'packets.log')
        log('логин-сервер -> комната: join=%s' % ('join_notification' in proxy_log))
        log('пакетов в packets.log: %d' % (0 if not packets else len(packets.splitlines())))
        if entered:
            log('PASS: клиент вошёл в комнату (enter_room_response в endpoint.log)')
            return 0
        if not args.launch_client:
            log('PASS: запуск проверен (комната поднялась, API отвечает)')
            return 0
        log('FAIL: вход в комнату не подтверждён; последние строки endpoint.log:')
        for line in session_log(session_dir, 'endpoint.log').splitlines()[-5:]:
            log('   ' + line[:200])
        return 5
    finally:
        if game is not None and game.poll() is None:
            game.terminate()
            try:
                game.wait(timeout=10)
            except Exception:
                game.kill()
        if server.poll() is None:
            subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            try:
                server.wait(timeout=15)
            except Exception:
                server.kill()


if __name__ == '__main__':
    sys.exit(main())
