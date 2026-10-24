"""Кастомные комнаты: подтверждённые раскладки 0x736F..0x737D по фикстурам.

Фикстуры — decrypted application plaintext до TCONN (регрессионные данные
партнёра): список из трёх строк, CREATE_RSP, REMOVE_RSP, пустой ENTER_NTF.
Заголовок кадра (10 байт) в сравнениях отбрасывается: seq соединения наш.
"""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from roe_custom_room_2022 import (
    decode_create, decode_room_list, decode_quit, decode_remove, decode_change_pos,
    encode_create_response, encode_room_list_response, encode_echo_response,
    encode_result_response, encode_enter_ntf, encode_enter_ntf_empty,
    encode_room_record, quit_variants, quit_ntf_variants,
)

HEADER_BYTES = 10

LIST_FIXTURE = ('011ac166737000007370000000000000000100000001'
                '00000000000000010000000000000000000000055269636f000000000100'
                '00000001000000010000000500003e870000003c0000000100000001')
CREATE_FIXTURE = '011ac05c73720000737200000000'
REMOVE_FIXTURE = '011ac05e73740000737400000000'
ENTER_EMPTY_FIXTURE = ('011ac05e737b0000737b00000000000000000000000000000000000000010000'
                       '0000010000000000000000000000000000000000000000000000000000000000'
                       '00000000')


def payload(hex_text):
    return bytes.fromhex(hex_text)[HEADER_BYTES:]


def request(name='Dave', password='password', mode=1, perspective=2, map_id=16007, max_players=60):
    body = struct.pack('>IIQ', 0, 0, 0x515bb16f306f05)
    for value in (name, password):
        data = value.encode('ascii') + b'\x00'
        body += struct.pack('>I', len(data)) + data
    body += struct.pack('>7I', mode, perspective, 0, map_id, max_players, 0, 0)
    return body


class CustomRoomDecodeTests(unittest.TestCase):
    def test_live_capture_layout_is_decoded(self):
        row = decode_create(request())
        self.assertEqual((row['name'], row['password']), ('Dave', 'password'))
        self.assertEqual((row['uid'], row['map_id']), (0x515bb16f306f05, 16007))
        self.assertEqual((row['mode'], row['perspective'], row['max_players']), (1, 2, 60))
        self.assertEqual((row['mode_name'], row['perspective_name'], row['map_name']),
                         ('Solo', 'FPP', 'Europa'))
        self.assertEqual(row['reserved'], [0, 0, 0])

    def test_squad_vera_and_empty_password(self):
        row = decode_create(request(password='', mode=4, perspective=1, map_id=16021))
        self.assertEqual((row['mode_name'], row['map_name']), ('Squad', 'Vera'))
        self.assertEqual(row['password'], '')

    def test_password_length_zero_means_missing(self):
        body = struct.pack('>IIQ', 0, 0, 7)
        data = b'awp\x00'
        body += struct.pack('>I', len(data)) + data
        body += struct.pack('>I', 0)
        body += struct.pack('>7I', 4, 1, 0, 10120, 60, 0, 0)
        row = decode_create(body)
        self.assertEqual((row['name'], row['password'], row['map_name']), ('awp', '', 'Dion'))

    def test_rejects_truncated_and_foreign_headers(self):
        for body in (request()[:20], b'', struct.pack('>IIQ', 1, 0, 7) + request()[8:],
                     request() + b'\x00'):
            with self.subTest(length=len(body)):
                with self.assertRaises(ValueError):
                    decode_create(body)

    def test_quit_change_pos_and_remove_requests(self):
        self.assertEqual(decode_quit(struct.pack('>Q', 1)), {'room_id': 1})
        with self.assertRaises(ValueError):
            decode_quit(b'\x00' * 7)
        for value in (0x00000200, 0x00000300):
            self.assertEqual(decode_change_pos(struct.pack('>I', value)), {'position': value})
        with self.assertRaises(ValueError):
            decode_change_pos(b'\x00\x00')
        self.assertEqual(decode_remove(struct.pack('>Q', 5)),
                         {'room_id': 5, 'raw_length': 8})
        self.assertEqual(decode_remove(struct.pack('>I', 5)),
                         {'room_id': 5, 'raw_length': 4})
        with self.assertRaises(ValueError):
            decode_remove(b'\x00' * 17)

    def test_room_list_request_is_single_page_word(self):
        self.assertEqual(decode_room_list(struct.pack('>I', 0)), {'page': 0})
        for body in (b'', b'\x00\x00\x00'):
            with self.assertRaises(ValueError):
                decode_room_list(body)


