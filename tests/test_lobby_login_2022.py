"""Локальное лобби: базовые ответы и разбор login-id клиента."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'server'/'directory'))
sys.path.insert(0, str(ROOT/'tools'))

import lobby_login_2022 as lobby
from roe_protocol_2022 import encrypt

KEY = bytes(range(16))


def it_packet():
    # IT-пакет клиента: magic, cmd 0x03, флаг, полный размер 37, остальное нули.
    return bytes.fromhex('550e0300') + (37).to_bytes(4, 'big') + bytes(29)


def sa_packet():
    return bytes.fromhex('550e0904') + (45).to_bytes(4, 'big') + bytes(37)


def login_hello(login_id):
    """DT-кадр Login_Hello_v3 (0x2f0) с login-id по смещению 42."""
    plain = bytearray(59)
    plain[0:4] = b'\x00\x00\x7b\xcd'
    plain[4:8] = (len(plain) - 4).to_bytes(4, 'big')
    plain[8:10] = (0x2f0).to_bytes(2, 'big')
    plain[32:36] = (0x2f0).to_bytes(4, 'big')
    plain[42:46] = login_id.to_bytes(4, 'big')
    cipher = encrypt(bytes(plain), KEY)
    return bytes.fromhex('550e0004') + (12).to_bytes(4, 'big') + len(cipher).to_bytes(4, 'big') + cipher


class LobbyLoginTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.ck = Path(self.folder.name)/'lobby-ck.bin'
        self.ck.write_bytes(bytes(range(32)))
        self.session = lobby.LobbyLogin(self.ck, KEY)

    def tearDown(self):
        self.folder.cleanup()

    def test_it_packet_gets_sn_answer(self):
        answer = self.session.feed(it_packet())
        self.assertTrue(answer.startswith(b'\x55\x0e\x08\x00'))
        total = int.from_bytes(answer[4:8], 'big')
        self.assertEqual(total, len(answer))
        self.assertEqual(answer[13:13+32], lobby.IT_DATA)

    def test_sa_packet_gets_id_and_ck(self):
        answer = self.session.feed(sa_packet())
        self.assertTrue(answer.startswith(b'\x55\x0e\x04\x00'))
        self.assertIn(b'\x55\x0e\x01\x00', answer)
        self.assertIn(self.ck.read_bytes(), answer)

    def test_dt_packet_gets_four_welcome_frames_once(self):
        answer = self.session.feed(login_hello(4242))
        expected = sum(12+len(bytes.fromhex(item)) for item in lobby.WELCOME_DT)
        self.assertEqual(len(answer), expected)
        self.assertEqual(self.session.uid, 4242)
        # Второй DT-кадр приветствие не повторяет.
        second = self.session.feed(login_hello(4242))
        self.assertEqual(second, b'')

    def test_uid_is_read_from_login_hello(self):
        self.session.feed(login_hello(1001))
        self.assertEqual(self.session.uid, 1001)

    def test_other_messages_do_not_change_login_id(self):
        plain = bytearray(35)
        plain[4:8] = (31).to_bytes(4, 'big')
        plain[8:10] = (0x1f5e).to_bytes(2, 'big')
        cipher = encrypt(bytes(plain), KEY)
        frame = bytes.fromhex('550e0004') + (12).to_bytes(4, 'big') + len(cipher).to_bytes(4, 'big') + cipher
        self.session.feed(frame)
        self.assertIsNone(self.session.uid)

    def test_split_packet_is_buffered(self):
        packet = login_hello(4242)
        self.assertEqual(self.session.feed(packet[:20]), b'')
        self.assertTrue(self.session.feed(packet[20:]))
        self.assertEqual(self.session.uid, 4242)

    def test_ck_must_be_32_bytes(self):
        broken = Path(self.folder.name)/'broken.bin'
        broken.write_bytes(bytes(31))
        with self.assertRaises(ValueError):
            lobby.LobbyLogin(broken, KEY)


if __name__ == '__main__':
    unittest.main()
