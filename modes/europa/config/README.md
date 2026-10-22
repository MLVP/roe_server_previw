# Europa (Kill Zone, 16007) - config overlay

Only the files in this folder replace the same-named files from the global
`config/` folder for this mode.

| File | What it drives |
|---|---|
| `environment.json` | map 16007, hour and temperature preset |
| `join.json` | lobby answer for the player: game endpoint route, instance id, map id (the launcher rewrites the instance id and the map id) |

Everything else stays the global Dione profile, because the Kill Zone data is
not extracted yet:

- `world.json`, `endless.json` - zone stages, hazard bounds;
- `scene-cycle.json` - scene rules and timings;
- `winter-doors.json`, `winter-breakables.json` - doors and breakables;
- `loot-pool61.json` - loot positions (the mode points at the Dione copy);
- `spawn_points.json` - the Dione spawn grid (the mode points at the Dione copy);
- `heightmap_4096x4096_u16.raw` - the Dione heightmap (the mode points at the
  Dione copy).

The same approach is used by `tools/anotheruser_louncher` for the Kill Zone
map: the client loads the map, the server keeps Dione's data.
