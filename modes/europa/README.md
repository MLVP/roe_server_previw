# Europa (Kill Zone) - map 16007

The Kill Zone of the EU server. In the client tables the map is called
**EuropaKillZone** (`m_strName`), id **16007**, world folder
`EU_Killzone_4096` (the client has it in `Cache/Data/world/`).

## How the other launcher does it

`tools/anotheruser_louncher` (Rust launcher of another user) has the same four
maps in `crates/roe-core/src/maps.rs`:

| name | world | id | state |
|---|---|---|---|
| Dione | `EU_IceLand_4096` | 16010 | Supported |
| **Kill Zone** | `EU_Killzone_4096` | **16007** | **Experimental** |
| Desert | `EU_Desert_4096` | 16021 | Broken (falls through the ground) |
| Dione at night | `EU_IcelandNight_4096` | 16011 | Broken (hangs at match start) |

It applies the map the same way we do: the map id is written into the
enter-room reply, field `profile.base.m644` (`crates/roe-core/src/playername.rs`,
`PATCH_PY`). For the Kill Zone it keeps the Dione server data - spawn points,
zones, evacuation - and only swaps the map id, which is why it is marked
Experimental.

Here the same patch is done by the launcher itself:
`tools/room_map_2022.py` (`patch_room_map`) rewrites `profile.base.m644` in the
room template, and `config/join.json` gets the same map id for the lobby.

## Launch parameters

```bat
rem window 1 - server (the login server creates the room itself)
serve-login.cmd --room-mode europa --room-profile awp

rem window 2 - client
play-account.cmd awp
```

Room only: `serve-room.cmd europa --profile awp`.

## Mode settings

| Field | Value |
|---|---|
| `map.id` | 16007 |
| `map.route` | `0:127.0.0.1:18001` |
| `weather.hours` | `[7, 8, 15, 16]` (client time table for 16007) |
| `weather.temperatures` | `[-500, 0, 500]` (random) |
| `spawn_points` | `spawn_points_killzone.json` (Kill Zone: the default landing cell) |
| `heightmap` | `../dion/heightmap_4096x4096_u16.raw` (Dione terrain, shared) |
| `loot` | `loot-killzone-64.json` (64 items at the local spawn point) |
| `config` | `config/` overlay: `environment.json` (map 16007), `join.json`, `scene-cycle.json` (Dione scene + 2 vehicles) |

Launcher arguments (the map id and the hour come from the mode and the
overlay):

```text
--kit glider --mode cycle --cycle-scale 3 --weapon-profile citori
--target armored --target-los off --selection-seconds 7
--reliable-udp --idle-handoff --winter-doors --winter-windows
--endless --auto-match-seconds 12
--loot-catalog loot-killzone-64.json
```

## Local spawn point (loot and vehicles)

The player spawns at **X 360047, Y 366722, Z 40173** (the values from the
player's own overlay: `X=360047.216 Y=40173.483 Z=366722.359`, the height is
the last component). The closest known grid point of the IceLand spawn table
is cell 12,12 = `(364800, 364800, 261784)`, 5127 units away.

At that point the mode places:

- **64 loot entities** - `modes/europa/loot-killzone-64.json`, a 8x8 grid with
  35 unit steps, the same item ids as the Dione pool (10101 R700, 10201 M4A1,
  ... 30001 5.56mm, 70001 Bandage, ...);
- **2 vehicles** - `modes/europa/config/scene-cycle.json` (a copy of the global
  scene plus one rule with `origin: local_spawn_vehicles`):
  - Jeep102 at `(360347, 366722, 40173)`;
  - SnowMotor109 at `(359747, 366722, 40173)`.

Regenerate after moving the spawn point:

```bat
.tools\python\python.exe tools\build_spawn_loot_2022.py ^
    --center 360047 366722 40173 --count 64 ^
    --catalog modes\europa\loot-killzone-64.json ^
    --scene modes\europa\config\scene-cycle.json
```

The loot is sent by the endpoint when the player is inside the AOI radius
(`radius_cm: 2000`), the vehicles with the scene rule after the selection.

## What is still the Dione profile

The Kill Zone has its own landscape, so the Dione zone, hazard bounds, doors,
breakables and heightmap do not describe it. The client loads the map and the
match starts, the loot and the vehicles are now placed at the local spawn
point, but the evacuation helicopter still uses the Dione zone.

The landing points are per map now: the endpoint takes
`--spawn-points <table>`, the launcher passes it and the room fills it in from
`spawn_points` of the mode. The Kill Zone table holds the default landing
cell of the map:

```json
{"map_id": 16007, "default_cell": [12, 26],
 "points": [[12, 26, 360047, 366722, 40173]]}
```

On the Kill Zone the client does not ask the server for the landing point (the
picker does not answer, the same as in the other launcher), it uses its own
default, which is the point above.

Client archives can be read with `tools/sfc_reader_2022.py` (read only):

```bat
.tools\python\python.exe tools\sfc_reader_2022.py ^
    "C:\Program Files (x86)\Steam\steamapps\common\Ring of Elysium\Cache\Data\world\EU_Killzone_4096\EU_Killzone_4096.sfc" --list
```
Extracting the Kill Zone data (spawns, zone, doors, breakables, scene) is the
next step for this mode.

Runtime checks:

```bat
curl http://127.0.0.1:8099/room/api/status
curl "http://127.0.0.1:8099/room/api/weather?hour=8&temperature_raw=0"
```
