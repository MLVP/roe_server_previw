"""Замена типа машины в сцене без исходного vehicle RNG.

Меняется только поле configuration (смещение 8) в 164-byte payload сущности
0x654b: UID, точка, HP и остальные байты остаются исходными. Проверенная
пара — Jeep102 (исходная) и SnowMotor109. Любое другое значение подходит
только для 164-byte наземного шаблона: у лодки (203) и вертолёта (6) в
сцене лежат payload другой длины, их нужно собирать отдельно.
"""
import copy
from pathlib import Path
import struct


def vehicle_scene(scene, configuration):
    """Сохраняет UID, точки и движение; меняет config у Jeep102/164."""
    if type(configuration) is not int or not 0 < configuration < 1000:
        raise ValueError('vehicle configuration: 1..999')
    result = copy.deepcopy(scene)
    found = 0
    for rule in result:
        for response in rule.get('responses', []):
            if int(response['command'], 0) != 0x654b:
                continue
            body = bytearray(Path(response['payload_file']).read_bytes() if 'payload_file' in response
                             else bytes.fromhex(response['payload_hex']))
            if len(body) != 164 or struct.unpack_from('>I', body, 8)[0] != 102:
                continue
            if struct.unpack_from('>I', body, 16)[0] != 21600:
                raise ValueError('Требуется проверенная исходная fixture21600HP')
            struct.pack_into('>I', body, 8, configuration)
            response.pop('payload_file', None)
            response['payload_hex'] = body.hex()
            found += 1
    if not found:
        raise ValueError('Нет Jeep102/164 для замены')
    return result


def snowmotor_scene(scene):
    """Сохраняет UID, точки и движение; меняет config только Jeep164."""
    return vehicle_scene(scene, 109)
