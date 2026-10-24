"""Спаун машин в оригинальных точках карты (0x654B из прототипа сцены)."""
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from vehicle_points_2022 import spawn_vehicles_from_points, _yaw_quaternion

EUROPA_POINTS = ROOT / 'map-data' / 'europa-vehiclepoints.json'


def scene_with_prototype():
    body = bytearray(164)
    struct.pack_into('>Q', body, 0, 0x5040000150001)
    struct.pack_into('>I', body, 8, 102)
    struct.pack_into('>I', body, 16, 21600)
    struct.pack_into('>3i', body, 20, 364860, 532844, 38128)
    scene = [{'trigger': '0x1f49', 'responses': [
        {'command': '0x654b', 'payload_hex': body.hex()}]}]
    return scene, bytes(body)


class VehiclePointSpawnTests(unittest.TestCase):
    def test_adds_requested_count_with_unique_uids_and_source_positions(self):
        scene, prototype = scene_with_prototype()
        result = spawn_vehicles_from_points(scene, EUROPA_POINTS, 5, seed=42)
        rule = result[-1]
        self.assertEqual(rule['trigger'], '0x1f49')
        self.assertTrue(rule['after_selection'])
        self.assertEqual(len(rule['responses']), 5)
        source = {(p['position_cm'][0], p['position_cm'][1], p['position_cm'][2])
                  for p in json.loads(EUROPA_POINTS.read_text(encoding='utf-8'))['points']}
        uids = set()
        for response in rule['responses']:
            body = bytes.fromhex(response['payload_hex'])
            uid = struct.unpack_from('>Q', body)[0]
            self.assertNotIn(uid, uids)
            uids.add(uid)
            self.assertIn(struct.unpack_from('>I', body, 8)[0], (102, 109))
            self.assertEqual(struct.unpack_from('>I', body, 16)[0], 21600)
            self.assertIn(struct.unpack_from('>3i', body, 20), source)
        # исходный ответ сцены не тронут
        self.assertEqual(len(result[0]['responses']), 1)
        original = bytes.fromhex(result[0]['responses'][0]['payload_hex'])
        self.assertEqual(struct.unpack_from('>Q', original)[0],
                         struct.unpack_from('>Q', prototype)[0])

    def test_same_seed_same_vehicles_different_seed_differs(self):
        scene, _ = scene_with_prototype()
        first = spawn_vehicles_from_points(scene, EUROPA_POINTS, 5, seed=42)
        second = spawn_vehicles_from_points(scene, EUROPA_POINTS, 5, seed=42)
        other = spawn_vehicles_from_points(scene, EUROPA_POINTS, 5, seed=7)
        self.assertEqual(first, second)
        self.assertNotEqual(first[-1]['responses'], other[-1]['responses'])

    def test_custom_configuration_pool_is_respected(self):
        scene, _ = scene_with_prototype()
        result = spawn_vehicles_from_points(scene, EUROPA_POINTS, 6, seed=3,
                                            configurations=(103, 104, 105))
        used = {struct.unpack_from('>I', bytes.fromhex(r['payload_hex']), 8)[0]
                for r in result[-1]['responses']}
        self.assertTrue(used.issubset({103, 104, 105}))
        with self.assertRaises(ValueError):
            spawn_vehicles_from_points(scene, EUROPA_POINTS, 3, configurations=())
        with self.assertRaises(ValueError):
            spawn_vehicles_from_points(scene, EUROPA_POINTS, 3, configurations=(0,))

    def test_direction_270_matches_verified_quaternion(self):
        x, y, z, w = _yaw_quaternion(270.0)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(z, -math.sqrt(.5))
        self.assertAlmostEqual(w, math.sqrt(.5))

    def test_rejects_bad_count_empty_points_and_missing_prototype(self):
        scene, _ = scene_with_prototype()
        with self.assertRaises(ValueError):
            spawn_vehicles_from_points(scene, EUROPA_POINTS, 0)
        with self.assertRaises(ValueError):
            spawn_vehicles_from_points(scene, EUROPA_POINTS, 10 ** 6)
        with tempfile.TemporaryDirectory() as folder:
            empty = Path(folder) / 'empty.json'
            empty.write_text(json.dumps({'points': []}), encoding='utf-8')
            with self.assertRaises(ValueError):
                spawn_vehicles_from_points(scene, empty, 3)
        with self.assertRaises(ValueError):
            spawn_vehicles_from_points([{'responses': []}], EUROPA_POINTS, 3)

    def test_europa_mode_wires_vehicle_points(self):
        args = json.loads((ROOT / 'modes' / 'europa' / 'mode.json')
                          .read_text(encoding='utf-8'))['launcher_args']
        value = args[args.index('--vehicle-points') + 1]
        self.assertTrue((ROOT / 'modes' / 'europa' / value).is_file())
        count = int(args[args.index('--vehicle-count') + 1])
        self.assertTrue(1 <= count <= 500)


if __name__ == '__main__':
    unittest.main()
