"""Управление игровой комнатой из логин-сервера.

Логин-сервер (tools/account_service.py) поднимает супервизор комнаты
(server/room_manager.py) и проксирует его API. Комната сама поднимает
лобби, прокси и игровой endpoint, перезапускает стек при простое и ведёт
журнал пакетов.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOM_MANAGER = ROOT / 'server' / 'room_manager.py'


class RoomControl:
    """Запускает супервизор комнаты и проксирует его HTTP API."""

    def __init__(self, root=ROOT, mode='dion', room_id='dion-1', api_port=18080,
                 client=None, profile='default', manager=None):
        self.root = Path(root)
        self.mode = mode
        self.room_id = room_id
        self.api_port = int(api_port)
        self.client = Path(client) if client else None
        self.profile = profile
        self.manager = Path(manager) if manager else DEFAULT_ROOM_MANAGER
        self.lock = threading.RLock()
        self.proc = None
        self.started_at = None
        self.restarts = 0
        self.last_error = None

    # ------------------------------------------------------------------ start
    def command(self):
        command = [sys.executable, '-X', 'utf8', '-B', '-u', str(self.manager),
                   '--mode', self.mode, '--room-id', self.room_id,
                   '--api-port', str(self.api_port), '--profile', self.profile]
        if self.client is not None:
            command.extend(['--client', str(self.client)])
        return command

    def start(self):
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                return False
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'
            self.proc = subprocess.Popen(self.command(), cwd=str(self.root), env=env)
            self.started_at = time.time()
            self.last_error = None
            return True

    def stop(self):
        with self.lock:
            proc = self.proc
            self.proc = None
            if proc is None:
                return
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       check=False)
                    else:
                        proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass

    def watch(self, stop_event=None):
        """Перезапускает супервизор, если он неожиданно завершился."""
        while stop_event is None or not stop_event.is_set():
            time.sleep(2)
            with self.lock:
                proc = self.proc
            if proc is None:
                continue
            if proc.poll() is None:
                continue
            with self.lock:
                if self.proc is not proc:
                    continue
                self.proc = None
                self.last_error = f'room supervisor exited with code {proc.returncode}'
                self.restarts += 1
                self.start()
                print(f'[login] комната перезапущена ({self.restarts}): {self.last_error}', flush=True)

    # ------------------------------------------------------------------- api
    def request(self, path, method='GET', body=None, timeout=30):
        url = f'http://127.0.0.1:{self.api_port}{path}'
        data = body
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            request.add_header('Content-Type', 'application/json; charset=utf-8')
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read().decode('utf-8')
                return response.status, self._decode(payload)
        except urllib.error.HTTPError as error:
            try:
                payload = error.read().decode('utf-8')
            except Exception:
                payload = ''
            return error.code, self._decode(payload) or {'ok': False, 'error': payload}
        except Exception as error:
            return 503, {'ok': False, 'error': f'room API is not reachable: {error}'}

    @staticmethod
    def _decode(payload):
        payload = (payload or '').strip()
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except ValueError:
            return {'ok': False, 'error': 'room API returned a non JSON body', 'body': payload[:400]}

    def status(self):
        with self.lock:
            proc = self.proc
            supervisor = {
                'mode': self.mode,
                'room_id': self.room_id,
                'api_port': self.api_port,
                'api': f'http://127.0.0.1:{self.api_port}/api/status',
                'supervisor_pid': proc.pid if proc is not None and proc.poll() is None else None,
                'started_at': self.started_at,
                'restarts': self.restarts,
                'error': self.last_error,
            }
        code, value = self.request('/api/status', timeout=10)
        supervisor['room'] = value if code == 200 else None
        supervisor['room_error'] = None if code == 200 else value
        return supervisor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', default='dion')
    parser.add_argument('--room-id', default='dion-1')
    parser.add_argument('--api-port', type=int, default=18080)
    parser.add_argument('--client', type=Path)
    parser.add_argument('--profile', default='default')
    parser.add_argument('--status-only', action='store_true')
    args = parser.parse_args(argv)
    control = RoomControl(mode=args.mode, room_id=args.room_id, api_port=args.api_port,
                           client=args.client, profile=args.profile)
    if args.status_only:
        print(json.dumps(control.status(), ensure_ascii=False, indent=2))
        return 0
    control.start()
    stop_event = threading.Event()
    threading.Thread(target=control.watch, args=(stop_event,), daemon=True).start()
    print(f'[login] комната запущена: {control.command()}', flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        control.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
