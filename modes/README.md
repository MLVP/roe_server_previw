# Modes and rooms

Each immediate child of `modes/` is one mode folder. A room starts with exactly
one mode from `modes/<name>/mode.json`.

Current modes:

- `dion` - single-room test profile, map id `16010` (`EU_IceLand_4096`, point
  selection start, client hours 7/8/15/16).
- `fdtd` - "From Dusk Till Dawn", map id `16011` (`EU_IcelandNight_4096` /
  `IceLandNight_01`, client hour 0 only). Landscape, spawn grid, zone, doors,
  breakables and heightmap are shared with `dion`; the map id and the time of
  day differ. See `modes/fdtd/README.md`.
- `europa` - Kill Zone of the EU server, map id `16007`
  (`EU_Killzone_4096` / `KillZone_001`, "EuropaKillZone" in the client tables).
  Own landscape, so the spawn grid, zone, loot and heightmap stay the Dione
  ones - experimental, the same as the other launcher does it. See
  `modes/europa/README.md`.
- `vera` - Desert of the EU server, map id `16021` (`EU_Desert_4096` /
  `Desert_001`, "Vera" in the client tables). Own landscape; the server data
  stays the Dione one. The spawn point is taken from the ground points of the
  client archive `Cache/Data/world/EU_Desert_4096/EU_Desert_4096.sfc`, the
  loot and the two vehicles are placed there. See `modes/vera/README.md`.

Run the new room stack:

```bat
serve-room.cmd dion
```

The API is loopback-only and defaults to `http://127.0.0.1:18080/api/status`.

Useful fields in `mode.json`:

- `launcher_args` — extra arguments passed to `tools/windows_launch.py`.
- `config/` — mode-owned copies of `config/*.json`. They override the global
  files for this mode (the room manager passes `--config-overlay`).
- `duration_seconds` — launcher lifetime; the room supervisor resets earlier
  when the idle rule fires.
- `room.idle_reset_seconds` — after the first game packet, reset the room when
  no packet arrives for this many seconds (default 30).
- `features.dynamic_events` — disabled scaffold for periodic loot/vehicle
  requests. Actual protocol spawn injection is not implemented yet.
- `weather` — start hour/temperature or random choices.
- `spawn_points` — JSON file used by `/api/spawn/near` and the heightmap tool.
- `loot-pool61.json` — mode-local loot catalog passed to the endpoint.

Map data is still guarded by the launcher: map ids other than `16010` are
rejected until per-map spawn, loot, zone, scene, terrain and environment data
exist.
