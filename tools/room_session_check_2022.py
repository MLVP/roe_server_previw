"""Manual end-to-end check of the room supervisor.

Starts the supervisor on a free API port, waits until lobby, proxy and game
endpoint report ready, injects one TCP client block into the proxy, verifies
the shared packet log and then waits for the idle reset to create a new room
session. The ports 8001/9001/18001 must be free.

    .tools\\python\\python.exe tools\\room_session_check_2022.py
    .tools\\python\\python.exe tools\\room_session_check_2022.py --api-port 18080

The script never touches the game client and only reads/writes inside the
repository `rooms/` folder.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.tools' / 'python' / 'python.exe'
LOG = ROOT / 'rooms' / 'room-session-check.log'


def log(message):
    line = f'[{time.strftime("%H:%M:%S")}] {message}'
    print(line, flush=True)
    with LOG.open('a', encoding='utf-8') as stream:
        stream.write(line + '\n')


def tcp_free(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def udp_free(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-port', type=int, default=18080)
    parser.add_argument('--mode', default='dion')
    parser.add_argument('--room-id', default='session-check')
    parser.add_argument('--wait-ports', type=int, default=0,
                        help='seconds to wait for 8001/18001 to be released')
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.api_port}'

    def api(path, timeout=15):
        with urllib.request.urlopen(base + path, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))

    deadline = time.time() + max(0, args.wait_ports)
    while time.time() < deadline:
        if tcp_free(8001) and udp_free(18001):
            break
        time.sleep(5)
    if not (tcp_free(8001) and udp_free(18001)):
        log('FAIL: 8001/18001 are busy; stop the other server first')
        return 2

    LOG.parent.mkdir(parents=True, exist_ok=True)
    stream = LOG.open('a', encoding='utf-8')
    process = subprocess.Popen(
        [str(PY), '-X', 'utf8', '-B', '-u', str(ROOT / 'server' / 'room_manager.py'),
         '--mode', args.mode, '--room-id', args.room_id, '--api-port', str(args.api_port)],
        cwd=str(ROOT), stdout=stream, stderr=subprocess.STDOUT)
    try:
        status = None
        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                status = api('/api/status')
            except Exception:
                time.sleep(2)
                continue
            if status.get('ready'):
                break
            time.sleep(2)
        if not status or not status.get('ready'):
            log('FAIL: room never became ready: ' + json.dumps(status))
            return 3
        log(f'ready: session={status["session_id"]} dir={status["session_dir"]}')
        session_dir = Path(status['session_dir'])
        for name in ('session.json', 'launcher.log', 'lobby.log', 'proxy.log', 'endpoint.log'):
            if not (session_dir / name).is_file():
                log(f'FAIL: missing {name}')
                return 4
        log('all service logs present')

        client = socket.create_connection(('127.0.0.1', 8001), timeout=5)
        client.sendall(b'\x01\x02\x03\x04')
        time.sleep(1.5)
        client.close()
        packet_log = session_dir / 'packets.log'
        deadline = time.time() + 20
        while time.time() < deadline and (not packet_log.is_file() or packet_log.stat().st_size == 0):
            time.sleep(0.5)
        if not packet_log.is_file() or packet_log.stat().st_size == 0:
            log('FAIL: packets.log is empty')
            return 5
        first = packet_log.read_text(encoding='utf-8', errors='replace').splitlines()[0]
        log('packet log line: ' + first[:160])
        if '\t' not in first:
            log('FAIL: packet log line has no timestamp columns')
            return 6

        first_session = status['session_id']
        log('waiting for the idle reset')
        deadline = time.time() + 90
        while time.time() < deadline:
            current = api('/api/status')
            if current.get('session_id') != first_session:
                log(f'idle reset done: {first_session} -> {current["session_id"]}')
                break
            time.sleep(2)
        else:
            log('FAIL: idle reset did not happen')
            return 7
        if not (session_dir / 'packets.log').is_file():
            log('FAIL: previous session lost its packet log')
            return 8

        api('/api/stop')
        time.sleep(4)
        stopped = api('/api/status')
        log('stop state: ' + str(stopped.get('state')))
        if stopped.get('state') != 'stopped':
            log('FAIL: room did not stop')
            return 9
        time.sleep(2)
        if not (tcp_free(8001) and tcp_free(9001) and udp_free(18001)):
            log('FAIL: ports still bound after stop')
            return 10
        log('ports released after stop')
        log('SESSION_CHECK_OK')
        return 0
    finally:
        try:
            api('/api/stop')
        except Exception:
            pass
        try:
            if process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            process.wait(timeout=15)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        stream.close()


if __name__ == '__main__':
    sys.exit(main())
