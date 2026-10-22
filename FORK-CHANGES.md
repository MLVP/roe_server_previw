# FORK-CHANGES — ROE-local-fork

Форк локального preservation-сервера Ring of Elysium 2022.  
Базовая копия: `F:\ROERevive\tools\ring-of-elysium-local-main\ring-of-elysium-local-main`.

## Что добавлено

- Файловый реестр пользователей `accounts_2022.py`.
- CLI `roe_accounts.py` и Windows-обёртки.
- HTTP-сервис регистрации `account_service.py` + тестовый клиент
  `register_client.py`.
- Патч ника в `ENTER_ROOM_RSP` (`profile.base.m014`).
- Патч ника команды через `--team-nickname`.
- Патч lobby-профиля 0x2ef включён по умолчанию (`--lobby-profile-name`,
  отключается `--no-lobby-profile-name`); именно он меняет видимый ник,
  который без патча равен `BRING_BACK_ROE!!`.
- Отпечаток свежего UDP-ключа в журнале (`session_key_generated`).
- Отдельный `cosmetics.json` на пользователя.
- Раздельный запуск: `serve-game.cmd` (только серверный стек) и
  `play-client.cmd` (только клиент).
- Настраиваемый таймер старта `-SelectionSeconds` (по умолчанию 47; 5..10 —
  чтобы быстро начать матч).
- Каталог лута по умолчанию — `config/loot-pool61.json` (подставляет
  `tools/bootstrap.ps1`; отключается `-NoLootCatalog`). Раньше `play.cmd` был
  зашит на диагностический `config/windows-smoke-20261015.json`.
- Режим `-Endless` и `config/endless.json`: зона не сжимается и не наносит
  урон, серверный timeout/result по смерти отключены. Обёртки
  `play-endless.cmd` и `serve-game-endless.cmd`.
- `-Duration` для Endless по умолчанию 7200 с; верхняя граница поднята до
  86400 с. `-SelectionSeconds` для Endless по умолчанию 7 с.

## Быстрый старт

```bat
cd /d F:\ROERevive\tools\ROE-local-fork
register-account.cmd alice --nickname Alice
register-account.cmd bob --nickname Bob
list-accounts.cmd
play-account.cmd alice
```

Раздельно сервер и клиент:

```bat
rem окно 1 - только серверный стек
serve-game.cmd alice -SelectionSeconds 7

rem окно 2 - только клиент
play-client.cmd
```

Бесконечный тестовый матч (без сжатия зоны и без завершения):

```bat
rem окно 1 - сервер, профиль awp
serve-game-endless.cmd awp -SelectionSeconds 7

rem окно 2 - клиент
play-client.cmd
```

Или всё сразу: `play-endless.cmd`. Подробнее — `F:\ROERevive\12_MATCH_TIMERS.md`.

Тестовый HTTP-клиент:

```bat
serve-accounts.cmd --port 8099
register-client.cmd --name carol --nickname Carol
register-client.cmd --list
```

## Данные

```
accounts/
  alice/
    account.json
    cosmetics.json
```

`account.json` содержит `name`, `nickname`, `actor_uid` (hex U64), даты,
`session_key_policy`. UID уникален; при коллизии автоматически прибавляется 4.
`default` сохраняет исторический UID `0x515BB1E1DD242C`.

## Ключи

- UDP-ключ игровой сессии: `os.urandom(16)` на каждый SYN (уже было); в журнал
  пишется только `sha256(key)[:16]`.
- Lobby TCP-ключ: фиксированный CK из C#-эмулятора; смена через CHGSKEY требует
  нестандартного TEA-кодека, в форке не включена.
- `private/candidate-001.key` и `private/lobby-ck.bin` не публиковать.

## Ограничения

- Не оригинальная авторизация/Steam; UID и инвентарь синтетические.
- Один lobby-эмулятор обслуживает одну сессию; одновременные клиенты на одних
  портах не поддерживаются.
- `--lobby-profile-name` включён по умолчанию; при проблемах в лобби отключите
  `-NoLobbyProfileName`.
- Не изменяйте `.exe`/`.dll` и не трогайте античит.

## Комната и режимы (`ROE_local_test_1`)

Эта копия добавляет поверх форка экспериментальный супервизор комнаты.

- `server/room_manager.py` — одна комната поверх существующего стека
  (`windows_launch.py --services-only`): лобби `9001`, прокси `8001`, UDP
  endpoint `18001`. Комната перезапускает стек, если 30 секунд нет пакетов
  игрока.
- `modes/<name>/mode.json` — режим: карта, аргументы лаунчера, погода,
  idle-reset, динамические события. Первый режим — `modes/dion` (карта 16010).
- `serve-room.cmd dion` — запуск супервизора, API на
  `http://127.0.0.1:18080/api/status` (только loopback, только GET).
- `rooms/<room>/sessions/<session>/` — папка сессии: `session.json`,
  `packets.log` (hex построчно с таймкодами), логи сервисов,
  `live-commands.json`.
- `server/directory/listener.py` (`Capture`) теперь всегда пишет `packets.log`
  рядом с `events.jsonl`, а при заданном `ROE_PACKET_LOG` дублирует поток в
  общий файл комнаты.
- `tools/heightmap_from_points_2022.py` — генератор 16-битной raw heightmap
  (4096×4096) из точек спавна; результат лежит в `modes/dion/`.
- `tools/windows_launch.py` — новые ключи `--map-id` (сейчас только 16010),
  `--instance-id` (идентификатор комнаты в `join.json`),
  `--config-overlay` (папка с настройками режима) и `--room-run-dir`.

Подробно: `F:\ROERevive\18_ROOM_SERVER_TEST1.md`, `modes/README.md`,
`rooms/README.md`.

## Подробная документация

`F:\ROERevive\09_LOCAL_SERVER_ACCOUNTS.md`, `F:\ROERevive\18_ROOM_SERVER_TEST1.md`

## Объединённый лобби и пользователи (`ROE_local_test_2`)

- Лобби и прокси — **один процесс Python** на `127.0.0.1:8001`. Отдельный
  лобби на C#/.NET (`server/lobby/LobbyEmulator.Sdk`) и рантайм `.tools/dotnet`
  удалены; базовая часть протокола перенесена в
  `server/directory/lobby_login_2022.py` (IT→SN, SA→ID+CK, DT→приветствие).
  Порт 9001 больше не используется.
- uid клиента (`-uid=`) читается из DT-кадра `0x2f0` (BE32 по смещению 42)
  и выдаёт личность из `users/registry.json`: `actor_uid` в `0x32b` и ник в
  `0x2ef`. Несколько игроков могут быть в лобби одновременно, у каждого своя
  личность и своё TCP-соединение.
- Справочник с исходниками C# переименован в `search_/` (в серверном коде
  C# не осталось; лицензия MIT и пояснение сохранены).
- `user.cmd` — менеджер пользователей: оба идентификатора (uid и
  actor uid), папка `accounts/<name>/` + `users/<name>/` и реестр
  `users/registry.json`. uid генерируется случайно.
- `lnroeuser.cmd` — генератор ярлыка клиента:
  `lnroeuser -uid [uid] -f [game folder] -o [shortcut path]`.
- `play-account.cmd <имя>` берёт uid пользователя из реестра.
- Подробности: `docs/LOBBY-SERVICE-2022.md`.
