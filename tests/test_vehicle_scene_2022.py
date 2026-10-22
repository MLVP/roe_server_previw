"""Смена типа машины в сцене: только поле configuration у Jeep102/164."""
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from snowmotor_fixture_2022 import snowmotor_scene, vehicle_scene


def materialize(folder):
    """Тот же разбор @wire/<token>, что делает windows_launch.materialize."""
    wires = json.loads((ROOT / 'config' / 'wire.json').read_text(encoding='utf-8'))
    wire_dir = Path(folder) / 'wire'
    wire_dir.mkdir(parents=True, exist_ok=True)
    for token, record in wires.items():
        (wire_dir / (token + '.bin')).write_bytes(bytes.fromhex(record['hex']))
    scene = json.loads((ROOT / 'config' / 'scene-cycle.json').read_text(encoding='utf-8'))

    def resolve(value):
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, str) and value.startswith('@wire/'):
            return str(wire_dir / (value.split('/')[-1] + '.bin'))
        return value

    return resolve(scene)


def vehicles(scene):
    result = []
    for rule in scene:
        for response in rule.get('responses', []):
            if int(response['command'], 0) != 0x654b:
                continue
            if 'payload_hex' in response:
                body = bytes.fromhex(response['payload_hex'])
            elif 'payload_file' in response:
                body = Path(response['payload_file']).read_bytes()
            else:
                continue
            if len(body) == 164:
                result.append((struct.unpack_from('>Q', body, 0)[0],
                               struct.unpack_from('>I', body, 8)[0],
                               struct.unpack_from('>I', body, 16)[0],
                               struct.unpack_from('>3i', body, 20)))
    return result


class VehicleSceneTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self._temporary.name)
        self.scene_data = materialize(self.folder)

    def tearDown(self):
        self._temporary.cleanup()

    def test_source_scene_keeps_the_jeep(self):
        found = vehicles(self.scene_data)
        self.assertTrue(found)
        for _, configuration, hp, _ in found:
            self.assertEqual(configuration, 102)
            self.assertEqual(hp, 21600)

    def test_vehicle_scene_changes_only_the_configuration(self):
        original = {uid: (configuration, hp, position) for uid, configuration, hp, position in vehicles(self.scene_data)}
        changed = vehicles(vehicle_scene(self.scene_data, 109))
        self.assertTrue(changed)
        for uid, configuration, hp, position in changed:
            self.assertEqual(configuration, 109)
            self.assertEqual(hp, original[uid][1])
            self.assertEqual(position, original[uid][2])

    def test_snowmotor_scene_is_configuration_109(self):
        for _, configuration, _, _ in vehicles(snowmotor_scene(self.scene_data)):
            self.assertEqual(configuration, 109)

    def test_invalid_configuration_is_rejected(self):
        for value in (0, 1000, -1, True, '109'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                vehicle_scene(self.scene_data, value)

    def test_source_scene_is_not_modified_in_place(self):
        scene = self.scene_data
        before = json.dumps(scene, sort_keys=True)
        vehicle_scene(scene, 109)
        self.assertEqual(json.dumps(scene, sort_keys=True), before)


if __name__ == '__main__':
    unittest.main()
