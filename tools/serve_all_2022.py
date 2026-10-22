"""Запуск трёх служб локального сервера: аккаунты, лобби, комнаты.

Службы поднимаются как отдельные процессы с отдельными конфигами:

  * сервер аккаунтов  - `config/services/accounts.json` (HTTP 8099);
  * лобби             - `config/services/lobby.json`     (TCP 8001, HTTP-API 8010);
  * менеджер комнат   - `config/services/room.json`      (HTTP 18080).

Менеджер комнат сам регистрирует готовую комнату в лобби, поэтому лобби
живёт своей жизнью и не перезапускается вместе с комнатой.

  python tools/serve_all_2022.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


class Service:
    def __init__(self, name, command, ready_url=None, log=None):
        self.name = name
        self.command = command
        self.ready_url = ready_url
        self.log_path = log
        self.process = None
        self.handle = None

    def start(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.log_path.open('a', encoding='utf-8')
        self.process = subprocess.Popen(self.command, cwd=ROOT, stdout=self.handle,
                                        stderr=subprocess.STDOUT)
        print(f'{self.name}: pid {self.process.pid}, журнал {self.log_path}', flush=True)
        return self

    def ready(self, timeout=30):
        if not self.ready_url:
            return self.process is not None and self.process.poll() is None
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process is not None and self.process.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(self.ready_url, timeout=2) as response:
                    if response.status == 200:
                        return True
            except Exception:
                time.sleep(0.5)
        return False

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.handle:
            self.handle.close()
            self.handle = None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--accounts-config', type=Path, default=ROOT/'config'/'services'/'accounts.json')
    parser.add_argument('--lobby-config', type=Path, default=ROOT/'config'/'services'/'lobby.json')
    parser.add_argument('--room-config', type=Path, default=ROOT/'config'/'services'/'room.json')
    parser.add_argument('--log-dir', type=Path, default=ROOT/'runtime'/'services')
    parser.add_argument('--no-rooms', action='store_true', help='не поднимать менеджер комнат')
    args = parser.parse_args(argv)

    accounts = read_json(args.accounts_config, {}) or {}
    lobby = read_json(args.lobby_config, {}) or {}
    room = read_json(args.room_config, {}) or {}

    accounts_host = accounts.get('host', '127.0.0.1')
    accounts_port = int(accounts.get('port', 8099))
    lobby_host = lobby.get('host', '127.0.0.1')
    lobby_port = int(lobby.get('port', 8001))
    lobby_api_port = int(lobby.get('api_port', 8010))
    room_api_port = int(room.get('api_port', 18080))

    log_dir = args.log_dir
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')

    services = [
        Service('accounts',
                [PYTHON, '-X', 'utf8', '-B', '-u', str(ROOT/'tools'/'roe_accounts.py'), 'serve',
                 '--host', accounts_host, '--port', str(accounts_port)],
                ready_url=f'http://{accounts_host}:{accounts_port}/health',
                log=log_dir/f'accounts-{stamp}.log'),
        Service('lobby',
                [PYTHON, '-X', 'utf8', '-B', '-u', str(ROOT/'tools'/'lobby_service.py'),
                 '--config', str(args.lobby_config)],
                ready_url=f'http://{lobby_host}:{lobby_api_port}/api/status',
                log=log_dir/f'lobby-{stamp}.log'),
    ]
    if not args.no_rooms:
        services.append(Service(
            'room-manager',
            [PYTHON, '-X', 'utf8', '-B', '-u', str(ROOT/'server'/'room_manager.py'),
             '--config', str(args.room_config)],
            ready_url=f'http://{room.get("api_host", "127.0.0.1")}:{room_api_port}/api/health',
            log=log_dir/f'room-manager-{stamp}.log'))

    stopping = {'flag': False}

    def stop_all(*_):
        stopping['flag'] = True

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    started = []
    try:
        for service in services:
            service.start()
            started.append(service)
            if not service.ready():
                print(f'{service.name}: не готов, смотрите {service.log_path}', flush=True)
                return 1
            print(f'{service.name}: готов', flush=True)
        print(json.dumps({'ok': True,
                          'accounts': f'http://{accounts_host}:{accounts_port}',
                          'lobby_tcp': f'{lobby_host}:{lobby_port}',
                          'lobby_api': f'http://{lobby_host}:{lobby_api_port}/api/status',
                          'room_api': f'http://{room.get("api_host", "127.0.0.1")}:{room_api_port}/api/status'},
                         ensure_ascii=False), flush=True)
        print('Ctrl+C - остановить.', flush=True)
        while not stopping['flag']:
            for service in started:
                if service.process is not None and service.process.poll() is not None:
                    print(f'{service.name}: завершился с кодом {service.process.returncode}', flush=True)
                    return 1
            time.sleep(1)
    finally:
        for service in reversed(started):
            service.stop()
    print('Остановлено.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
