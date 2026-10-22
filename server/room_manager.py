"""Single-room supervisor and small real-time HTTP API for ROE_local_test_1.

The existing fork already implements the lobby, proxy and game endpoint.  This
module keeps that stack unchanged, starts it as one room, records every packet
in the room session folder and exposes simple GET endpoints for live commands.

It deliberately starts with one lobby and one room.  The room id and mode are
configuration, so a future multi-room manager can use the same interface.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import struct
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODES = ROOT / 'modes'
ROOMS = ROOT / 'rooms'
SAFE_NAME = re.compile(r'[A-Za-z0-9_.-]{1,64}')
SAFE_ID = re.compile(r'[A-Za-z0-9_-]{1,64}')

sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'server' / 'directory'))
try:
    from windows_launch import WindowsJob
except Exception:  # pragma: no cover - the job helper is optional
    WindowsJob = None
try:
    from map_profiles_2022 import allowed_hours, describe, has_local_profile
except Exception:  # pragma: no cover - the map profile table is optional
    allowed_hours = describe = has_local_profile = None


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def iso_now():
    return utc_now().isoformat()


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def read_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def tail_lines(path: Path, count: int):
    if count < 1:
        count = 1
    if count > 2000:
        count = 2000
    if not path.is_file():
        return []
    size = path.stat().st_size
    window = min(size, max(4096, count * 512))
    with path.open('rb') as stream:
        stream.seek(size - window)
        data = stream.read()
    lines = data.decode('utf-8', errors='replace').splitlines()
    return lines[-count:]


def parse_int(value, name):
    try:
        result = int(str(value), 0)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be an integer')
    return result


def parse_int_list(value, name):
    if value in (None, ''):
        return []
    if isinstance(value, list):
        value = ','.join(str(item) for item in value)
    try:
        return [int(str(item).strip(), 0) for item in str(value).split(',') if str(item).strip()]
    except ValueError:
        raise ValueError(f'{name} must be comma-separated integers')


def load_mode(name: str):
    if not SAFE_NAME.fullmatch(name or ''):
        raise ValueError('invalid mode name')
    path = MODES / name / 'mode.json'
    if not path.is_file():
        raise ValueError(f'mode not found: {name}')
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f'mode file must contain an object: {path}')
    data.setdefault('name', name)
    data.setdefault('launcher_args', [])
    data.setdefault('map', {})
    data.setdefault('features', {})
    data.setdefault('room', {})
    data.setdefault('weather', {})
    return data


def list_modes():
    result = []
    if not MODES.is_dir():
        return result
    for folder in sorted(MODES.iterdir()):
        if not folder.is_dir() or not (folder / 'mode.json').is_file():
            continue
        try:
            mode = load_mode(folder.name)
        except Exception as error:
            result.append({'name': folder.name, 'error': str(error)})
            continue
        result.append({
            'name': mode.get('name', folder.name),
            'title': mode.get('title', folder.name),
            'description': mode.get('description', ''),
            'enabled': mode.get('enabled', True),
            'map': mode.get('map', {}),
        })
    return result


def default_client():
    override = os.environ.get('ROE_CLIENT')
    if override:
        return Path(override).expanduser()
    path = ROOT / '.tools' / 'client-path.txt'
    if path.is_file():
        value = path.read_text(encoding='utf-8-sig').strip()
        if value:
            return Path(value)
    return None


def load_spawn_points(path: Path):
    data = read_json(path)
    if data is None:
        raise ValueError(f'spawn point file not found: {path}')
    rows = data.get('points') if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError('spawn point file must contain a points array')
    points = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        if len(row) >= 5:
            cell = [row[0], row[1]]
            x, y, z = float(row[2]), float(row[3]), float(row[4])
        elif len(row) >= 3:
            cell = None
            x, y, z = float(row[0]), float(row[1]), float(row[2])
        else:
            continue
        points.append({'cell': cell, 'x': x, 'y': y, 'z': z})
    return data.get('map_id') if isinstance(data, dict) else None, points


class Room:
    def __init__(self, mode_name, room_id, client, profile, duration=None,
                 idle_reset=None, auto_restart=True, instance_id=1, lobby_api=None):
        if not SAFE_NAME.fullmatch(mode_name or ''):
            raise ValueError('invalid mode name')
        if not SAFE_NAME.fullmatch(room_id or ''):
            raise ValueError('invalid room id')
        self.mode_name = mode_name
        self.room_id = room_id
        self.client = Path(client).expanduser() if client else None
        self.profile = profile
        self.lobby_api = lobby_api
        self.mode = load_mode(mode_name)
        self.duration = int(duration if duration is not None else self.mode.get('duration_seconds', 86400))
        self.idle_reset_seconds = int(idle_reset if idle_reset is not None else self.mode.get('room', {}).get('idle_reset_seconds', 30))
        if self.duration < 60:
            raise ValueError('duration must be at least 60 seconds')
        if self.idle_reset_seconds < 0:
            raise ValueError('idle reset must be zero or positive')
        self.auto_restart = bool(auto_restart)
        self.instance_id = int(instance_id)
        self.registered_map_id = None
        self.epoch = 0
        self.lock = threading.RLock()
        self.restart_lock = threading.Lock()
        self.shutdown_event = threading.Event()
        self.proc = None
        self.log_handle = None
        self.job = None
        self.state = 'stopped'
        self.ready = False
        self.error = None
        self.session_dir = None
        self.session_id = None
        self.packet_log = None
        self.live_commands = None
        self.started_at = None
        self.last_activity = None
        self.ever_active = False
        self.user_stopped = True
        self.weather_override = None
        self.vehicle_configuration = None
        self.session_weather = self._weather()
        self._dynamic_last = 0.0
        self._last_status = None

    def _weather(self):
        if self.weather_override is not None:
            return dict(self.weather_override)
        weather = self.mode.get('weather') or {}
        hours = weather.get('hours') or [weather.get('start_hour', 8)]
        temperatures = weather.get('temperatures') or [weather.get('temperature_raw', 500)]
        if weather.get('randomize'):
            return {'hour': random.choice(hours), 'temperature_raw': random.choice(temperatures)}
        return {
            'hour': int(weather.get('start_hour', 8)),
            'temperature_raw': int(weather.get('temperature_raw', 500)),
        }

    def _resolve_launcher_args(self):
        result = []
        source = list(self.mode.get('launcher_args') or [])
        path_options = {'--loot-catalog', '--key-file'}
        index = 0
        while index < len(source):
            value = str(source[index])
            if value in path_options and index + 1 < len(source):
                candidate = Path(source[index + 1]).expanduser()
                if not candidate.is_absolute():
                    root_candidate = ROOT / candidate
                    mode_candidate = MODES / self.mode_name / candidate
                    candidate = root_candidate if root_candidate.exists() else mode_candidate
                result.append(value)
                result.append(str(candidate))
                index += 2
                continue
            result.append(value)
            index += 1
        return result

    def _session_metadata(self, reason):
        return {
            'room_id': self.room_id,
            'mode': self.mode_name,
            'mode_title': self.mode.get('title', self.mode_name),
            'map': self.mode.get('map', {}),
            'instance_id': self.instance_id,
            'weather': self.weather_override if self.weather_override is not None else self._weather(),
            'profile': self.profile,
            'client': str(self.client) if self.client else None,
            'duration_seconds': self.duration,
            'idle_reset_seconds': self.idle_reset_seconds,
            'reason': reason,
            'started_at': iso_now(),
        }

    def _start_locked(self, reason, watch=True):
        if self.proc is not None and self.proc.poll() is None:
            return
        if self.client is None:
            raise ValueError('client path is not set; use --client or .tools/client-path.txt')
        if not self.client.is_dir():
            raise ValueError(f'client directory does not exist: {self.client}')
        self.mode = load_mode(self.mode_name)
        session_id = utc_now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
        session = ROOMS / self.room_id / 'sessions' / session_id
        session.mkdir(parents=True, exist_ok=False)
        metadata = self._session_metadata(reason)
        metadata['session_id'] = session_id
        atomic_write(session / 'session.json', json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')

        env = os.environ.copy()
        env['ROE_ROOM_ID'] = self.room_id
        env['ROE_SESSION_ID'] = session_id
        env['ROE_PACKET_LOG'] = str(session / 'packets.log')
        env['PYTHONUTF8'] = '1'

        weather = metadata['weather']
        map_id = int(self.mode.get('map', {}).get('id', 16010))
        command = [
            sys.executable, '-X', 'utf8', '-B', '-u',
            str(ROOT / 'tools' / 'windows_launch.py'),
            '--client', str(self.client),
            '--profile', self.profile,
            '--services-only',
            '--room-run-dir', str(session),
            '--duration', str(self.duration),
            '--map-id', str(map_id),
            '--instance-id', str(self.instance_id),
            '--start-hour', str(int(weather['hour'])),
            '--temperature-raw', str(int(weather['temperature_raw'])),
            '--live-control',
        ]
        command.extend(self._resolve_launcher_args())
        spawn_points = self._spawn_points_path()
        if spawn_points is not None and Path(spawn_points).is_file():
            command.extend(['--spawn-points', str(spawn_points)])
        local_spawn = self.mode.get('local_spawn') or {}
        point = local_spawn.get('point')
        if isinstance(point, (list, tuple)) and len(point) == 3:
            command.extend(['--spawn-origin', ','.join(str(int(value)) for value in point)])
        if self.vehicle_configuration is not None:
            command.extend(['--vehicle-configuration', str(self.vehicle_configuration)])
        overlay = self._config_overlay_path()
        if overlay is not None:
            command.extend(['--config-overlay', str(overlay)])
        metadata['launcher_command'] = command
        atomic_write(session / 'session.json', json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')

        self.log_handle = (session / 'launcher.log').open('w', encoding='utf-8', buffering=1)
        creationflags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) if os.name == 'nt' else 0
        try:
            self.proc = subprocess.Popen(
                command, cwd=ROOT, env=env,
                stdout=self.log_handle, stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        except Exception:
            self.log_handle.close()
            self.log_handle = None
            self.proc = None
            raise
        self.session_dir = session
        self.session_id = session_id
        self.session_weather = dict(metadata['weather'])
        if WindowsJob is not None:
            try:
                self.job = WindowsJob()
                self.job.add(self.proc)
            except Exception:
                self.job = None
        self.packet_log = session / 'packets.log'
        self.live_commands = session / 'live-commands.json'
        self.started_at = time.time()
        self.last_activity = None
        self.ever_active = False
        self.state = 'starting'
        self.ready = False
        self.error = None
        self.user_stopped = False
        self._last_status = None
        metadata['pid'] = self.proc.pid
        atomic_write(session / 'session.json', json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        if watch:
            threading.Thread(target=self._ready_watch, args=(self.proc, session), daemon=True).start()

    def _ready_watch(self, proc, session):
        if self._wait_ready(proc, session, 75):
            return
        with self.lock:
            if self.proc is not proc:
                return
            self.ready = False
            self.state = 'failed'
            self.error = 'launcher did not become ready; see ' + str(session / 'launcher.log')
        self.stop(user=False)
        with self.lock:
            if self.error:
                self.state = 'failed'

    def _wait_ready(self, proc, session, timeout, epoch=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.shutdown_event.is_set():
                return False
            if epoch is not None and self.epoch != epoch:
                return False
            if self.proc is not proc:
                return False
            if proc.poll() is not None:
                return False
            lobby = session / 'proxy.log'
            endpoint = session / 'endpoint.log'
            pointer = self._lobby_pointer() or {}
            if pointer.get('events_log'):
                # Журнал событий лобби живёт в lobby/<запуск>/, а не в папке сессии.
                lobby = Path(pointer['events_log'])
            lobby_text = lobby.read_text(encoding='utf-8', errors='replace') if lobby.is_file() else ''
            endpoint_text = endpoint.read_text(encoding='utf-8', errors='replace') if endpoint.is_file() else ''
            if '"kind": "ready"' in lobby_text and '"kind": "ready"' in endpoint_text:
                with self.lock:
                    if self.proc is proc:
                        self.ready = True
                        self.state = 'running'
                        self.error = None
                self.register_room_with_lobby(session)
                return True
            time.sleep(0.25)
        return False

    def register_room_with_lobby(self, session):
        """Регистрирует готовую комнату в лобби: адрес, карта, instance id."""
        base = getattr(self, 'lobby_api', None)
        if not base:
            return None
        join = read_json(Path(session) / 'join.json')
        if not isinstance(join, dict):
            return None
        route = str((join.get('response') or {}).get('route') or '')
        if not route:
            return None
        map_id = int(self.mode.get('map', {}).get('id', 16010))
        query = urlencode({'route': route, 'map_id': map_id,
                           'instance_id': self.instance_id, 'mode': self.mode_name})
        url = f'{base.rstrip("/")}/api/room?{query}'
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as error:
            with self.lock:
                self.error = f'Не удалось зарегистрировать комнату в лобби: {error}'
            return None
        self.registered_map_id = map_id
        return payload.get('room')

    def unregister_room_with_lobby(self):
        """Сообщает лобби, что комната остановлена (по зарегистрированной карте)."""
        base = getattr(self, 'lobby_api', None)
        map_id = self.registered_map_id
        self.registered_map_id = None
        if not base or map_id is None:
            return
        query = urlencode({'map_id': map_id})
        try:
            with urllib.request.urlopen(f'{base.rstrip("/")}/api/room/unregister?{query}', timeout=8):
                return
        except Exception:
            return

    def _stop_locked(self):
        proc = self.proc
        self.proc = None
        self.ready = False
        self.state = 'stopped'
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   check=False)
                else:
                    proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        if self.log_handle is not None:
            try:
                self.log_handle.close()
            except OSError:
                pass
            self.log_handle = None
        if self.job is not None:
            try:
                self.job.close()
            except Exception:
                pass
            self.job = None
        self.unregister_room_with_lobby()

    def start(self, reason='manual'):
        with self.lock:
            self._start_locked(reason)
            return self.status()

    def stop(self, user=True):
        with self.lock:
            self.epoch += 1
            if user:
                self.user_stopped = True
            self._stop_locked()
            return self.status()

    def restart(self, reason='reset'):
        with self.restart_lock:
            epoch = self.epoch
            with self.lock:
                self._stop_locked()
            for attempt in range(3):
                if self.epoch != epoch:
                    break
                time.sleep(1.5 if attempt == 0 else 3.0)
                with self.lock:
                    if self.proc is not None or self.epoch != epoch:
                        break
                    self._start_locked(reason, watch=False)
                    proc = self.proc
                    session = self.session_dir
                if self._wait_ready(proc, session, 45, epoch):
                    break
                with self.lock:
                    if self.proc is proc:
                        self._stop_locked()
                        self.state = 'failed'
                        self.error = (f'restart attempt {attempt + 1} failed; see '
                                      + str(session / 'launcher.log'))
            return self.status()

    def restart_async(self, reason='reset'):
        threading.Thread(target=self.restart, args=(reason,), daemon=True).start()
        return {'ok': True, 'restart': 'in-progress', 'reason': reason, 'status': self.status()}

    def _lobby_pointer(self):
        """Указатель на текущий запуск лобби (лobby/current.json)."""
        path = ROOT / 'lobby' / 'current.json'
        if not path.is_file():
            return None
        try:
            data = read_json(path)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _activity_mtime(self):
        """Свежесть трафика: и комнаты (UDP), и лобби (TCP)."""
        stamps = []
        for path in (self.packet_log, self._lobby_packet_log()):
            if path is not None and Path(path).is_file():
                try:
                    stamps.append(Path(path).stat().st_mtime)
                except OSError:
                    pass
        return max(stamps) if stamps else None

    def _lobby_packet_log(self):
        pointer = self._lobby_pointer()
        if not pointer:
            return None
        value = pointer.get('packets_log')
        return Path(value) if value else None

    def monitor(self):
        while not self.shutdown_event.is_set():
            action = None
            with self.lock:
                if self.proc is not None:
                    returncode = self.proc.poll()
                    if returncode is not None:
                        self.proc = None
                        self.ready = False
                        self.state = 'exited'
                        self.error = f'launcher exited with code {returncode}'
                        if self.log_handle is not None:
                            try:
                                self.log_handle.close()
                            except OSError:
                                pass
                            self.log_handle = None
                        uptime = time.time() - self.started_at if self.started_at else 0.0
                        if self.auto_restart and not self.user_stopped and uptime >= 15:
                            action = 'process-exit'
                        elif not self.user_stopped:
                            self.state = 'failed'
                            self.error = f'launcher exited after {uptime:.1f}s; automatic restart suppressed'
                    else:
                        # Активность - по трафику комнаты (UDP) и лобби (TCP):
                        # пока игрок в меню лобби, UDP-трафика ещё нет.
                        stamp = self._activity_mtime()
                        if stamp is not None:
                            self.ever_active = True
                            self.last_activity = stamp
                        # Отсчёт простоя - от последнего трафика или от старта
                        # комнаты, иначе новая комната сразу считается простаивающей.
                        baseline = max(stamp or 0, self.started_at or 0)
                        if self.idle_reset_seconds and time.time() - baseline >= self.idle_reset_seconds:
                            action = 'idle'
            if action:
                try:
                    self.restart(action)
                except Exception as error:
                    with self.lock:
                        self.state = 'failed'
                        self.error = f'{action} restart failed: {error}'
            self._dynamic_tick()
            self.shutdown_event.wait(1.0)

    def _dynamic_tick(self):
        features = self.mode.get('features') or {}
        dynamic = features.get('dynamic_events') or {}
        if not dynamic.get('enabled'):
            return
        interval = max(10, int(dynamic.get('interval_seconds', 600)))
        if time.time() - self._dynamic_last < interval:
            return
        self._dynamic_last = time.time()
        with self.lock:
            session = self.session_dir
            points_file = self._spawn_points_path()
        if session is None or points_file is None:
            return
        try:
            map_id, points = load_spawn_points(points_file)
        except Exception:
            return
        if not points:
            return
        point = random.choice(points)
        entry = {
            'timestamp': iso_now(),
            'kind': 'dynamic_event_request',
            'map_id': map_id,
            'point': point,
            'radius_cm': int(dynamic.get('radius_cm', 50000)),
            'loot': bool(dynamic.get('loot', True)),
            'vehicles': bool(dynamic.get('vehicles', True)),
            'implemented': False,
            'note': 'request recorded; protocol spawn injection is not implemented yet',
        }
        with (session / 'dynamic-events.jsonl').open('a', encoding='utf-8', buffering=1) as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def _spawn_points_path(self):
        value = self.mode.get('spawn_points')
        if not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            mode_path = MODES / self.mode_name / path
            path = mode_path if mode_path.exists() else ROOT / path
        return path

    def _config_overlay_path(self):
        value = self.mode.get('config')
        path = Path(value) if value else Path('config')
        if not path.is_absolute():
            path = MODES / self.mode_name / path
        return path if path.is_dir() else None

    def status(self):
        with self.lock:
            idle = None
            if self.last_activity is not None:
                idle = max(0.0, time.time() - self.last_activity)
            commands = []
            if self.live_commands is not None and self.live_commands.is_file():
                try:
                    value = read_json(self.live_commands, [])
                    if isinstance(value, list):
                        commands = value
                except Exception:
                    pass
            pointer = self._lobby_pointer() or {}
            return {
                'ok': True,
                'room_id': self.room_id,
                'mode': self.mode_name,
                'mode_title': self.mode.get('title', self.mode_name),
                'profile': self.profile,
                'map': self.mode.get('map', {}),
                'instance_id': self.instance_id,
                'state': self.state,
                'ready': self.ready,
                'pid': self.proc.pid if self.proc is not None else None,
                'session_id': self.session_id,
                'session_dir': str(self.session_dir) if self.session_dir else None,
                'packets_log': str(self.packet_log) if self.packet_log else None,
                'live_commands': str(self.live_commands) if self.live_commands else None,
                'lobby': {
                    'run': pointer.get('run'),
                    'directory': pointer.get('directory'),
                    'packets_log': pointer.get('packets_log'),
                    'events_log': pointer.get('events_log'),
                    'status': pointer.get('status'),
                    'service_log': pointer.get('service_log'),
                },
                'started_at': dt.datetime.fromtimestamp(self.started_at, dt.timezone.utc).isoformat() if self.started_at else None,
                'last_activity': dt.datetime.fromtimestamp(self.last_activity, dt.timezone.utc).isoformat() if self.last_activity else None,
                'idle_seconds': idle,
                'idle_reset_seconds': self.idle_reset_seconds,
                'ever_active': self.ever_active,
                'weather': self.weather_override if self.weather_override is not None else (
                    self.session_weather if self.session_weather is not None else self._weather()),
                'vehicle_configuration': self.vehicle_configuration,
                'command_count': len(commands),
                'error': self.error,
                'duration_seconds': self.duration,
            }

    def _require_session(self):
        if self.session_dir is None:
            raise ValueError('room has no active session; call /api/start first')
        return self.session_dir

    STATE_ACTIONS = {
        'set_own_health': ('hp',),
        'give_ammo': ('quantity', 'definition'),
        'damage_npc': ('damage',),
    }

    def _state_action(self, action, query):
        if action.startswith('{'):
            value = json.loads(action)
            if not isinstance(value, dict):
                raise ValueError('action json must be an object')
            return value
        parameters = {}
        for key in ('hp', 'quantity', 'definition', 'damage'):
            raw = (query.get(key) or [''])[0].strip()
            if raw:
                parameters[key] = parse_int(raw, key)
        allowed = self.STATE_ACTIONS.get(action)
        if allowed is None:
            raise ValueError('unknown state action: ' + action
                             + ' (known: ' + ', '.join(sorted(self.STATE_ACTIONS)) + ')')
        missing = [key for key in allowed if key not in parameters]
        if missing:
            raise ValueError('action ' + action + ' needs ' + ', '.join(missing))
        return dict(action=action, **parameters)

    def add_command(self, query):
        session = self._require_session()
        path = session / 'live-commands.json'
        source = read_json(path, [])
        if not isinstance(source, list):
            raise ValueError('live-commands.json is not an array')
        if len(source) >= 128:
            raise ValueError('live command limit is 128')
        name = (query.get('id') or query.get('name') or [''])[0].strip()
        if not SAFE_ID.fullmatch(name):
            raise ValueError('id must match [A-Za-z0-9_-]{1,64}')
        if any(isinstance(row, dict) and row.get('id') == name for row in source):
            raise ValueError(f'command id already exists: {name}')
        row = {'id': name}
        action = (query.get('action') or query.get('action_json') or [''])[0].strip()
        code = (query.get('command') or query.get('opcode') or query.get('code') or [''])[0].strip()
        if action:
            row['action'] = self._state_action(action, query)
        elif code:
            row['command'] = parse_int(code, 'command')
        else:
            raise ValueError('command or action is required')
        payload_hex = (query.get('payload_hex') or [''])[0].strip()
        if payload_hex:
            row['payload_hex'] = payload_hex
        elif 'payload_hex' not in row:
            row['payload_hex'] = ''
        recipient = (query.get('recipient_actor_uid') or [''])[0].strip()
        if recipient:
            row['recipient_actor_uid'] = parse_int(recipient, 'recipient_actor_uid')
        for key in ('actor_uid_offsets', 'clock_tick_offsets', 'clock_seconds_offsets'):
            values = parse_int_list((query.get(key) or [''])[0], key)
            if values:
                row[key] = values
        source.append(row)
        atomic_write(path, json.dumps(source, ensure_ascii=False, indent=2) + '\n')
        return {'ok': True, 'command': row, 'path': str(path), 'count': len(source)}

    def clear_commands(self):
        session = self._require_session()
        path = session / 'live-commands.json'
        atomic_write(path, '[]\n')
        return {'ok': True, 'path': str(path), 'count': 0}

    def commands(self):
        session = self._require_session()
        path = session / 'live-commands.json'
        return {'ok': True, 'path': str(path), 'commands': read_json(path, [])}

    def packets(self, query):
        session = self._require_session()
        count = parse_int((query.get('tail') or ['100'])[0], 'tail')
        path = session / 'packets.log'
        return {'ok': True, 'path': str(path), 'count': count, 'lines': tail_lines(path, count)}

    def logs(self, query):
        session = self._require_session()
        name = (query.get('name') or ['launcher'])[0].strip()
        if name not in {'launcher', 'lobby', 'proxy', 'endpoint', 'build', 'client'}:
            raise ValueError('unknown log name')
        if name in ('lobby', 'proxy'):
            # Лобби - постоянная служба, его журналы лежат в lobby/<запуск>/.
            pointer = self._lobby_pointer()
            if pointer and pointer.get('service_log'):
                path = Path(pointer['service_log'])
                count = parse_int((query.get('tail') or ['100'])[0], 'tail')
                return {'ok': True, 'path': str(path), 'name': name, 'count': count,
                        'lines': tail_lines(path, count)}
        path = session / f'{name}.log'
        count = parse_int((query.get('tail') or ['100'])[0], 'tail')
        return {'ok': True, 'path': str(path), 'name': name, 'count': count, 'lines': tail_lines(path, count)}

    def heightmap(self):
        value = self.mode.get('heightmap')
        if not value:
            raise ValueError('mode has no heightmap file')
        path = Path(value)
        if not path.is_absolute():
            mode_path = MODES / self.mode_name / path
            path = mode_path if mode_path.exists() else ROOT / path
        if not path.is_file():
            raise ValueError(f'heightmap not found: {path}')
        return {'ok': True, 'path': str(path), 'bytes': path.stat().st_size,
                'size': 4096, 'dtype': 'uint16', 'endian': 'little',
                'metadata': str(path.with_suffix(path.suffix + '.json'))}

    def features(self):
        features = dict(self.mode.get('features') or {})
        resolved_args = self._resolve_launcher_args()
        loot_catalog = None
        for index, value in enumerate(resolved_args):
            if value == '--loot-catalog' and index + 1 < len(resolved_args):
                loot_catalog = resolved_args[index + 1]
                break
        return {
            'ok': True,
            'mode': self.mode_name,
            'map': self.mode.get('map', {}),
            'features': features,
            'loot_catalog': loot_catalog,
            'heightmap': self.mode.get('heightmap'),
            'spawn_points': str(self._spawn_points_path()) if self._spawn_points_path() else None,
            'packet_log': str(self.packet_log) if self.packet_log else None,
            'dynamic_events': features.get('dynamic_events', {}),
            'notes': [
                'dynamic_events only records requests; live loot/vehicle spawn is not implemented',
                'revive is disabled; existing medical fixtures are available',
                'tcp key rotation requires inverse CHGSKEY/TEA and is not implemented',
            ],
        }

    def _catalog_items(self):
        resolved_args = self._resolve_launcher_args()
        path = None
        for index, value in enumerate(resolved_args):
            if value == '--loot-catalog' and index + 1 < len(resolved_args):
                path = Path(resolved_args[index + 1])
                break
        if path is None or not path.is_file():
            return set()
        data = read_json(path, {})
        items = set()
        for entity in (data.get('entities') or []):
            if isinstance(entity, dict) and 'item_id' in entity:
                items.add(int(entity['item_id']))
        for item in (data.get('items') or []):
            if isinstance(item, dict) and 'item_id' in item:
                items.add(int(item['item_id']))
        return items

    def spawn_request(self, query):
        session = self._require_session()
        kind = (query.get('kind') or ['loot'])[0].strip()
        if kind not in ('loot', 'crate', 'vehicle'):
            raise ValueError('kind must be loot, crate or vehicle')
        request = {'timestamp': iso_now(), 'kind': kind, 'applied': False,
                   'note': 'request recorded; live spawn injection needs a confirmed MsgID payload'}
        if kind in ('loot', 'crate'):
            item_id = parse_int((query.get('item_id') or ['0'])[0], 'item_id')
            quantity = parse_int((query.get('quantity') or ['1'])[0], 'quantity')
            known = self._catalog_items()
            if known and item_id not in known:
                raise ValueError(f'item_id {item_id} is not in the mode loot catalog')
            request.update(item_id=item_id, quantity=quantity)
        elif (query.get('item_id') or query.get('configuration') or [''])[0].strip():
            request['configuration'] = parse_int(
                (query.get('item_id') or query.get('configuration'))[0], 'configuration')
        request['radius_cm'] = float((query.get('radius_cm') or ['2000'])[0])
        for key in ('x', 'y', 'z'):
            raw = (query.get(key) or [''])[0].strip()
            if raw:
                request[key] = float(raw)
        request.setdefault('position_source', 'player')
        with (session / 'spawn-requests.jsonl').open('a', encoding='utf-8', buffering=1) as stream:
            stream.write(json.dumps(request, ensure_ascii=False) + '\n')
        return {'ok': True, 'applied': False, 'path': str(session / 'spawn-requests.jsonl'),
                'request': request}

    def spawn_near(self, query):
        path = self._spawn_points_path()
        if path is None:
            raise ValueError('mode has no spawn_points file')
        map_id, points = load_spawn_points(path)
        x = float((query.get('x') or ['365878'])[0])
        y = float((query.get('y') or ['552814'])[0])
        z = float((query.get('z') or ['260206'])[0])
        radius = float((query.get('radius') or ['50000'])[0])
        limit = max(1, min(200, parse_int((query.get('limit') or ['20'])[0], 'limit')))
        nearest = []
        for point in points:
            dx = point['x'] - x
            dy = point['y'] - y
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= radius:
                item = dict(point)
                item['distance_cm'] = round(distance, 1)
                item['height_delta'] = round(point['z'] - z, 1)
                nearest.append(item)
        nearest.sort(key=lambda item: item['distance_cm'])
        return {'ok': True, 'path': str(path), 'map_id': map_id, 'origin': [x, y, z],
                'radius_cm': radius, 'count': len(nearest), 'points': nearest[:limit]}

    def set_weather(self, query):
        hour = parse_int((query.get('hour') or [str(self._weather()['hour'])])[0], 'hour')
        temperature = parse_int((query.get('temperature_raw') or query.get('temperature') or [str(self._weather()['temperature_raw'])])[0], 'temperature_raw')
        if not 0 <= hour <= 23:
            raise ValueError('hour must be 0..23')
        if allowed_hours is not None:
            map_id = int(self.mode.get('map', {}).get('id', 16010))
            if hour not in allowed_hours(map_id):
                raise ValueError('hour must be one of ' + str(allowed_hours(map_id))
                                 + ' for map ' + str(map_id))
        if not -5000 <= temperature <= 500:
            raise ValueError('temperature_raw must be -5000..500')
        with self.lock:
            self.weather_override = {'hour': hour, 'temperature_raw': temperature}
        live = 'applies to the next room start'
        try:
            seconds = int(time.time())
            self.push_live([
                {'id': f'weather-time-{seconds}', 'command': 0x4816,
                 'payload_hex': struct.pack('>II', hour, seconds).hex()},
                {'id': f'weather-temp-{seconds}', 'command': 0x10d0,
                 'payload_hex': struct.pack('>Ii', 5, temperature).hex()},
            ])
            live = 'pushed to the client in the running match'
        except Exception as error:
            live = f'next room start only ({error})'
        return {'ok': True, 'weather': self.weather_override, 'live': live, 'status': self.status()}

    def push_live(self, rows):
        """Adds commands to the live-commands file of the running session."""
        path = self.live_commands
        if path is None or not path.is_file():
            raise ValueError('no active session; start the room first')
        source = read_json(path, [])
        if not isinstance(source, list):
            source = []
        if len(source) + len(rows) > 128:
            raise ValueError('live command limit is 128')
        source.extend(rows)
        atomic_write(path, json.dumps(source, ensure_ascii=False, indent=2) + '\n')
        return rows

    def _vehicle_swap_rows(self, configuration):
        scene = read_json(Path(self.session_dir) / 'scene-cycle.json', [])
        for rule in scene or []:
            for response in rule.get('responses', []):
                if int(response['command'], 0) != 0x654b:
                    continue
                body = bytes.fromhex(response.get('payload_hex', ''))
                if len(body) != 164 or struct.unpack_from('>I', body, 8)[0] != 102:
                    continue
                replacement = bytearray(body)
                struct.pack_into('>I', replacement, 8, configuration)
                stamp = int(time.time())
                return [
                    {'id': f'vehicle-off-{stamp}', 'command': 0x654c, 'payload_hex': body[:8].hex()},
                    {'id': f'vehicle-on-{stamp}', 'command': 0x654b, 'payload_hex': bytes(replacement).hex()},
                ]
        raise ValueError('the current scene has no 164-byte ground vehicle to replace')

    def set_vehicle(self, query):
        raw = (query.get('configuration') or query.get('config') or [''])[0].strip()
        with self.lock:
            if not raw:
                self.vehicle_configuration = None
            else:
                value = parse_int(raw, 'configuration')
                if not 0 < value < 1000:
                    raise ValueError('configuration must be 1..999')
                self.vehicle_configuration = value
        live = 'applies to the next room start'
        try:
            if self.vehicle_configuration is not None:
                self.push_live(self._vehicle_swap_rows(self.vehicle_configuration))
                live = 'swapped in the running scene'
        except Exception as error:
            live = f'next room start only ({error})'
        return {'ok': True, 'vehicle_configuration': self.vehicle_configuration,
                'live': live, 'status': self.status()}

    def set_mode(self, query):
        name = (query.get('name') or [''])[0].strip()
        if not name:
            raise ValueError('name is required')
        self.mode = load_mode(name)
        with self.lock:
            self.mode_name = name
            self.weather_override = None
        return self.restart_async('mode')

    def handle(self, path, query):
        aliases = {
            '/status': '/api/status', '/health': '/api/health',
            '/start': '/api/start', '/stop': '/api/stop', '/reset': '/api/reset',
            '/rooms': '/api/rooms', '/modes': '/api/modes', '/mode': '/api/mode',
            '/weather': '/api/weather', '/cmd': '/api/command',
            '/vehicle': '/api/vehicle',
            '/features': '/api/features',
            '/commands': '/api/commands', '/packets': '/api/packets',
            '/logs': '/api/logs', '/spawn/near': '/api/spawn/near',
            '/spawn/request': '/api/spawn/request',
            '/heightmap': '/api/heightmap',
        }
        path = aliases.get(path, path)
        if path in ('', '/', '/api', '/api/'):
            return {
                'ok': True,
                'service': 'roe-room-manager',
                'room': self.room_id,
                'mode': self.mode_name,
                'endpoints': [
                    '/api/status', '/api/health', '/api/start', '/api/stop', '/api/reset',
                    '/api/rooms', '/api/modes', '/api/mode?name=dion',
                    '/api/weather?hour=8&temperature_raw=500',
                    '/api/vehicle?configuration=109',
                    '/api/features',
                    '/api/command?id=demo&command=0x4a6&payload_hex=',
                    '/api/command?id=heal&action=set_own_health&hp=100',
                    '/api/command?id=ammo&action=give_ammo&definition=30004&quantity=30',
                    '/api/commands', '/api/command/clear',
                    '/api/packets?tail=100', '/api/logs?name=endpoint&tail=100',
                    '/api/spawn/near?x=365878&y=552814&z=260206&radius=50000',
                    '/api/spawn/request?kind=loot&item_id=10204&quantity=1&radius_cm=2000',
                    '/api/heightmap',
                ],
            }
        if path == '/api/health':
            return {'ok': True, 'state': self.state, 'ready': self.ready}
        if path in ('/api/status', '/api/room', '/api/session'):
            return self.status()
        if path in ('/api/start', '/api/room/start'):
            return self.start('api-start')
        if path in ('/api/stop', '/api/room/stop'):
            return self.stop(user=True)
        if path in ('/api/reset', '/api/room/reset'):
            return self.restart_async('api-reset')
        if path == '/api/rooms':
            return {'ok': True, 'rooms': [self.status()], 'note': 'single-room foundation'}
        if path == '/api/modes':
            return {'ok': True, 'modes': list_modes()}
        if path == '/api/mode':
            return self.set_mode(query)
        if path == '/api/weather':
            return self.set_weather(query)
        if path == '/api/vehicle':
            return self.set_vehicle(query)
        if path == '/api/command':
            return self.add_command(query)
        if path == '/api/commands':
            return self.commands()
        if path in ('/api/command/clear', '/api/commands/clear'):
            return self.clear_commands()
        if path == '/api/packets':
            return self.packets(query)
        if path == '/api/logs':
            return self.logs(query)
        if path == '/api/spawn/near':
            return self.spawn_near(query)
        if path == '/api/spawn/request':
            return self.spawn_request(query)
        if path == '/api/heightmap':
            return self.heightmap()
        if path == '/api/features':
            return self.features()
        raise ValueError('unknown endpoint')


class Server(ThreadingHTTPServer):
    # No port sharing on Windows: a second room manager must fail loudly
    # instead of silently taking the port over.
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    server_version = 'ROE-Room/1.0'

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            result = self.server.room.handle(parsed.path, parse_qs(parsed.query, keep_blank_values=True))
            self.send_json(200, result)
        except Exception as error:
            self.send_json(400, {'ok': False, 'error': str(error)})

    def send_json(self, code, value):
        body = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser(description='ROE single-room supervisor and live GET API')
    parser.add_argument('--config', type=Path, default=ROOT/'config'/'services'/'room.json',
                        help='конфиг комнаты (config/services/room.json)')
    parser.add_argument('--mode', default='dion', help='mode folder under modes/')
    parser.add_argument('--room-id', default='dion-1')
    parser.add_argument('--profile', default='default')
    parser.add_argument('--client', type=Path, help='client directory; default .tools/client-path.txt')
    parser.add_argument('--api-host', default='127.0.0.1')
    parser.add_argument('--api-port', type=int, default=18080)
    parser.add_argument('--lobby-api', help='HTTP-API лобби для регистрации комнаты')
    parser.add_argument('--duration', type=int, help='launcher lifetime override in seconds')
    parser.add_argument('--idle-reset', type=int, help='idle reset seconds override')
    parser.add_argument('--instance-id', type=int, default=1, help='room instance id for the join config')
    parser.add_argument('--no-autostart', action='store_true')
    parser.add_argument('--no-auto-restart', action='store_true')
    args = parser.parse_args()
    if args.config and args.config.is_file():
        # Конфиг задаёт значения по умолчанию, ключи командной строки важнее.
        data = read_json(args.config)
        if not isinstance(data, dict):
            parser.error('room config must contain an object')
        defaults = {
            'mode': data.get('mode', args.mode),
            'room_id': data.get('room_id', args.room_id),
            'profile': data.get('profile', args.profile),
            'api_host': data.get('api_host', args.api_host),
            'api_port': data.get('api_port', args.api_port),
            'lobby_api': data.get('lobby_api', args.lobby_api),
            'duration': data.get('duration_seconds', args.duration),
            'idle_reset': data.get('idle_reset_seconds', args.idle_reset),
            'instance_id': data.get('instance_id', args.instance_id),
        }
        for key, value in defaults.items():
            if value is None:
                continue
            if key == 'duration' and args.duration is not None:
                continue
            if key == 'idle_reset' and args.idle_reset is not None:
                continue
            if key == 'lobby_api' and args.lobby_api:
                continue
            setattr(args, key, value)
    if args.api_host not in ('127.0.0.1', 'localhost', '::1'):
        parser.error('API must bind to loopback')
    if not 0 <= args.api_port <= 65535:
        parser.error('invalid API port')
    client = args.client if args.client else default_client()
    try:
        room = Room(args.mode, args.room_id, client, args.profile,
                    duration=args.duration, idle_reset=args.idle_reset,
                    auto_restart=not args.no_auto_restart,
                    instance_id=args.instance_id, lobby_api=args.lobby_api)
    except Exception as error:
        parser.error(str(error))
    if not args.no_autostart:
        try:
            room.start('startup')
        except Exception as error:
            room.error = f'startup failed: {error}'
            print(f'startup failed: {error}', flush=True)
    threading.Thread(target=room.monitor, daemon=True).start()
    try:
        httpd = Server((args.api_host, args.api_port), Handler)
    except OSError as error:
        parser.error(f'cannot bind API on {args.api_host}:{args.api_port}: {error} '
                     f'(the port is already taken by another room or login server)')
    httpd.room = room
    port = httpd.server_address[1]
    print(json.dumps({'ok': True, 'api': f'http://{args.api_host}:{port}/api/status',
                      'room': args.room_id, 'mode': args.mode,
                      'client': str(client) if client else None}, ensure_ascii=False), flush=True)
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        room.shutdown_event.set()
        httpd.shutdown()
        room.stop(user=True)


if __name__ == '__main__':
    main()
