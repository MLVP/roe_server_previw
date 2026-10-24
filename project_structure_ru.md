# Структура сервера ROE Local — дерево и вызовы

Карта «кто кого вызывает (с какими аргументами) и чем занимается». Корень:
`F:\ROERevive\tools\ROE_local_test_3\`. Исследовательские документы — в `protocol/`.
Английская версия: `project_structure_en.md`.

## 1. Цепочка вызовов

```
serve-all.cmd
└─ tools/serve_all_2022.py              оркестратор:3 службы + ожидание /health
   ├─ tools/roe_accounts.py serve --host127.0.0.1 --port 8099        аккаунты (HTTP 8099)
   ├─ tools/lobby_service.py --config config/services/lobby.json     лобби: TCP 8001 + HTTP-API 8010
   └─ server/room_manager.py --config config/services/room.json      менеджер комнат (HTTP-API 18080)
      └─ на каждую сессию — tools/windows_launch.py (лаунчер комнаты):
         --client <папка клиента> --profile --services-only
         --room-run-dir rooms/<комната>/sessions/<id> --duration
         --map-id --instance-id --start-hour --temperature-raw --live-control
         + modes/<режим>/mode.json → launcher_args (кит, цикл, двери/окна,
           --loot-generation runtime --loot-points … --loot-pools …)
         + --spawn-points modes/<режим>/spawn_points*.json
         + --spawn-origin X,Y,Z (local_spawn из mode.json)
         + --config-overlay <папка> (переопределения config/*.json)
         └─ tools/run_service.py endpoint
            --handshake --ident --grant --auth
            --room-template <room.bin> --scene-rules <scene-cycle.json>
            --scene-clock --selection-seconds7
            --weapon-config --parcel-config --environment-config
            --door-config --breakable-config
            --loot-catalog <файл>  ИЛИ  --loot-generation runtime
                                     --loot-points --loot-pools
                                     --loot-max-entities --loot-seed
            --spawn-points --world-config --evacuation-*-config
            --actor-config --live-commands --output <сессия>/scene
            └─ server/directory/game_endpoint_probe_2022.py   игровой UDP 18001
               (run_service.py proxy → tools/heartbeat_probe_2022.py — режим TCP-прокси)
```

Клиент запускается отдельно (стек и игра — независимо):

```
play-client.cmd → tools/play_client.ps1 -Uid <N> [-Profile]
└─ Europa_Client.exe -uid=<N> -server=127.0.0.1:8001
   └─ лобби (TCP 8001) выдаёт маршрут0:127.0.0.1:18001 → клиент ходит в эндпоинт комнаты
```

Разовые запуски без менеджера комнат (legacy-путь):

```
play.cmd → run-roe-2022.cmd → tools/bootstrap.ps1 → windows_launch.py … (полный цикл, сам стартует клиент)
serve-game.cmd <профиль>   → run-roe-2022.cmd … --services-only (только сервисы; клиент — play-client.cmd)
serve-room.cmd [режим]     → server/room_manager.py --mode <режим> (по умолчанию dion)
serve-accounts.cmd         → tools/roe_accounts.py serve
stop-server.cmd            → taskkill по портам8001/8010/8099/18001/18080/19001/9001 + Europa_Client.exe
```

HTTP-поверхность: `accounts: 8099 /health` · `lobby: 8010 /api/status` ·
`room: 18080 /api/status, /api/mode, /api/features, /api/spawn/*` (спавн-запросы
только пишутся, инъекция в живой матч не реализована).

## 2. Дерево корня

```
ROE_local_test_3/
├─ serve-all.cmd              поднять всё (accounts+lobby+room-manager)
├─ stop-server.cmd            убить всё по портам
├─ play.cmd / play-endless.cmd   полный одиночный цикл (legacy, bootstrap.ps1)
├─ play-client.cmd            только клиент (play_client.ps1 -Uid)
├─ serve-game.cmd / -endless / -room / -accounts / -login   отдельные службы поштучно
├─ register-account.cmd / register-client.cmd /
│  lnroeuser.cmd / list-accounts.cmd / user.cmd / play-account.cmd /
│  check-login-room.cmd       управление локальными аккаунтами
├─ export-report.cmd          собрать отчёт без ключей и сырых пакетов
├─ reset.cmd                  чистка локальных следов (без файлов игры)
├─ telemetry.cmd              ручной переключатель телеметрии клиента
├─ run-roe-2022.cmd           обёртка bootstrap (play/serve-game)
├─ README.md                  быстрый старт (EN/RU)
├─ GOALS.md                   цели проекта (коротко)
├─ TODO.md                    задачи с приоритетами (P0/P1/P2)
├─ project_structure_ru.md    этот файл
├─ project_structure_en.md    English version
├─ SMOKE-TEST.md / WINDOWS-TESTS*.md / VALIDATION.md   процедуры тестирования
├─ requirements.txt           Python-зависимости (для .tools/python)
│
├─ server/                    серверные процессы
│  └─ room_manager.py         менеджер комнат: load_mode, спавн сессий (windows_launch),
│                             монитор (конец матча + тишина UDP → новая сессия, idle),
│                             HTTP-API 18080, регистрация комнат в лобби
├─ server/directory/          ← импортируется эндпоинтом (см. §3)
│
├─ tools/                     скрипты запуска и инструменты
│  ├─ serve_all_2022.py       запуск3 служеб в одном процессе-надзорщике
│  ├─ roe_accounts.py         HTTP-аккаунты (регистрация/логин, users/ + accounts/)
│  ├─ lobby_service.py        лобби: TCP 8001 (протокол входа) + REST 8010
│  ├─ windows_launch.py       лаунчер сессии: materialize конфигов, firewall,
│  │                          телеметрия-off, запуск run_service.py endpoint
│  ├─ run_service.py          диспетчер+обвязка: endpoint → game_endpoint_probe_2022,
│  │                          proxy → heartbeat_probe_2022 (sys.path + компактный Capture)
│  ├─ heartbeat_probe_2022.py TCP-фронт комнаты (proxy): логин/хендшейк, -uid=,
│  │                          JOIN_INSTANCE, сообщения кастомных комнат0x737x
│  ├─ play_client.ps1         запуск Europa_Client.exe с -uid из users/registry.json
│  ├─ bootstrap.ps1           установка зависимостей + полный запуск (play.cmd)
│  ├─ ensure_firewall.ps1 / telemetry_switch.ps1   изоляция игры, отключение телеметрии
│  ├─ extract_map_points_2022.py   выгрузка точек лута из SFC → map-data/
│  ├─ extract_bornpos_2022.py      выгрузка сеток высадки (BlockBornPosTable) + срезы техники
│  ├─ build_loot_pools_2022.py     сборка modes/common/loot-pools.json
│  ├─ build_spawn_loot_2022.py     генерация статических каталогов лута у спавна
│  ├─ roe_custom_room_2022.py  (отложено) обработчики кастомных комнат0x737x
│  └─ …                        protocol-фикстуры, косметика, отчёты (62 .py)
│
├─ modes/<режим>/             один папка = один режим карты (dion, europa, vera, fdtd, common)
│  ├─ mode.json               map.id, launcher_args (в т.ч. переключатель лута),
│  │                          weather, local_spawn, room.idle_reset_seconds, features
│  ├─ spawn_points*.json      сетка высадки [cellX, cellY, x, y, height] + default_cell
│  ├─ doors-*.json / breakables-*.json   каталоги дверей/окон (accept_unknown для europa/vera)
│  └─ config/                 scene-cycle.json, scene-walk.json и пр. фикстуры сцены
│
├─ config/                    общие фикстуры лаунчера: join/room/weapon-*/target-*/parcel,
│                             environment, cosmetics, endless.json, ballistic-*, loot-*.json
├─ config/services/           accounts.json, lobby.json, room.json (порты3 служб)
│
├─ map-data/                  выгруженные оригинальные таблицы:
│                             <map>-entitypoints.json (лут), <map>-bornpos.json (сетки),
│                             <map>-vehiclepoints.json (техника)
├─ protocol/                  объяснения анализа протокола и поведения сервера:
│                             LOBBY-PROTOCOL, LOBBY-SERVICE, MAP-POINTS, ITEMS-2022 (+csv),
│                             HIT-*, SESSION-RESULT, LOOT-SURFACE, TERRAIN-HEIGHTFIELD,
│                             client_message_names.tsv (таблица опкодов) и др.
├─ rooms/<комната>/sessions/<id>/   артефакты сессии (создаются при работе):
│                             launcher/endpoint.log, packets.log, scene/events.jsonl,
│                             runtime-loot-catalog.json, сгенерированные конфиги
├─ lobby/<запуск>/            журналы лобби (создаются при работе)
├─ runtime/                   логи служб (runtime/services/*.log), state
├─ accounts/ / users/         локальные аккаунты и реестр uid (users/registry.json)
├─ private/                   ключи нашего эмулятора (candidate-001.key, lobby-ck.bin)
├─ .tools/                    локальный Python40МБ + client-path.txt
├─ tests/                     86 файлов: python -m unittest discover -s tests (678 тестов)
└─ runs/                      каталоги legacy-запусков (bootstrap)
```

Не переносилось намеренно: `some_RE_data/` (архив исследований), `captures/`,
`proto_analysis/` (пустой), журналы/бэкапы сессий, `AGENTS.md`, `TODO.txt`
(замещён `TODO.md`). Права: `RIGHTS.md`, `.gitignore`, `.gitattributes`. `SOURCE-MANIFEST.json` удалён
(функции для сервера не выполнял, ссылки вырезаны из `windows_launch.py`/`export_test_report_2022.py`).

## 3. Эндпоинт (`server/directory/`) — внутренняя структура

`game_endpoint_probe_2022.py` — диспетчер UDP: фазы handshake/ident/grant/auth,
шаблон комнаты, сцена, затем игровые сообщения.

| Группа | Модули | Что делает |
|---|---|---|
| Ядро | `listener.py`, `reliable_udp_2022.py` | журнал пакетов (Capture), надёжный UDP |
| Инвентарь/оружие | `weapon_probe_2022.py`, `inventory_codec_2022.py`, `attachment_probe_2022.py` | слоты, магазины, подбор с учётом веса рюкзака, кодировка предметов |
| Выбор старта | `winter_selection_2022.py` + `winter_spawn_points_2022.json` | BORN_POS_REQ/SYNC (сетка клеток), выбор способности/комплекта |
| Лут | `loot_catalog_2022.py`, `loot_runtime_2022.py` | загрузка каталога (статический или рантайм-генерация), выдача по близости |
| Двери/окна | `door_state_2022.py`, `breakable_state_2022.py` | состояния дверей, разрушение окон/пробиваемых объектов |
| Мир | `world_probe_2022.py`, `region_index_2022.py`, `match_result_2022.py`, `match_statistics_2022.py`, `environment_probe_2022.py` | HP/урон, зоны, итог матча, статистика, погода/время |
| Транспорт | `vehicle_probe_2022.py`, `shared_vehicle_2022.py` | машины/лодки, общие места/владение |
| Мультипир | `peer_avatar_2022.py`, `peer_motion_2022.py`, `peer_lifecycle_2022.py`, `peer_equipment_2022.py`, `peer_spectator_2022.py`, `shared_*` | аватары, синхронизация, общий лут/бой/эвакуация |
| Бой | `ballistics_2022.py`, `hit_feedback_2022.py`, `shoot_target_records_2022.py`, `projectile_materials_2022.py`, `shared_combat_2022.py` | баллистика, отметки попаданий, мишень |
| Прочее | `medical_probe_2022.py`, `throwable_*`, `parcel_*`, `death_parcel_2022.py`, `cosmetic_selection_2022.py`, `room_cosmetics_2022.py`, `map_profiles_2022.py`, `state_scene_actions_2022.py`, `live_scene_probe_2022.py`, `actor_probe_2022.py`, `bot_controller_2022.py`, `collision_*`, `ground_route_2022.py`, `movement_validation_2022.py`, `lobby_login_2022.py` | аптечки/гранаты/посылки/смерть, косметика, карта-профили, сцена, боты, коллизии, валидация движения |

## 4. Данные режима и где что лежит

- **Точки высадки**: `map-data/*-bornpos.json` (BlockBornPosTable из `SFC/Common.sfc`)
  → `modes/<мап>/spawn_points*.json` → `--spawn-points` → `winter_selection_2022`.
- **Точки лута**: `map-data/*-entitypoints.json` (ENTITYPOINTCONFIG) →
  `--loot-points` → `loot_runtime_2022.build_catalog()` → `runtime-loot-catalog.json`
  в сессии → `loot_catalog_2022.LootCatalog.load`. Переключатель в `mode.json`:
  `--loot-generation runtime` (основной) или `--loot-catalog <файл>` (исключительный).
- **Пулы предметов**: `modes/common/loot-pools.json` (сборка `tools/build_loot_pools_2022.py`).
- **Веса генерации**: `modes/<мап>/loot-weights.json` (`--loot-weights`) — шанс
  появления предмета на точке; default 1.0, патроны 0.1; компаньоны-паки
  появившегося оружия вес не проверяют (`loot_runtime_2022.load_weights`).
- **Машины в точках**: `map-data/<мап>-vehiclepoints.json` (`--vehicle-points`,
  `--vehicle-count`, `--vehicle-configs`, только europa) → `tools/vehicle_points_2022.py`
  → дополнительные 0x654B-ответы в scene-walk/scene-cycle (случайные точки,
  случайный тип из пула; проверены 102 jeep / 109 snowmotor; вертолёт 104Б/cfg6,
  лодка 87Б/cfg7 и 117Б/cfg501 — шаблоны есть, точки/проверка нужны).
- **Двери/окна**: `modes/<мап>/doors-*.json`, `breakables-*.json` → `--door-config`/`--breakable-config`.

## 5. Проверки

```
.tools\python\python.exe -X utf8 -B -m unittest discover -s tests
```

86 файлов, 678 тестов. Известные исключения (без установленного клиента):
`test_reset_local_2022` (6), `test_select_client_2022` (1).
