"""Constants for Dreame Smart Cut Height."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "dreame_smart_cut_height"
PLATFORMS = ["sensor", "switch", "number", "button"]

# How often the weather is fetched and the plan recalculated.
UPDATE_INTERVAL = timedelta(minutes=30)
# How often the mowing calendar is checked for the pre-mow check and the apply.
TICK_INTERVAL = timedelta(seconds=30)
CALENDAR_CACHE = timedelta(minutes=4)
CALENDAR_LOOKAHEAD = timedelta(days=10)

CHECK_BEFORE = timedelta(hours=1)   # read heights and ask this long before a mow
APPLY_BEFORE = timedelta(minutes=5)  # write the heights this long before a mow
DOCKED_FOR = timedelta(minutes=2)    # a queued change waits for the mower to sit docked this long
READ_BACK_DELAY = 120                # seconds to wait after a write before reading it back
SELECT_TIMEOUT = 30                  # seconds to wait for a select or a zone height to settle
SKIP_FOR = timedelta(days=2)

STORAGE_VERSION = 1

# Config entry keys: the mower.
CONF_MOWER = "mower"
CONF_DOCKED = "docked"
CONF_CALENDAR = "calendar"
CONF_MAP_SELECT = "map_select"
CONF_MAP_OPTION = "map_option"
CONF_ZONE_SELECT = "zone_select"
CONF_ZONE_HEIGHT = "zone_height"
CONF_NOTIFY = "notify_service"
CONF_ZONES = "zones"

# Config entry keys: weather and garden sources.
CONF_WEATHER = "weather"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_STATION_TEMP = "station_temperature"
CONF_STATION_RAIN = "station_rain"
CONF_LOCAL_RAIN = "local_rain_24h"
CONF_BUCKET = "water_balance"
CONF_WARNINGS = "warnings"

MOWER_KEYS = (CONF_DOCKED, CONF_CALENDAR, CONF_MAP_SELECT, CONF_MAP_OPTION,
              CONF_ZONE_SELECT, CONF_ZONE_HEIGHT, CONF_NOTIFY)
WEATHER_KEYS = (CONF_WEATHER, CONF_LATITUDE, CONF_LONGITUDE, CONF_STATION_TEMP,
                CONF_STATION_RAIN, CONF_LOCAL_RAIN, CONF_BUCKET, CONF_WARNINGS)
OPTIONAL_KEYS = (CONF_CALENDAR, CONF_MAP_SELECT, CONF_MAP_OPTION, CONF_NOTIFY, CONF_WEATHER,
                 CONF_STATION_TEMP, CONF_STATION_RAIN, CONF_LOCAL_RAIN, CONF_BUCKET,
                 CONF_WARNINGS)

# Phone notification buttons. Distinct from the old YAML package's CUT_HEIGHT_* actions so
# the two never answer the same tap while you migrate.
ACTION_APPLY = "DREAME_CUT_HEIGHT_APPLY_NOW"
ACTION_SKIP = "DREAME_CUT_HEIGHT_SKIP"
NOTIFY_TAG = "dreame_cut_height"

DEFAULT_BASELINE = 3.5

# key: (name, min, max, step, unit). Defaults come from plan.DEFAULTS.
TUNABLES = {
    "grow": ("Growing season from", 15, 30, 0.5, "°C"),
    "heavy_rain": ("Heavy rain from", 5, 150, 5, "mm"),
    "hot_max": ("Hot day from", 28, 42, 0.5, "°C"),
    "t95": ("Heatwave 3-day mean from", 24, 36, 0.5, "°C"),
    "dry_bucket": ("Dry at water balance", -60, 0, 1, "mm"),
    "dry_deficit": ("Dry-spell deficit from", 20, 150, 5, "mm"),
    "rain_offset": ("After heavy rain", -2, 0, 0.5, "cm"),
    "hot_offset": ("Heat or dry spell", 0, 2, 0.5, "cm"),
    "wave_offset": ("Heatwave", 0, 3, 0.5, "cm"),
    "dry_season_offset": ("Dry season", 0, 2, 0.5, "cm"),
}

# Helpers from the earlier YAML package. Read once, on the first start, so the switch-over
# keeps your settings and the plan's memory (latches, last lowering, anything pending).
LEGACY_TUNABLES = {
    "grow": "input_number.cut_height_grow_temp",
    "heavy_rain": "input_number.cut_height_heavy_rain",
    "hot_max": "input_number.cut_height_hot_max_temp",
    "t95": "input_number.cut_height_heatwave_temp",
    "dry_bucket": "input_number.cut_height_dry_bucket",
    "dry_deficit": "input_number.cut_height_dry_deficit",
    "rain_offset": "input_number.cut_height_rain_offset",
    "hot_offset": "input_number.cut_height_hot_offset",
    "wave_offset": "input_number.cut_height_heatwave_offset",
    "dry_season_offset": "input_number.cut_height_dry_season_offset",
}
LEGACY_BASELINE = "input_number.cut_height_baseline_zone_{}"
LEGACY_MANAGE = "input_boolean.cut_height_manage_zone_{}"
LEGACY_STATE = {
    "dry": "input_boolean.cut_height_dry_spell",
    "rain_until": "input_datetime.cut_height_rain_until",
    "heat_until": "input_datetime.cut_height_heat_until",
    "wave_until": "input_datetime.cut_height_heatwave_until",
    "last_lower": "input_datetime.cut_height_last_lower",
    "skip_until": "input_datetime.cut_height_skip_until",
}
LEGACY_PENDING = "input_text.cut_height_pending"
