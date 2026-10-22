# Mode config overlay

Files in this folder replace the same-named files from the global `config/`
folder when the room starts. The room manager passes
`--config-overlay modes/<mode>/config` to `tools/windows_launch.py`.

Overridden files are resolved exactly like the global ones, so the
`@wire/...`, `@account` and `@region` placeholders still work.

Current overrides:

| File | What it drives |
|---|---|
| `join.json` | lobby answer for the player: game endpoint route, instance id, map id. The launcher still rewrites `instance_id`, `connection_id_a8` and the map id. |
| `endless.json` | endless world: HP, hazard, zone stages, evacuation refuge |
| `world.json` | base world used for the scene pacing in non-endless mode |
| `scene-cycle.json` | cycle scene rules (scene timings and responses) |
| `environment.json` | environment preset; hour and temperature are still taken from the room API |

Everything else (doors, breakables, cosmetics, weapons, loot catalog) still
comes from the global `config/` folder unless a copy is added here.
