"""Логин-сервер: прокси к игровой комнате и запуск супервизора комнаты."""
from pathlib import Path
import json
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import account_service
from room_control_2022 import RoomControl


class FakeRoom:
    def __init__(self):
        self.calls = []

    def status(self):
        return {'mode': 'dion', 'room_id': 'unit', 'room': {'ready': True, 'state': 'running'}}

    def request(self, path, method='GET', body=None, timeout=30):
        self.calls.append((path, method))
        if path == '/api/status':
            return 200, {'ok': True, 'state': 'running', 'ready': True}
        return 200, {'ok': True, 'path': path, 'method': method}


class LoginServerTests(unittest.TestCase):
    def setUp(self):
        self.room = FakeRoom()
        account_service.Handler.room = self.room
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), account_service.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        account_service.Handler.room = None

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return response.status, json.loads(response.read().decode('utf-8'))

    def test_health_reports_the_room(self):
        status, value = self.get('/health')
        self.assertEqual(status, 200)
        self.assertTrue(value['ok'])
        self.assertEqual(value['room']['room']['ready'], True)

    def test_room_root_maps_to_the_room_status(self):
        status, value = self.get('/room')
        self.assertEqual(status, 200)
        self.assertTrue(value['ready'])
        self.assertIn(('/api/status', 'GET'), self.room.calls)

    def test_room_paths_are_proxied(self):
        status, value = self.get('/room/api/packets?tail=10')
        self.assertEqual(status, 200)
        self.assertEqual(value['path'], '/api/packets?tail=10')
        self.assertIn(('/api/packets?tail=10', 'GET'), self.room.calls)

    def test_accounts_still_work_next_to_the_room(self):
        status, value = self.get('/accounts')
        self.assertEqual(status, 200)
        self.assertIn('accounts', value)


class RoomControlTests(unittest.TestCase):
    def test_command_points_at_the_room_manager(self):
        control = RoomControl(mode='dion', room_id='unit', api_port=18081, profile='awp')
        command = control.command()
        self.assertIn(str(ROOT / 'server' / 'room_manager.py'), command)
        self.assertIn('--mode', command)
        self.assertIn('dion', command)
        self.assertIn('--room-id', command)
        self.assertIn('unit', command)
        self.assertIn('--api-port', command)
        self.assertIn('18081', command)
        self.assertIn('awp', command)

    def test_status_reports_an_unreachable_room(self):
        control = RoomControl(api_port=1)
        status = control.status()
        self.assertIsNone(status['room'])
        self.assertIsNotNone(status['room_error'])
        self.assertFalse(status['room_error']['ok'])

    def test_start_and_stop_manage_the_supervisor(self):
        control = RoomControl(api_port=1)
        self.assertTrue(control.start())
        with self.lock_guard(control):
            self.assertIsNotNone(control.proc)
        control.stop()
        with self.lock_guard(control):
            self.assertIsNone(control.proc)

    @staticmethod
    def lock_guard(control):
        class Guard:
            def __enter__(self):
                control.lock.acquire()

            def __exit__(self, *args):
                control.lock.release()

        return Guard()


if __name__ == '__main__':
    unittest.main()