class ConfirmedFixtureTests(unittest.TestCase):
    """Байтовое совпадение с фикстурами партнёра."""

    def test_create_response_is_u32_result_only(self):
        self.assertEqual(encode_create_response(0), payload(CREATE_FIXTURE))
        self.assertEqual(encode_create_response(), payload(CREATE_FIXTURE))
        self.assertEqual(encode_create_response(3), struct.pack('>I', 3))

    def test_remove_response_is_u32_result(self):
        self.assertEqual(encode_result_response(0), payload(REMOVE_FIXTURE))

    def test_room_list_matches_fixture_record(self):
        room = {'id': 1, 'owner': 0, 'name': 'Rico', 'password': '',
                'mode': 1, 'perspective': 1, 'map_id': 16007,
                'max_players': 60, 'players': 1, 'state': 1}
        body = encode_room_list_response([room], page=0, page_count=1)
        self.assertEqual(body, payload(LIST_FIXTURE))
        page, page_count, room_count = struct.unpack_from('>III', body, 0)
        self.assertEqual((page, page_count, room_count), (0, 1, 1))
        # Пустой список: page 0, одна страница, ноль комнат.
        self.assertEqual(encode_room_list_response(), struct.pack('>III', 0, 1, 0))

    def test_empty_enter_ntf_matches_fixture(self):
        self.assertEqual(encode_enter_ntf_empty(), payload(ENTER_EMPTY_FIXTURE))

    def test_full_enter_ntf_carries_room_and_local_actor(self):
        room = {'id': 2, 'owner': 0x515bb16f306f05, 'name': 'Rico', 'password': '',
                'mode': 1, 'perspective': 1, 'map_id': 16007,
                'max_players': 60, 'players': 1, 'state': 1}
        body = encode_enter_ntf(room, room['owner'], 'Rico')
        # Запись комнаты расшифровывается тем же кодом, что и в списке.
        offset = 0
        room_id, creator = struct.unpack_from('>QQ', body, offset)
        offset += 16
        name_len = struct.unpack_from('>I', body, offset)[0]
        offset += 4
        name = body[offset:offset + name_len].rstrip(b'\x00').decode()
        offset += name_len
        password_len = struct.unpack_from('>I', body, offset)[0]
        offset += 4
        offset += password_len
        team_type, perspective, zone_id, map_id, max_actor, cur_actor, state = \
            struct.unpack_from('>7I', body, offset)
        offset += 28
        self.assertEqual((room_id, creator, name), (2, 0x515bb16f306f05, 'Rico'))
        self.assertEqual(password_len, 1)
        self.assertEqual((team_type, perspective, zone_id, map_id),
                         (1, 1, 5, 16007))
        self.assertEqual((max_actor, cur_actor, state), (60, 1, 1))
        members = struct.unpack_from('>I', body, offset)[0]
        self.assertEqual(members, 1)
        offset += 4
        member_uid = struct.unpack_from('>Q', body, offset)[0]
        self.assertEqual(member_uid, room['owner'])

    def test_record_hides_password_in_foreign_list(self):
        room = {'id': 1, 'owner': 7, 'name': 'x', 'password': 'secret',
                'map_id': 16007, 'players': 1}
        hidden = encode_room_record(room)
        self.assertNotIn(b'secret', hidden)
        shown = encode_room_record(room, include_password=True)
        self.assertIn(b'secret', shown)


