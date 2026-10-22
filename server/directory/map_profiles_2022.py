"""Карты EU (Europa) и локальный профиль данных.

Клиент 2022 грузит `SFC/World_EU_ICELAND_4096_RemainingFiles.sfc`, поэтому
все карты семейства EU_IceLand_* используют один и тот же ландшафт. Значит
профиль сервера (сетка точек спавна, зона, двери, разрушения, heightmap)
одинаков для всех id из ICELAND_MAPS — меняются только id карты в
`join.json` и режим времени суток.

Карты из EXPERIMENTAL_MAPS (Kill Zone, Desert) — другой ландшафт: клиент
их грузит, но серверные данные остаются от Dione. Так же поступает и чужой
лаунчер `tools/anotheruser_louncher` (crates/roe-core/src/maps.rs).

Часы суток взяты из клиентской таблицы EnvrMapTimeTable (индекс периода
EnvrTimeTable равен часу): 16010 и подобные — 7/8/15/16, 16011 — 0 (ночь).
"""
from __future__ import annotations

# id -> (world folder, config, mode)
ICELAND_MAPS = {
    10020: ('EU_IceLand_4096', 'IceLand_001', 'wild'),
    10021: ('EU_IceLandNight_4096', 'IceLandNight_01', 'wild night'),
    16008: ('EU_IceLand_4096', 'IceLand_002', 'plane start'),
    16010: ('EU_IceLand_4096', 'IceLand_001', 'point selection start'),
    16011: ('EU_IcelandNight_4096', 'IceLandNight_01', 'night mode'),
    16015: ('EU_IceLand_4096', 'IceLand_001', 'sniper event'),
    16016: ('EU_IceLand_4096', 'IceLand_001', 'HeatRush'),
    16030: ('EU_IceLand_4096', 'IceLand_001', 'warm match'),
}

# Other EU locations: own landscape, the server keeps the Dione data.
# 16007 is the Kill Zone ("EuropaKillZone" in the client tables).
EXPERIMENTAL_MAPS = {
    16007: ('EU_Killzone_4096', 'KillZone_001', 'kill zone'),
    16021: ('EU_Desert_4096', 'Desert_001', 'desert'),
}

# EnvrMapTimeTable: allowed hours per map.
MAP_HOURS = {
    16005: (8,),
    16007: (7, 8, 15, 16),
    16008: (7, 8, 15, 16),
    16009: (7, 8, 15, 16),
    16010: (7, 8, 15, 16),
    16011: (0,),
    16012: (7, 8, 15, 16),
    16014: (7, 8, 15, 16),
    16015: (7, 8, 15, 16),
    16016: (7, 8, 15, 16),
    16017: (7, 8, 15, 16),
    16020: (7, 8, 15, 16),
    16021: (7, 8, 15, 16),
    16022: (7, 8, 15, 16),
    16023: (7, 8, 15, 16),
    16024: (7, 8, 15, 16),
    16030: (7, 8, 15, 16),
    16031: (7, 8, 15, 16),
    16100: (8,),
}

DEFAULT_HOURS = (7, 8, 15, 16)


def has_local_profile(map_id):
    """True, если сервер умеет отдать комнату с этой картой."""
    try:
        return int(map_id) in ICELAND_MAPS or int(map_id) in EXPERIMENTAL_MAPS
    except (TypeError, ValueError):
        return False


def is_experimental(map_id):
    """True, если у карты свой ландшафт, а серверные данные от Dione."""
    try:
        return int(map_id) in EXPERIMENTAL_MAPS
    except (TypeError, ValueError):
        return False


def describe(map_id):
    try:
        value = int(map_id)
    except (TypeError, ValueError):
        return 'unknown map'
    entry = ICELAND_MAPS.get(value) or EXPERIMENTAL_MAPS.get(value)
    if entry is None:
        return 'unknown map'
    root, name, mode = entry
    return f'{root}/{name} ({mode})'


def allowed_hours(map_id):
    """Часы, которые клиентская таблица времени допускает для карты."""
    try:
        return MAP_HOURS.get(int(map_id), DEFAULT_HOURS)
    except (TypeError, ValueError):
        return DEFAULT_HOURS
