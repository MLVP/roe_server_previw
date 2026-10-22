"""Минимальный HTTP-сервис регистрации локальных пользователей.

Только stdlib. По умолчанию слушает 127.0.0.1:8099.
Эндпоинты:
  GET  /health
  GET  /accounts
  GET  /accounts/<name>
  POST /register            {"name": "...", "nickname": "...", "actor_uid": "0x..."}
  PATCH /accounts/<name>    {"nickname": "...", "actor_uid": "...", "notes": "..."}
  DELETE /accounts/<name>   (только с --allow-delete)

С опцией --room сервис поднимает игровую комнату (server/room_manager.py)
и проксирует её API:
  GET  /room                 состояние комнаты
  GET  /room/<path>          любой GET-эндпоинт комнаты (/room/api/status)
  POST /room/<path>          любой POST-эндпоинт комнаты
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import sys
import threading
import urllib.parse
from urllib.parse import unquote, urlparse

import accounts_2022 as accounts
from room_control_2022 import RoomControl


MAX_BODY = 64 * 1024
_ACCOUNT_PATH = re.compile(r'/accounts/([^/]+)\Z')


class Server(ThreadingHTTPServer):
    # Windows allows two sockets on one port with SO_REUSEADDR; that would let a
    # second login server silently take over the port, so it is switched off.
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    server_version = 'ROELocalAccounts/1.1'
    allow_delete = False
    room = None

    def log_message(self, format, *args):
        sys.stderr.write('[accounts] ' + (format % args) + '\n')

    def _send(self, status, value):
        body = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error(self, status, message, code='error'):
        self._send(status, {'error': code, 'message': message})

    def _room_proxy(self, path, method='GET', body=None):
        if self.room is None:
            self._error(503, 'Комната не запущена', 'room_disabled')
            return
        target = path[len('/room'):] or '/api/status'
        if not target.startswith('/'):
            target = '/' + target
        status, value = self.room.request(target, method=method, body=body)
        self._send(status, value)

    def _read_json(self):
        length = self.headers.get('Content-Length')
        if length is None:
            raise ValueError('Нужен Content-Length')
        try:
            size = int(length)
        except ValueError as error:
            raise ValueError('Неверный Content-Length') from error
        if not 0 < size <= MAX_BODY:
            raise ValueError('Тело должно быть 1..65536 байт')
        raw = self.rfile.read(size)
        try:
            value = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError('Ожидается JSON UTF-8') from error
        if not isinstance(value, dict):
            raise ValueError('JSON должен быть объектом')
        return value

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/room' or path.startswith('/room/'):
            self._room_proxy(self.path)
            return
        if path == '/health':
            value = {'ok': True, 'accounts_root': str(accounts.ACCOUNTS_ROOT)}
            if self.room is not None:
                value['room'] = self.room.status()
            self._send(200, value)
            return
        if path == '/accounts':
            self._send(200, {'accounts': [accounts.summary(r) for r in accounts.list_accounts()]})
            return
        match = _ACCOUNT_PATH.fullmatch(path)
        if match:
            name = unquote(match.group(1))
            try:
                record = accounts.load_account(name)
            except accounts.AccountError as error:
                self._error(400, str(error), 'invalid_name')
                return
            if record is None:
                self._error(404, f'Пользователь {name} не найден', 'not_found')
            else:
                self._send(200, accounts.summary(record))
            return
        self._error(404, 'Неизвестный путь', 'not_found')

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith('/room/') or path == '/room':
            body = None
            length = self.headers.get('Content-Length')
            if length:
                try:
                    size = int(length)
                except ValueError:
                    size = 0
                if 0 < size <= MAX_BODY:
                    body = self.rfile.read(size)
            self._room_proxy(self.path, method='POST', body=body)
            return
        if path != '/register':
            self._error(404, 'Неизвестный путь', 'not_found')
            return
        try:
            value = self._read_json()
            record = accounts.register_account(
                value.get('name'), nickname=value.get('nickname'),
                actor_uid=value.get('actor_uid'), overwrite=bool(value.get('overwrite', False)),
                reset_cosmetics=bool(value.get('reset_cosmetics', False)))
        except accounts.AccountExists as error:
            self._error(409, str(error), 'exists')
            return
        except accounts.AccountError as error:
            self._error(400, str(error), 'invalid')
            return
        except ValueError as error:
            self._error(400, str(error), 'invalid_body')
            return
        self._send(201, accounts.summary(record))

    def do_PATCH(self):
        match = _ACCOUNT_PATH.fullmatch(urlparse(self.path).path)
        if not match:
            self._error(404, 'Неизвестный путь', 'not_found')
            return
        name = unquote(match.group(1))
        try:
            value = self._read_json()
            record = accounts.update_account(
                name, nickname=value.get('nickname'), actor_uid=value.get('actor_uid'),
                notes=value.get('notes'))
        except accounts.AccountNotFound as error:
            self._error(404, str(error), 'not_found')
            return
        except accounts.AccountError as error:
            self._error(400, str(error), 'invalid')
            return
        except ValueError as error:
            self._error(400, str(error), 'invalid_body')
            return
        self._send(200, accounts.summary(record))

    def do_DELETE(self):
        if not self.allow_delete:
            self._error(403, 'Удаление выключено; запустите serve --allow-delete', 'forbidden')
            return
        match = _ACCOUNT_PATH.fullmatch(urlparse(self.path).path)
        if not match:
            self._error(404, 'Неизвестный путь', 'not_found')
            return
        name = unquote(match.group(1))
        try:
            accounts.delete_account(name)
        except accounts.AccountNotFound as error:
            self._error(404, str(error), 'not_found')
            return
        except accounts.AccountError as error:
            self._error(400, str(error), 'invalid')
            return
        self._send(200, {'deleted': name})


def serve(host='127.0.0.1', port=8099, allow_delete=False, room=None):
    if not 1 <= int(port) <= 65535:
        raise SystemExit('port: 1..65535')
    Handler.allow_delete = bool(allow_delete)
    Handler.room = room
    stop_event = threading.Event()
    if room is not None:
        room.start()
        threading.Thread(target=room.watch, args=(stop_event,), daemon=True).start()
        print(f'Комната запускается: {room.command()}', flush=True)
    if host not in ('127.0.0.1', 'localhost', '::1'):
        print(f'ВНИМАНИЕ: сервис слушает {host}; это тестовый инструмент без авторизации', file=sys.stderr)
    try:
        httpd = Server((host, int(port)), Handler)
    except OSError as error:
        print(f'Порт {int(port)} уже занят: {error}. Остановите прежний экземпляр '
              f'(serve-login.cmd / serve-accounts.cmd) и запустите заново.', flush=True)
        raise SystemExit(2)
    print(f'Сервис аккаунтов: http://{host}:{int(port)}  root={accounts.ACCOUNTS_ROOT}', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        if room is not None:
            room.stop()
        httpd.server_close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8099)
    parser.add_argument('--allow-delete', action='store_true')
    parser.add_argument('--room', action='store_true', help='поднять игровую комнату')
    parser.add_argument('--room-mode', default='dion')
    parser.add_argument('--room-id', default='dion-1')
    parser.add_argument('--room-api-port', type=int, default=18080)
    parser.add_argument('--room-client', help='папка клиента для комнаты')
    parser.add_argument('--room-profile', default='default')
    args = parser.parse_args(argv)
    room = None
    if args.room:
        room = RoomControl(mode=args.room_mode, room_id=args.room_id, api_port=args.room_api_port,
                           client=args.room_client, profile=args.room_profile)
    return serve(args.host, args.port, allow_delete=args.allow_delete, room=room)


if __name__ == '__main__':
    sys.exit(main())
