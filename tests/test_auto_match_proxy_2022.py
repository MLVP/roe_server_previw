"""Auto-match: комната сама начинает тренировочный матч.

Клиент сидит в event center и не отправляет запрос поиска. Прокси после
novice-синхронизации сам отправляет MATCH_FOUND и JOIN_INSTANCE, клиент
входит в комнату без нажатия Play.
"""
import argparse
import asyncio
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'server' / 'directory')]
import heartbeat_probe_2022 as probe
import roe_protocol_2022 as protocol
from roe_team_2022 import server_message
from test_roe_protocol_2022 import KEY


class AutoMatchProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_room_starts_the_match_without_a_client_search(self):
        uid = 42
        enter = bytearray(29)
        struct.pack_into('>Q', enter, 12, uid)
        seed = server_message(0x32b, enter, 100, KEY)

        async def backend(reader, writer):
            writer.write(seed)
            await writer.drain()
            while await reader.read(65536):
                pass
            writer.close()
            await writer.wait_closed()

        async def packet(reader):
            header = await asyncio.wait_for(reader.readexactly(12), 3)
            size = struct.unpack_from('>I', header, 8)[0]
            plain = protocol.dt_plain(header + await asyncio.wait_for(reader.readexactly(size), 3), KEY)
            return struct.unpack_from('>H', plain, 4)[0]

        def team_request():
            body = struct.pack('>IIII', 1, 16010, 1, 0)
            code = 0x701d
            plain = struct.pack('>IIHIIIQI', 7, 30 + len(body), code, 0, 0, 0, uid, code) + body
            cipher = protocol.encrypt(plain, KEY)
            return protocol.MAGIC + b'\0\x04' + struct.pack('>II', 12, len(cipher)) + cipher

        server = await asyncio.start_server(backend, '127.0.0.1', 0)
        stop = asyncio.Event()
        (ROOT / 'captures').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'captures') as temporary:
            folder = Path(temporary)
            key = folder / 'key'
            key.write_bytes(KEY)
            args = argparse.Namespace(
                session_key_file=key, reply=True, team_reply=True, match_reply=True,
                training_reply=True, novice_state=1, match_found_delay=0.2,
                auto_match_seconds=0.5, join_instance_config=ROOT / 'config' / 'join.json',
                port=0, duration=10, output=folder,
                upstream_port=server.sockets[0].getsockname()[1])
            ready = asyncio.get_running_loop().create_future()
            with contextlib.redirect_stdout(io.StringIO()):
                task = asyncio.create_task(probe.serve(args, ready, stop))
                writer = None
                try:
                    address, output = await asyncio.wait_for(ready, 3)
                    reader, writer = await asyncio.open_connection(*address)
                    # The room sends the novice sync and then starts the match itself.
                    codes = [await packet(reader) for _ in range(4)]
                    self.assertIn(0x6e35, codes)
                    self.assertIn(0x6e2d, codes)
                    self.assertIn(0xd77, codes)
                    writer.write(team_request())
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                    writer = None
                    stop.set()
                    await task
                    events = [json.loads(row) for row in (output / 'events.jsonl').read_text().splitlines()]
                    kinds = [row['kind'] for row in events]
                    self.assertIn('auto_match_armed', kinds)
                    forced = [row for row in events if row['kind'] == 'match_found']
                    self.assertTrue(forced)
                    self.assertTrue(forced[0].get('forced'))
                    self.assertIn('join_notification', kinds)
                finally:
                    if writer:
                        writer.close()
                        await writer.wait_closed()
                    stop.set()
                    await task
        server.close()
        await server.wait_closed()


if __name__ == '__main__':
    unittest.main()
