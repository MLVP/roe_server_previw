# Vera (Desert) - map 16021

Пустынная карта ("Vera" в клиенте, мир `EU_Desert_4096`, сцена
`Desert_001`), id **16021**. Клиент грузит эту карту у себя; серверные
данные (зона, сцена, heightmap) остаются от Dione -
так же, как в режиме Kill Zone. Двери и breakables описываются
своими каталогами режима (см. ниже).

## Как запустить

```bat
rem переключить живую комнату на пустыню
curl "http://127.0.0.1:18080/api/mode?name=vera"

rem или в конфиге комнаты: "mode": "vera" в config/services/room.json
```

Игрок в лобби выбирает карту Vera (Normal -> карта Vera) - запрос
подбора приходит с id карты 16021, и лобби отдаёт именно пустынную
комнату (`0xd77` с `unknown_28 = 16021`).

## Где лежат координаты лута

Каталог лута - `modes/vera/loot-desert-64.json`: 64 предмета сеткой 8x8
с шагом 35 вокруг точки спауна. Позиции **генерируются** из точки спауна,
а не хранятся вручную:

```bat
.tools\python\python.exe tools\build_spawn_loot_2022.py ^
    --center 345746 341956 12779 --count 64 --map-id 16021 ^
    --catalog modes\vera\loot-desert-64.json ^
    --scene-source modes\dion\config\scene-cycle.json ^
    --scene modes\vera\config\scene-cycle.json ^
    --vehicles 102:300,109:-300
```

Тот же инструмент правит `modes/vera/config/scene-cycle.json`: добавляет
правило с двумя машинами (Jeep102 и SnowMotor109) в точке спауна.

## Точка спауна

**X 345746, Y(плоскость) 341956, Z(высота) 12779** - клетка [10, 10].

Взята из точек поверхности, извлечённых из клиентского архива
`Cache/Data/world/EU_Desert_4096/EU_Desert_4096.sfc` (в архиве 84354
записи; `modes/vera/desert_ground_points.json` - 19610 точек в порядке
x, z, height). Критерий выбора: ближе к центру карты и с самым ровным
окружением (6 соседей в радиусе 600, разброс высот 155).

Индекс клетки сетки 32x32 (0..31) для пустыни не восстановлен, в таблице
лежит одна точка - на любой запрос рождения клиент получит её.

## Настройки режима

| Поле | Значение |
|---|---|
| `map.id` | 16021 |
| `map.route` | `0:127.0.0.1:18001` |
| `weather.hours` | `[7, 8, 15, 16]` (таблица времени клиента для 16021) |
| `weather.temperatures` | `[-500, 0, 500]` (случайно) |
| `spawn_points` | `spawn_points.json` (одна точка) |
| `heightmap` | `../dion/heightmap_4096x4096_u16.raw` (общий с Dione) |
| `loot` | `loot-desert-64.json` (64 предмета в точке спауна) |
| `config` | `config/`: `environment.json` (карта 16021), `join.json`, `scene-cycle.json` (сцена Dione + 2 машины) |

Аргументы запуска (карта и час берутся из режима и оверлея):

```text
--kit glider --mode cycle --cycle-scale 3 --weapon-profile citori
--target armored --target-los off --selection-seconds 7
--reliable-udp --idle-handoff
--door-catalog doors-vera.json --breakable-catalog breakables-vera.json
--endless --auto-match-seconds 12
--loot-catalog loot-desert-64.json
```

## Двери и окна

На пустыне id сущностей выдаются при загрузке карты и меняются от
сессии к сессии, поэтому в `doors-vera.json` и `breakables-vera.json`
нет закреплённых id: стоит `accept_unknown: true`, состояния дверей
подтверждаются по запросу клиента, а прочность и число частей берутся
из первого запроса удара. Проверка дистанции включается только если
позиция сущности есть в каталоге.

## Что остаётся от профиля Dione

У пустыни своя местность, поэтому зона, границы опасности, двери,
breakables и heightmap не описывают её. Клиент карту грузит и матч
начинается, лут и машины стоят в локальной точке спауна, но вертолёт
эвакуации всё ещё использует зону Dione.
