# Dion room profile

This is the first room profile in `ROE_local_test_1`.

- Map id: `16010` (validated world/spawn/zone/environment data).
- Mode: cycle, endless test match, 3x cycle scale, 7 second selection.
- Loot catalog: `loot-pool61.json` (mode-local copy, identical to the fork2 one).
- Spawn table: `spawn_points.json` (the 660 point fork2 grid, identical).
- Room idle reset: 30 seconds after the first game packet.
- Weather: fixed hour 8 and +5 C, exactly as the fork2 default. A random
  hour or temperature changes the time of day and with it the landing point,
  so `randomize` stays off here.
- Dynamic loot/vehicle events: disabled in `mode.json`.
- The lobby does not auto-match in this mode: the player presses
  Play -> Start Matchmaking, so the client picks the landing point itself and
  the spawn matches the old fork2.

The name `dion` is the room/mode name. Do not switch `map.id` to another value
without adding the matching world, spawn, loot, zone, scene and terrain data;
the launcher will reject unsupported ids.

API examples:

```text
GET /api/status
GET /api/packets?tail=100
GET /api/logs?name=endpoint&tail=100
GET /api/reset
GET /api/weather?hour=15&temperature_raw=0
GET /api/spawn/near?x=365878&y=552814&z=260206&radius=50000
GET /api/spawn/request?kind=loot&item_id=10101&quantity=1&radius_cm=2000
GET /api/command?id=test&command=0x4a6&payload_hex=
GET /api/command?id=heal&action=set_own_health&hp=100
```

`/api/command` writes a normal `live-commands.json` entry consumed by the
existing endpoint's `--live-commands` polling. The command ID must be unique
within the current session.

`/api/spawn/request` records the request in `spawn-requests.jsonl` and
validates the item id against the mode loot catalog. It always answers
`applied: false`: the live entity spawn still needs a confirmed MsgID.