class CustomRoomFlowTests(unittest.TestCase):
    """Потоки в heartbeat: список, создание, удаление, выход, слоты."""

    def setUp(self):
        import heartbeat_probe_2022 as probe
        self.probe = probe
        probe.CUSTOM_STATE['rooms'].clear()
        probe.CUSTOM_STATE['next_id'] = 1

    def tearDown(self):
        self.probe.CUSTOM_STATE['rooms'].clear()
        self.probe.CUSTOM_STATE['next_id'] = 1

    def test_table_uses_numeric_reply_codes(self):
        probe = self.probe
        samples = {0x736f: struct.pack('>I', 0), 0x7371: request(),
                   0x7373: struct.pack('>Q', 1), 0x7377: struct.pack('>Q', 0),
                   0x7381: struct.pack('>I', 0x200)}
        self.assertEqual(set(probe.CUSTOM_ROOM_MESSAGES), set(samples))
        team = {'room_id': None, 'uid': 7}
        for code, (reply, decoder) in probe.CUSTOM_ROOM_MESSAGES.items():
            self.assertIsInstance(reply, int)
            outputs = probe.custom_room_messages(code, samples[code],
                                                 decoder(samples[code]), team)
            self.assertEqual(outputs[0][0], reply, hex(code))
            for out_code, payload_bytes in outputs:
                self.assertIsInstance(out_code, int)
                self.assertIsInstance(payload_bytes, bytes)

    def test_create_enters_room_without_other_enter(self):
        probe = self.probe
        team = {'room_id': None, 'uid': 7}
        decoder = probe.CUSTOM_ROOM_MESSAGES[0x7371][1]
        outputs = probe.custom_room_messages(0x7371, request(), decoder(request()), team)
        self.assertEqual([code for code, _ in outputs], [0x7372, 0x737b])
        self.assertEqual(outputs[0][1], payload(CREATE_FIXTURE))
        self.assertEqual(team['room_id'], 1)
        # Локальный актёр — только в записи участников ENTER_NTF.
        enter = outputs[1][1]
        members_offset = 16 + 4 + len('Rico\x00') + 4 + 1 + 28
        count = struct.unpack_from('>I', enter, members_offset)[0]
        self.assertEqual(count, 1)
        self.assertNotIn(0x737c, [code for code, _ in outputs])

    def test_list_reports_created_room_with_page_header(self):
        probe = self.probe
        team = {'room_id': None, 'uid': 7}
        create = probe.CUSTOM_ROOM_MESSAGES[0x7371][1]
        probe.custom_room_messages(0x7371, request(), create(request()), team)
        page = probe.CUSTOM_ROOM_MESSAGES[0x736f][1]
        outputs = probe.custom_room_messages(0x736f, struct.pack('>I', 0),
                                             page(struct.pack('>I', 0)), team)
        values = struct.unpack_from('>III', outputs[0][1], 0)
        self.assertEqual(values, (0, 1, 1))
        # Имя комнаты в записи — из запроса создания (Dave).
        self.assertIn(b'Dave', outputs[0][1])

    def test_owner_remove_clears_room_ui(self):
        probe = self.probe
        team = {'room_id': None, 'uid': 7}
        create = probe.CUSTOM_ROOM_MESSAGES[0x7371][1]
        probe.custom_room_messages(0x7371, request(), create(request()), team)
        remove = probe.CUSTOM_ROOM_MESSAGES[0x7373][1]
        outputs = probe.custom_room_messages(0x7373, struct.pack('>Q', 1),
                                             remove(struct.pack('>Q', 1)), team)
        self.assertEqual([code for code, _ in outputs], [0x7374, 0x737b])
        self.assertEqual(outputs[0][1], payload(REMOVE_FIXTURE))
        self.assertEqual(outputs[1][1], payload(ENTER_EMPTY_FIXTURE))
        self.assertEqual(probe.CUSTOM_STATE['rooms'], {})
        self.assertIsNone(team['room_id'])

    def test_quit_chain_stays_best_effort(self):
        probe = self.probe
        team = {'room_id': None, 'uid': 7}
        create = probe.CUSTOM_ROOM_MESSAGES[0x7371][1]
        probe.custom_room_messages(0x7371, request(), create(request()), team)
        decoder = probe.CUSTOM_ROOM_MESSAGES[0x7377][1]
        outputs = probe.custom_room_messages(0x7377, struct.pack('>Q', 1),
                                             decoder(struct.pack('>Q', 1)), team)
        self.assertEqual(outputs[0][0], 0x7378)
        self.assertTrue(any(code == 0x737d for code, _ in outputs))
        # Комната не удаляется преждевременно: остаётся со счётчиком 0.
        self.assertEqual(list(probe.CUSTOM_STATE['rooms']), [1])
        self.assertEqual(probe.CUSTOM_STATE['rooms'][1]['players'], 0)

    def test_unconfirmed_quit_variants_still_unique(self):
        variants = quit_variants(0, 1)
        self.assertEqual(len(variants), 3)
        self.assertEqual({len(item) for item in variants}, {4, 12})
        self.assertEqual(len({item for item in variants}), len(variants))
        self.assertEqual(variants[0], struct.pack('>I', 0) + struct.pack('>Q', 0))
        quits = quit_ntf_variants(3, 0x10)
        self.assertEqual(len({item for item in quits}), len(quits))

    def test_echo_response_keeps_request_tail(self):
        body = struct.pack('>I', 0x200)
        self.assertEqual(encode_echo_response(body), struct.pack('>I', 0) + body)


if __name__ == '__main__':
    unittest.main()
