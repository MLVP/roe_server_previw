# ROE Local server structure — tree and call chains

Map of "who invokes whom (with which arguments)" and what each piece does.
Root: `F:\ROERevive\tools\ROE_local_test_3\`. Research write-ups live in `protocol/`.
Russian version: `project_structure_ru.md`.

## 1. Call chain

```
serve-all.cmd
└─ tools/serve_all_2022.py              orchestrator:3 services + /health wait
   ├─ tools/roe_accounts.py serve --host127.0.0.1 --port 8099        accounts (HTTP 8099)
   ├─ tools/lobby_service.py --config config/services/lobby.json     lobby: TCP 8001 + HTTP API 8010
   └─ server/room_manager.py --config config/services/room.json      room manager (HTTP API 18080)
      └─ per session — tools/windows_launch.py (room launcher):
         --client <client dir> --profile --services-only
         --room-run-dir rooms/<room>/sessions/<id> --duration
         --map-id --instance-id --start-hour --temperature-raw --live-control
         + modes/<mode>/mode.json → launcher_args (kit, cycle, doors/windows,
           --loot-generation runtime --loot-points … --loot-pools …)
         + --spawn-points modes/<mode>/spawn_points*.json
         + --spawn-origin X,Y,Z (local_spawn from mode.json)
         + --config-overlay <dir> (config/*.json overrides)
         └─ tools/run_service.py endpoint
            --handshake --ident --grant --auth
            --room-template <room.bin> --scene-rules <scene-cycle.json>
            --scene-clock --selection-seconds7
            --weapon-config --parcel-config --environment-config
            --door-config --breakable-config
            --loot-catalog <file>  OR  --loot-generation runtime
                                     --loot-points --loot-pools
                                     --loot-max-entities --loot-seed
            --spawn-points --world-config --evacuation-*-config
            --actor-config --live-commands --output <session>/scene
            └─ server/directory/game_endpoint_probe_2022.py   game UDP 18001
               (run_service.py proxy → tools/heartbeat_probe_2022.py — TCP proxy role)
```

Client is started separately (stack and game are independent):

```
play-client.cmd → tools/play_client.ps1 -Uid <N> [-Profile]
└─ Europa_Client.exe -uid=<N> -server=127.0.0.1:8001
   └─ lobby (TCP 8001) hands out route0:127.0.0.1:18001 → client talks to the room endpoint
```

One-off launches without the room manager (legacy path):

```
play.cmd → run-roe-2022.cmd → tools/bootstrap.ps1 → windows_launch.py … (full cycle, spawns the client itself)
serve-game.cmd <profile>   → run-roe-2022.cmd … --services-only (services only; client via play-client.cmd)
serve-room.cmd [mode]      → server/room_manager.py --mode <mode> (default dion)
serve-accounts.cmd         → tools/roe_accounts.py serve
stop-server.cmd            → taskkill by ports8001/8010/8099/18001/18080/19001/9001 + Europa_Client.exe
```

HTTP surface: `accounts: 8099 /health` · `lobby: 8010 /api/status` ·
`room: 18080 /api/status, /api/mode, /api/features, /api/spawn/*` (spawn requests
are only recorded; live injection is not implemented).

## 2. Root tree

```
ROE_local_test_3/
├─ serve-all.cmd              start everything (accounts+lobby+room-manager)
├─ stop-server.cmd            kill everything by ports
├─ play.cmd / play-endless.cmd   full single-player cycle (legacy, bootstrap.ps1)
├─ play-client.cmd            client only (play_client.ps1 -Uid)
├─ serve-game.cmd / -endless / -room / -accounts / -login   individual services
├─ register-account.cmd / register-client.cmd /
│  lnroeuser.cmd / list-accounts.cmd / user.cmd / play-account.cmd /
│  check-login-room.cmd       local account management
├─ export-report.cmd          compact report without keys/raw packets
├─ reset.cmd                  clean local traces (never touches game files)
├─ telemetry.cmd              manual client telemetry switch
├─ run-roe-2022.cmd           bootstrap wrapper (play/serve-game)
├─ README.md                  quick start (EN/RU)
├─ GOALS.md                   project goals (short)
├─ TODO.md                    prioritized tasks (P0/P1/P2)
├─ project_structure_ru.md    Russian version
├─ project_structure_en.md    this file
├─ SMOKE-TEST.md / WINDOWS-TESTS*.md / VALIDATION.md   test procedures
├─ requirements.txt           Python dependencies (for .tools/python)
│
├─ server/                    server processes
│  └─ room_manager.py         room manager: load_mode, session spawn (windows_launch),
│                             monitor (match end + UDP silence → new session, idle),
│                             HTTP API 18080, room registration with the lobby
├─ server/directory/          ← imported by the endpoint (see §3)
│
├─ tools/                     launch scripts and instruments
│  ├─ serve_all_2022.py       runs the3 services under one supervisor
│  ├─ roe_accounts.py         HTTP accounts (register/login, users/ + accounts/)
│  ├─ lobby_service.py        lobby: TCP 8001 (login protocol) + REST 8010
│  ├─ windows_launch.py       session launcher: config materialization, firewall,
│  │                          telemetry off, starts run_service.py endpoint
│  ├─ run_service.py          dispatcher+bootstrap: endpoint → game_endpoint_probe_2022,
│  │                          proxy → heartbeat_probe_2022 (sys.path + compact Capture)
│  ├─ heartbeat_probe_2022.py room TCP front (proxy): login/handshake, -uid=,
│  │                          JOIN_INSTANCE, custom-room messages0x737x
│  ├─ play_client.ps1         starts Europa_Client.exe with -uid from users/registry.json
│  ├─ bootstrap.ps1           dependency install + full launch (play.cmd)
│  ├─ ensure_firewall.ps1 / telemetry_switch.ps1   game isolation, telemetry off
│  ├─ extract_map_points_2022.py   loot point extraction from SFC → map-data/
│  ├─ extract_bornpos_2022.py      spawn grid extraction (BlockBornPosTable) + vehicle slices
│  ├─ build_loot_pools_2022.py     builds modes/common/loot-pools.json
│  ├─ build_spawn_loot_2022.py     static loot catalogs near spawn
│  ├─ roe_custom_room_2022.py  (deferred) custom-room handlers0x737x
│  └─ …                        protocol fixtures, cosmetics, reports (62 .py)
│
├─ modes/<mode>/              one folder = one map mode (dion, europa, vera, fdtd, common)
│  ├─ mode.json               map.id, launcher_args (incl. the loot switch),
│  │                          weather, local_spawn, room.idle_reset_seconds, features
│  ├─ spawn_points*.json      spawn grid [cellX, cellY, x, y, height] + default_cell
│  ├─ doors-*.json / breakables-*.json   door/window catalogs (accept_unknown for europa/vera)
│  └─ config/                 scene-cycle.json, scene-walk.json and other scene fixtures
│
├─ config/                    shared launcher fixtures: join/room/weapon-*/target-*/parcel,
│                             environment, cosmetics, endless.json, ballistic-*, loot-*.json
├─ config/services/           accounts.json, lobby.json, room.json (ports of the3 services)
│
├─ map-data/                  extracted original tables:
│                             <map>-entitypoints.json (loot), <map>-bornpos.json (grids),
│                             <map>-vehiclepoints.json (vehicles)
├─ protocol/                  protocol-analysis and server-behavior write-ups:
│                             LOBBY-PROTOCOL, LOBBY-SERVICE, MAP-POINTS, ITEMS-2022 (+csv),
│                             HIT-*, SESSION-RESULT, LOOT-SURFACE, TERRAIN-HEIGHTFIELD,
│                             client_message_names.tsv (opcode table) and more
├─ rooms/<room>/sessions/<id>/   session artifacts (created at runtime):
│                             launcher/endpoint.log, packets.log, scene/events.jsonl,
│                             runtime-loot-catalog.json, generated configs
├─ lobby/<run>/               lobby logs (created at runtime)
├─ runtime/                   service logs (runtime/services/*.log), state
├─ accounts/ / users/         local accounts and uid registry (users/registry.json)
├─ private/                   emulator keys (candidate-001.key, lobby-ck.bin)
├─ .tools/                    local Python40MB + client-path.txt
├─ tests/                     86 files: python -m unittest discover -s tests (678 tests)
└─ runs/                      legacy launch dirs (bootstrap)
```

Deliberately not copied: `some_RE_data/` (research archive), `captures/`,
`proto_analysis/` (empty), session logs/backups, `AGENTS.md`, `TODO.txt`
(replaced by `TODO.md`). Rights: `RIGHTS.md`, `.gitignore`, `.gitattributes`. `SOURCE-MANIFEST.json` was
removed (no server function; references cut from `windows_launch.py`/`export_test_report_2022.py`).

## 3. Endpoint (`server/directory/`) internals

`game_endpoint_probe_2022.py` — UDP dispatcher: handshake/ident/grant/auth phases,
room template, scene, then gameplay messages.

| Group | Modules | Purpose |
|---|---|---|
| Core | `listener.py`, `reliable_udp_2022.py` | packet log (Capture), reliable UDP |
| Inventory/weapons | `weapon_probe_2022.py`, `inventory_codec_2022.py`, `attachment_probe_2022.py` | slots, magazines, pickup with bag-weight limits, item encoding |
| Start selection | `winter_selection_2022.py` + `winter_spawn_points_2022.json` | BORN_POS_REQ/SYNC (cell grid), ability/loadout choice |
| Loot | `loot_catalog_2022.py`, `loot_runtime_2022.py` | catalog load (static or runtime generation), proximity serving |
| Doors/windows | `door_state_2022.py`, `breakable_state_2022.py` | door states, breakable windows/objects |
| World | `world_probe_2022.py`, `region_index_2022.py`, `match_result_2022.py`, `match_statistics_2022.py`, `environment_probe_2022.py` | HP/damage, zones, match result, stats, weather/time |
| Vehicles | `vehicle_probe_2022.py`, `shared_vehicle_2022.py` | cars/boats, shared seats/ownership |
| Multiplayer | `peer_avatar_2022.py`, `peer_motion_2022.py`, `peer_lifecycle_2022.py`, `peer_equipment_2022.py`, `peer_spectator_2022.py`, `shared_*` | avatars, sync, shared loot/combat/evacuation |
| Combat | `ballistics_2022.py`, `hit_feedback_2022.py`, `shoot_target_records_2022.py`, `projectile_materials_2022.py`, `shared_combat_2022.py` | ballistics, hit markers, target |
| Misc | `medical_probe_2022.py`, `throwable_*`, `parcel_*`, `death_parcel_2022.py`, `cosmetic_selection_2022.py`, `room_cosmetics_2022.py`, `map_profiles_2022.py`, `state_scene_actions_2022.py`, `live_scene_probe_2022.py`, `actor_probe_2022.py`, `bot_controller_2022.py`, `collision_*`, `ground_route_2022.py`, `movement_validation_2022.py`, `lobby_login_2022.py` | meds/grenades/parcels/death, cosmetics, map profiles, scene, bots, collision, movement validation |

## 4. Mode data and where it lives

- **Spawn grids**: `map-data/*-bornpos.json` (BlockBornPosTable from `SFC/Common.sfc`)
  → `modes/<map>/spawn_points*.json` → `--spawn-points` → `winter_selection_2022`.
- **Loot points**: `map-data/*-entitypoints.json` (ENTITYPOINTCONFIG) →
  `--loot-points` → `loot_runtime_2022.build_catalog()` → `runtime-loot-catalog.json`
  in the session → `loot_catalog_2022.LootCatalog.load`. Switch in `mode.json`:
  `--loot-generation runtime` (main) vs `--loot-catalog <file>` (exceptional).
- **Item pools**: `modes/common/loot-pools.json` (built by `tools/build_loot_pools_2022.py`).
- **Generation weights**: `modes/<map>/loot-weights.json` (`--loot-weights`) — chance
  of an item appearing at its point; default 1.0, ammo 0.1; the companion ammo packs
  of a spawned weapon bypass the weight (`loot_runtime_2022.load_weights`).
- **Vehicles at points**: `map-data/<map>-vehiclepoints.json` (`--vehicle-points`,
  `--vehicle-count`, `--vehicle-configs`, europa only) → `tools/vehicle_points_2022.py`
  → extra 0x654B responses in scene-walk/scene-cycle (random points, random type
  from the pool; verified 102 jeep / 109 snowmotor; helicopter 104B/cfg6, boat
  87B/cfg7 and 117B/cfg501 — templates exist, points/verification pending).
- **Doors/windows**: `modes/<map>/doors-*.json`, `breakables-*.json` → `--door-config`/`--breakable-config`.

## 5. Checks

```
.tools\python\python.exe -X utf8 -B -m unittest discover -s tests
```

86 files, 678 tests. Known exclusions (no client installed):
`test_reset_local_2022` (6), `test_select_client_2022` (1).
