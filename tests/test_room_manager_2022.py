"""Room supervisor, mode folder, packet log and heightmap tool."""
from pathlib import Path
import json
import os
import struct
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
sys.path.insert(0, str(ROOT / 'server' / 'directory'))
sys.path.insert(0, str(ROOT / 'tools'))
import room_manager
import listener
import heightmap_from_points_2022 as heightmap


class ModeFolderTests(unittest.TestCase):
    def test_dion_mode_is_complete(self):
        mode = room_manager.load_mode('dion')
        self.assertEqual(mode['name'], 'dion')
        self.assertEqual(mode['map']['id'], 16010)
        self.assertEqual(mode['room']['idle_reset_seconds'], 30)
        self.assertFalse(mode['features']['dynamic_events']['enabled'])
        self.assertEqual(mode['features']['dynamic_events']['interval_seconds'], 600)
        self.assertIn('--loot-catalog', mode['launcher_args'])
        self.assertIn('--endless', mode['launcher_args'])

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            room_manager.load_mode('no-such-mode')
        with self.assertRaises(ValueError):
            room_manager.load_mode('../escape')

    def test_spawn_points_are_parsed(self):
        path = ROOT / 'modes' / 'dion' / 'spawn_points.json'
        map_id, points = room_manager.load_spawn_points(path)
        self.assertEqual(map_id, 16010)
        self.assertGreater(len(points), 600)
        for point in points[:5]:
            self.assertEqual(len(point), 4)
            self.assertEqual(len(point['cell']), 2)

    def test_heightmap_metadata_matches_raw(self):
        raw = ROOT / 'modes' / 'dion' / 'heightmap_4096x4096_u16.raw'
        meta = json.loads(raw.with_suffix(raw.suffix + '.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['size'], [4096, 4096])
        self.assertEqual(meta['dtype'], 'uint16')
        self.assertEqual(meta['endian'], 'little')
        self.assertEqual(raw.stat().st_size, 4096 * 4096 * 2)
        self.assertEqual(meta['bytes'], raw.stat().st_size)

    def test_mode_config_overlay_replaces_global_config(self):
        import windows_launch as launcher
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            overlay = base / 'overlay'
            overlay.mkdir()
            document = json.loads((ROOT / 'config' / 'endless.json').read_text(encoding='utf-8'))
            document['hp'] = 999
            (overlay / 'endless.json').write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            configs = launcher.materialize(base, 'glider', cycle_scale=3, endless=True, config_overlay=overlay)
            world = json.loads(configs['world'].read_text(encoding='utf-8'))
            self.assertEqual(world['hp'], 999)

    def test_mode_config_overlay_files_are_valid_json(self):
        overlay = ROOT / 'modes' / 'dion' / 'config'
        self.assertTrue(overlay.is_dir())
        for path in sorted(overlay.glob('*.json')):
            document = json.loads(path.read_text(encoding='utf-8'))
            self.assertIsInstance(document, (dict, list))
            self.assertTrue((ROOT / 'config' / path.name).is_file())

    def test_heightmap_point_loader_accepts_both_shapes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'points.json'
            path.write_text(json.dumps({'map_id': 1, 'points': [[1, 2, 10.0, 20.0, 30.0], [1.0, 2.0, 3.0]]}),
                            encoding='utf-8')
            map_id, points = heightmap.load_points(path)
            self.assertEqual(map_id, 1)
            self.assertEqual(len(points), 2)
            self.assertEqual(points[0]['x'], 10.0)
            self.assertEqual(points[0]['z'], 30.0)
            self.assertEqual(points[1]['x'], 1.0)


class RoomApiTests(unittest.TestCase):
    def setUp(self):
        self.client = Path(tempfile.mkdtemp())
        self.room = room_manager.Room('dion', 'unit', self.client, 'default',
                                      duration=600, idle_reset=30)

    def test_status_reports_mode_and_map(self):
        status = self.room.status()
        self.assertTrue(status['ok'])
        self.assertEqual(status['mode'], 'dion')
        self.assertEqual(status['map']['id'], 16010)
        self.assertEqual(status['state'], 'stopped')
        self.assertEqual(status['idle_reset_seconds'], 30)
        self.assertIn('weather', status)

    def test_aliases_route_to_the_same_handlers(self):
        self.assertEqual(self.room.handle('/status', {})['mode'], 'dion')
        self.assertEqual(self.room.handle('/api/status', {})['mode'], 'dion')
        self.assertTrue(self.room.handle('/api/health', {})['ok'])

    def test_modes_listing(self):
        modes = self.room.handle('/api/modes', {})['modes']
        self.assertIn('dion', [mode['name'] for mode in modes])

    def test_features_expose_the_mode_flags(self):
        features = self.room.handle('/api/features', {})
        self.assertTrue(features['features']['weather_random'])
        self.assertFalse(features['features']['revive'])
        self.assertFalse(features['features']['dynamic_events']['enabled'])
        self.assertTrue(features['loot_catalog'].endswith('loot-pool61.json'))

    def test_heightmap_endpoint(self):
        value = self.room.handle('/api/heightmap', {})
        self.assertEqual(value['bytes'], 4096 * 4096 * 2)
        self.assertTrue(Path(value['path']).is_file())

    def test_spawn_near_filters_by_radius(self):
        value = self.room.handle('/api/spawn/near', {'x': ['365878'], 'y': ['552814'],
                                                     'z': ['260206'], 'radius': ['20000'],
                                                     'limit': ['5']})
        self.assertTrue(value['ok'])
        self.assertLessEqual(len(value['points']), 5)
        for point in value['points']:
            self.assertLessEqual(point['distance_cm'], 20000)

    def test_unknown_endpoint_is_rejected(self):
        with self.assertRaises(ValueError):
            self.room.handle('/api/nope', {})

    def test_commands_need_a_session(self):
        with self.assertRaises(ValueError):
            self.room.add_command({'id': ['x'], 'command': ['0x10']})
        with self.assertRaises(ValueError):
            self.room.commands()

    def test_state_actions_are_validated(self):
        self.assertEqual(self.room._state_action('set_own_health', {'hp': ['100']}),
                         {'action': 'set_own_health', 'hp': 100})
        self.assertEqual(self.room._state_action('give_ammo', {'definition': ['30004'], 'quantity': ['30']}),
                         {'action': 'give_ammo', 'quantity': 30, 'definition': 30004})
        self.assertEqual(self.room._state_action('damage_npc', {'damage': ['50']}),
                         {'action': 'damage_npc', 'damage': 50})
        self.assertEqual(self.room._state_action('{"action":"set_own_health","hp":80}', {}),
                         {'action': 'set_own_health', 'hp': 80})
        with self.assertRaises(ValueError):
            self.room._state_action('nope', {})
        with self.assertRaises(ValueError):
            self.room._state_action('give_ammo', {'definition': ['30004']})

    def test_spawn_request_is_recorded_but_not_applied(self):
        with tempfile.TemporaryDirectory() as folder:
            self.room.session_dir = Path(folder)
            value = self.room.spawn_request({'kind': ['loot'], 'item_id': ['10101'],
                                             'quantity': ['2'], 'radius_cm': ['1500']})
            self.assertTrue(value['ok'])
            self.assertFalse(value['applied'])
            self.assertEqual(value['request']['item_id'], 10101)
            recorded = (Path(folder) / 'spawn-requests.jsonl').read_text(encoding='utf-8').strip()
            self.assertIn('10101', recorded)
            with self.assertRaises(ValueError):
                self.room.spawn_request({'kind': ['loot'], 'item_id': ['999999']})
            with self.assertRaises(ValueError):
                self.room.spawn_request({'kind': ['nope']})


class MapProfileTests(unittest.TestCase):
    def test_europa_mode_targets_the_kill_zone(self):
        mode = room_manager.load_mode('europa')
        self.assertEqual(mode['map']['id'], 16007)
        self.assertEqual(mode['weather']['hours'], [7, 8, 15, 16])
        self.assertEqual(mode['map']['route'], '0:127.0.0.1:18001')

    def test_fdtd_mode_targets_the_night_map(self):
        mode = room_manager.load_mode('fdtd')
        self.assertEqual(mode['map']['id'], 16011)
        self.assertEqual(mode['weather']['hours'], [0])
        self.assertIn('Dusk', mode['title'])

    def test_map_profile_table(self):
        from map_profiles_2022 import allowed_hours, describe, has_local_profile, is_experimental
        self.assertTrue(has_local_profile(16010))
        self.assertTrue(has_local_profile(16011))
        self.assertTrue(has_local_profile(16007))
        self.assertFalse(has_local_profile(10004))
        self.assertFalse(is_experimental(16011))
        self.assertTrue(is_experimental(16007))
        self.assertEqual(allowed_hours(16010), (7, 8, 15, 16))
        self.assertEqual(allowed_hours(16011), (0,))
        self.assertEqual(allowed_hours(16007), (7, 8, 15, 16))
        self.assertIn('IceLandNight', describe(16011))
        self.assertIn('Killzone', describe(16007))

    def test_weather_hour_is_validated_against_the_map(self):
        with tempfile.TemporaryDirectory() as folder:
            room = room_manager.Room('fdtd', 'fdtd-test', Path(folder), 'default')
            with self.assertRaises(ValueError):
                room.set_weather({'hour': ['8'], 'temperature_raw': ['0']})


class LocalSpawnTests(unittest.TestCase):
    def test_europa_spawn_loot_and_vehicles(self):
        mode = room_manager.load_mode('europa')
        point = mode['local_spawn']['point']
        self.assertEqual(point, [364560, 532844, 38128])
        catalog = json.loads((ROOT / 'modes' / 'europa' / 'loot-killzone-64.json').read_text(encoding='utf-8'))
        self.assertEqual(len(catalog['entities']), 64)
        self.assertEqual(catalog['spawn_center'], point)
        for entity in catalog['entities']:
            self.assertEqual(len(entity['position']), 3)
            self.assertLessEqual(abs(entity['position'][0] - point[0]), 400)
            self.assertLessEqual(abs(entity['position'][1] - point[1]), 400)
        scene = json.loads((ROOT / 'modes' / 'europa' / 'config' / 'scene-cycle.json').read_text(encoding='utf-8'))
        vehicles = []
        for rule in scene:
            for response in rule.get('responses', []):
                if int(response['command'], 0) != 0x654b or 'payload_hex' not in response:
                    continue
                body = bytes.fromhex(response['payload_hex'])
                if len(body) != 164:
                    continue
                vehicles.append((struct.unpack_from('>I', body, 8)[0],
                                 struct.unpack_from('>3i', body, 20)))
        self.assertEqual(len(vehicles), 2)
        for configuration, position in vehicles:
            self.assertIn(configuration, (102, 109))
            self.assertEqual(position[1], point[1])
            self.assertEqual(position[2], point[2])


    def test_europa_uses_the_kill_zone_spawn_table(self):
        mode = room_manager.load_mode('europa')
        self.assertEqual(mode['spawn_points'], 'spawn_points_killzone.json')
        table = json.loads((ROOT / 'modes' / 'europa' / 'spawn_points_killzone.json').read_text(encoding='utf-8'))
        self.assertEqual(table['map_id'], 16007)
        self.assertEqual(table['default_cell'], [12, 26])
        self.assertEqual(table['points'], [[12, 26, 364560, 532844, 38128]])
        from winter_selection_2022 import load_spawn_points
        points = load_spawn_points(ROOT / 'modes' / 'europa' / 'spawn_points_killzone.json')
        self.assertEqual(points, ((12, 26, 364560, 532844, 38128),))


class IdleResetTests(unittest.TestCase):
    def test_idle_timeout_creates_a_new_room_session(self):
        real_popen = room_manager.subprocess.Popen
        created = []

        class FakeProc:
            def __init__(self, command, **kwargs):
                self.pid = 1000 + len(created)
                self.returncode = None
                session = Path(command[command.index('--room-run-dir') + 1])
                session.mkdir(parents=True, exist_ok=True)
                (session / 'proxy.log').write_text('{"kind": "ready"}\n', encoding='utf-8')
                (session / 'endpoint.log').write_text('{"kind": "ready"}\n', encoding='utf-8')
                created.append(session)

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 0

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

        room_manager.subprocess.Popen = FakeProc
        original_rooms = room_manager.ROOMS
        try:
            with tempfile.TemporaryDirectory() as folder:
                room_manager.ROOMS = Path(folder) / 'rooms'
                room = room_manager.Room('dion', 'idle-test', Path(folder), 'default',
                                         duration=600, idle_reset=1)
                room.start('test')
                self.assertEqual(len(created), 1)
                first = created[0]
                packet_log = first / 'packets.log'
                packet_log.write_text('2020-01-01T00:00:00+00:00\trecv\tclient_to_server\ttcp\t()\t00\n',
                                      encoding='utf-8')
                stale = time.time() - 30
                os.utime(packet_log, (stale, stale))
                monitor = threading.Thread(target=room.monitor, daemon=True)
                monitor.start()
                deadline = time.time() + 20
                while time.time() < deadline and len(created) < 2:
                    time.sleep(0.2)
                room.shutdown_event.set()
                room.stop(user=True)
                self.assertGreaterEqual(len(created), 2)
                self.assertNotEqual(created[0], created[1])
                self.assertTrue((created[0] / 'packets.log').is_file())
        finally:
            room_manager.subprocess.Popen = real_popen
            room_manager.ROOMS = original_rooms


class PacketLogTests(unittest.TestCase):
    def test_capture_writes_local_and_shared_packet_log(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            shared = base / 'shared' / 'packets.log'
            os.environ['ROE_PACKET_LOG'] = str(shared)
            try:
                capture = listener.Capture(base / 'local')
                capture.record('recv', b'\x55\x0e\x01', transport='udp', remote=('127.0.0.1', 1))
                capture.record('send', b'\x55\x0e\x02', transport='udp', remote=('127.0.0.1', 1))
                capture.close()
            finally:
                os.environ.pop('ROE_PACKET_LOG', None)
            for path in (base / 'local' / 'packets.log', shared):
                self.assertTrue(path.is_file())
                lines = path.read_text(encoding='utf-8').strip().splitlines()
                self.assertEqual(len(lines), 2)
                columns = lines[0].split('\t')
                self.assertEqual(len(columns), 6)
                self.assertEqual(columns[1], 'recv')
                self.assertEqual(columns[2], 'client_to_server')
                self.assertEqual(columns[5], '550e01')
                self.assertIn('+00:00', columns[0])

    def test_capture_events_are_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = listener.Capture(Path(folder) / 'run')
            capture.record('ready', transport='udp')
            capture.close()
            events = (Path(folder) / 'run' / 'events.jsonl').read_text(encoding='utf-8').strip().splitlines()
            self.assertEqual(len(events), 1)
            self.assertEqual(json.loads(events[0])['kind'], 'ready')

    def test_compact_service_keeps_the_hex_packet_log(self):
        import run_service
        with tempfile.TemporaryDirectory() as folder:
            capture = listener.Capture(Path(folder) / 'run')
            original = listener.Capture.record
            listener.Capture.record = run_service.compact
            try:
                capture.record('data', b'\x55\x0e\x01', direction='client_to_server', origin='client')
            finally:
                listener.Capture.record = original
            capture.close()
            line = (Path(folder) / 'run' / 'packets.log').read_text(encoding='utf-8').strip()
            self.assertTrue(line.endswith('550e01'))
            self.assertIn('client_to_server', line)
            event = json.loads((Path(folder) / 'run' / 'events.jsonl').read_text(encoding='utf-8').strip())
            self.assertEqual(event['length'], 3)
            self.assertIn('sha256', event)
            self.assertNotIn('raw', event)


if __name__ == '__main__':
    unittest.main()
