# Room sessions

`server/room_manager.py` creates one folder per room session:

```text
rooms/<room-id>/sessions/<UTC-stamp>-<short-id>/
```

It contains:

- `session.json` — mode, map, weather, launch command, pid.
- `launcher.log`, `lobby.log`, `proxy.log`, `endpoint.log` — service logs.
- `packets.log` — shared lobby + game packets, one hex line per packet with
  UTC timestamp, kind, direction, transport and remote endpoint.
- `live-commands.json` — commands written by `GET /api/command`.
- `spawn-requests.jsonl` — queued loot/vehicle spawn requests from
  `GET /api/spawn/request` (recorded, not applied yet).
- `dynamic-events.jsonl` — disabled-by-default periodic event requests.
- the normal launcher `scene/`, `lobby/`, `wire/` and config output.

`rooms/` itself is runtime data, not source code.
