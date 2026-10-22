# From Dusk Till Dawn (fdtd) - map 16011

Dione at night. The map is `EU_IcelandNight_4096` / `IceLandNight_01`, id
**16011**; the landscape is the same island as `16010`, only the lighting and
the event mode differ.

## Launch parameters

```bat
rem window 1 - server (the login server creates the room itself)
serve-login.cmd --room-mode fdtd --room-profile awp

rem window 2 - client
play-account.cmd awp
```

Room only: `serve-room.cmd fdtd --profile awp`.

## Mode settings

| Field | Value |
|---|---|
| `map.id` | 16011 |
| `map.route` | `0:127.0.0.1:18001` |
| `weather.hours` | `[0]` - the client time table allows hour 0 only |
| `weather.temperatures` | `[-500, 0, 500]` (random) |
| `spawn_points` | `spawn_points.json` (shared IceLand grid, 660 points) |
| `heightmap` | `heightmap_4096x4096_u16.raw` (shared IceLand terrain) |
| `loot` | `loot-pool61.json` (mode-local copy) |
| `config` | `config/` overlay: `environment.json` (map 16011, hour 0), `join.json`, `world.json`, `endless.json`, `scene-cycle.json` |

Launcher arguments (the map id and the hour come from the mode and the
overlay):

```text
--kit glider --mode cycle --cycle-scale 3 --weapon-profile citori
--target armored --target-los off --selection-seconds 7
--reliable-udp --idle-handoff --winter-doors --winter-windows
--endless --auto-match-seconds 12 --vehicle-configuration 109
--loot-catalog loot-pool61.json
```

## Notes

`tools/anotheruser_louncher` (another user's Rust launcher) lists this map as
"Dione at night" and marks it broken: with the stock server the landing-point
picker does not answer and the game freezes when the countdown ends. Here the
room drives the scene itself (`--auto-match-seconds 12`, endless cycle scene),
so the client enters the room and the match starts.

Still shared with the 16010 profile: zone and hazard bounds, doors,
breakables, scene rules, loot positions and the heightmap (the night map uses
the same landscape). The night airdrop/plane rules and the night loot density
are not extracted yet.
