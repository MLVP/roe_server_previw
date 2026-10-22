"""Явная идентичность локального клиента2022: UID и публичное имя.

UID подставляется в ENTER_GAME_RSP (0x32b). Имя при включённом
profile_nickname — в lobby-профиль 0x2ef (строка с BE64 длиной и NUL).
Смена длины пересобирает AES-кадр и его body length.
"""
import struct
from roe_protocol_2022 import FrameBuffer, dt_plain, encrypt


DEFAULT_PROFILE_NAME = b'BRING_BACK_ROE!!'


class LobbyActorUIDStream:
    def __init__(self, key, uid, profile_nickname=None):
        if type(uid) is not int or not 0 < uid < 2**64:
            raise ValueError('Local actor UID требует ненулевой U64')
        if profile_nickname is not None and not isinstance(profile_nickname, str):
            raise ValueError('profile_nickname должен быть строкой')
        self.key = key
        self.uid = uid
        self.profile_nickname = profile_nickname or None
        self.frames = FrameBuffer()

    def _rebuild(self, frame, plain):
        head = struct.unpack_from('>I', frame, 4)[0]
        cipher = encrypt(plain, self.key)
        header = bytearray(frame[:head])
        struct.pack_into('>I', header, 8, len(cipher))
        return bytes(header) + cipher

    @staticmethod
    def _patch_profile_name(plain, nickname):
        index = plain.find(DEFAULT_PROFILE_NAME)
        if index < 8:
            return None
        length_at = index - 8
        old_length = struct.unpack_from('>Q', plain, length_at)[0]
        if old_length != len(DEFAULT_PROFILE_NAME) + 1:
            return None
        if plain[index + len(DEFAULT_PROFILE_NAME)] != 0:
            return None
        encoded = nickname.encode('utf-8')
        if not 1 <= len(encoded) <= 127:
            raise ValueError('profile nickname: 1..127 байт UTF-8')
        new = encoded + b'\x00'
        return (plain[:length_at] + struct.pack('>Q', len(new)) + new
                + plain[index + len(DEFAULT_PROFILE_NAME) + 1:])

    def feed(self, data):
        output, updates = [], []
        for frame in self.frames.feed(data):
            result = frame
            if frame[2:4] == bytes(2):
                plain = dt_plain(frame, self.key)
                if plain is not None and len(plain) >= 10:
                    code, tag = struct.unpack_from('>HI', plain, 4)
                    if code == tag == 0x32b and len(plain) == 39 and struct.unpack_from('>I', plain, 30)[0] == 0:
                        previous = struct.unpack_from('>Q', plain, 22)[0]
                        patched = bytearray(plain)
                        struct.pack_into('>Q', patched, 22, self.uid)
                        result = self._rebuild(frame, bytes(patched))
                        updates.append(dict(previous_actor_uid=hex(previous),
                                            actor_uid=hex(self.uid)))
                    elif code == tag == 0x2ef and self.profile_nickname:
                        patched = self._patch_profile_name(plain, self.profile_nickname)
                        if patched is not None:
                            result = self._rebuild(frame, patched)
                            updates.append(dict(kind='local_profile_name',
                                                previous_profile_nickname=DEFAULT_PROFILE_NAME.decode('ascii'),
                                                profile_nickname=self.profile_nickname))
            output.append(result)
        return b''.join(output), updates

    def finish(self):
        if self.frames.pending:
            raise ValueError('TCP-поток завершился внутри lobby-кадра')
