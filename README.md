# Ring of Elysium 2022 — local server (preview)

A test stack for the Ring of Elysium client (Steam, 2022): uid login, a permanent
lobby and a room manager. The client and game files are not modified — everything
works at the server protocol level.

Components:

| Service | Port | Purpose |
|---|---|---|
| accounts | TCP 8099 | login, profile delivery |
| lobby | TCP 8001 / HTTP 8010 | permanent lobby, room selection by map |
| room manager | HTTP 18080 | starts and stops a room |
| room | UDP 18001 | game room (scene, loot, vehicles) |


## Add a new user

```bat
user.cmd add alice --nickname Alice      :: uid and actor_uid are generated
user.cmd list                            :: all users with uids
user.cmd show alice                      :: uid, actor_uid, folder
user.cmd remove alice
```

Profile: `accounts/<name>/`, registry: `users/registry.json`.

```example
user.cmd add player
{
  "version": 1,
  "name": "player",
  "nickname": "player",
  "uid": 678052403,
  "actor_uid": "0x515bb114abb6d3",
  "created_at": "2026-10-22T15:26:41.153054+00:00",
  "account": "accounts/player",
  "cosmetics": "cosmetics.json"
}
```

## Create a client shortcut

```bat
lnroeuser.cmd -uid <uid> -f "C:\Program Files (x86)\Steam\steamapps\common\Ring of Elysium" -o "%USERPROFILE%\Desktop\ROE alice.lnk"
```

`<uid>` comes from `user.cmd show alice`. The shortcut runs
`Europa_Client.exe -uid=<uid> -server=127.0.0.1:8001`.

- another lobby address — `-s host:port`;
- another game folder — `-f "path"`.

```example
lnroeuser.cmd -uid 678052403 -f "C:\Program Files (x86)\Steam\steamapps\common\Ring of Elysium" -o "%USERPROFILE%\Desktop\ROE Player.lnk"
{
  "shortcut": "C:\\Users\\homepc\\Desktop\\ROE Player.lnk",
  "target": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Ring of Elysium\\Europa_Client.exe",
  "arguments": "-language=en -garena -uid=678052403 -server=127.0.0.1:8001",
  "working_directory": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Ring of Elysium",
  "uid": 678052403,
  "server": "127.0.0.1:8001"
}
```

## Maps and modes

A mode is a folder `modes/<name>/`:

| Mode | Map | id |
|---|---|---|
| `dion` | Dione (EU_IceLand_4096) | 16010 |
| `europa` | Kill Zone (EU_Killzone_4096) | 16007 |
| `fdtd` | From Dusk Till Dawn (EU_IcelandNight_4096) | 16011 |
| `vera` | Vera / Desert (EU_Desert_4096) | 16021 |

The default mode lives in `config/services/room.json`:

```json
{ "mode": "vera", "room_id": "dion-1", "api_port": 18080, "instance_id": 1 }
```

Switch the running room without a restart:

```bat
curl "http://127.0.0.1:18080/api/mode?name=europa"
```

The lobby picks the room by the map id in the client request (Normal → map).
If that map has no room, the default mode's room is used.

Inside `modes/<name>/`:

- `mode.json` — `map.id`, weather hours, launcher arguments, `local_spawn`
  (spawn point, loot, vehicles), path to the `config/` overlay;
- `config/` — mode-owned copies of `environment.json`, `join.json`,
  `scene-cycle.json`, `world.json`, etc. (they override the global files);
- `loot-*.json` — loot catalog;
- `spawn_points.json` — birth point(s).

To add your own mode: copy `modes/vera` to `modes/<new>` and change `name`,
`map.id`, hours and the overlay.

Match auto-start without pressing Play — `config/services/lobby.json`:

```json
"match": { "auto_match_seconds": 5, "found_delay": 3, "estimate_seconds": 3 }
```

"auto_match_seconds":null disables it.

Loot and vehicles are generated around the spawn point:

```bat
.tools\python\python.exe tools\build_spawn_loot_2022.py ^
  --center 345746 341956 12779 --count 64 --map-id 16021 ^
  --catalog modes\vera\loot-desert-64.json ^
  --scene-source modes\dion\config\scene-cycle.json ^
  --scene modes\vera\config\scene-cycle.json --vehicles 102:300,109:-300
```

## Start the server

```bat
serve-all.cmd
```

Starts all three services in one console window; `Ctrl+C` stops them. Check:

```bat
curl http://127.0.0.1:18080/api/status
curl http://127.0.0.1:8010/api/status
```

## Stop the server

```bat
stop-server.cmd
```

Kills the services by port (8001/8010/8099/18001/18080) and the
`Europa_Client.exe` client.

## Start the client

Use the desktop shortcut (created below), or launch without one:

```bat
tools\play_client.ps1 -Uid 611567691
```

## Notes

- lobby logs: `lobby\<run>\{packets.log, events.jsonl, status.json}`,
  the current run pointer is `lobby/current.json`;
- room logs: `rooms\<room_id>\sessions\<id>\{packets.log, endpoint.log, scene\}`;
- packet viewer: `tools\packet_log_view_2022.py --summary`;
- optional client telemetry switch: `telemetry.cmd off | on | status`.

## Requirements

- Windows 10/11 with Ring of Elysium installed;
- the bundled Python in `.tools\python` (no separate install needed);
- `private/candidate-001.key` and `private/lobby-ck.bin`.
