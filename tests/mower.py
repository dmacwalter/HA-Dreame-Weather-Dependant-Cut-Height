"""A fake Dreame mower, mowing calendar and phone for the integration tests."""
from __future__ import annotations

from datetime import date, timedelta

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from custom_components.dreame_smart_cut_height.const import (
    CONF_BUCKET, CONF_CALENDAR, CONF_DOCKED, CONF_LATITUDE, CONF_LOCAL_RAIN, CONF_LONGITUDE,
    CONF_MAP_OPTION, CONF_MAP_SELECT, CONF_MOWER, CONF_NOTIFY, CONF_STATION_RAIN,
    CONF_STATION_TEMP, CONF_WARNINGS, CONF_WEATHER, CONF_ZONE_HEIGHT, CONF_ZONE_SELECT, CONF_ZONES,
)
from custom_components.dreame_smart_cut_height.zones import zone_id

MOWER = "lawn_mower.a1"
DOCKED = "binary_sensor.a1_docked"
CALENDAR = "calendar.a1_schedule"
MAP = "select.a1_map"
ZONE = "select.a1_zone"
HEIGHT = "number.a1_selected_zone_mowing_height"
NOTIFY = "notify.mobile_app_phone"
ZONE_OPTIONS = ["Raised Lawn (#1)", "Orchard (#2)", "Front Yard (#3)", "Nature Strip (#4)"]
MAP_OPTIONS = ["Front (#1)", "Back Yard (#2)"]

ENTRY_DATA = {
    CONF_MOWER: MOWER, CONF_DOCKED: DOCKED, CONF_CALENDAR: CALENDAR, CONF_MAP_SELECT: MAP,
    CONF_MAP_OPTION: "Back Yard (#2)", CONF_ZONE_SELECT: ZONE, CONF_ZONE_HEIGHT: HEIGHT,
    CONF_NOTIFY: NOTIFY,
    CONF_ZONES: [{"id": 1, "name": "Raised Lawn"}, {"id": 2, "name": "Orchard"},
                 {"id": 3, "name": "Front Yard"}, {"id": 4, "name": "Nature Strip"}],
    CONF_WEATHER: None, CONF_LATITUDE: -19.25, CONF_LONGITUDE: 146.79, CONF_STATION_TEMP: None,
    CONF_STATION_RAIN: None, CONF_LOCAL_RAIN: None, CONF_BUCKET: None, CONF_WARNINGS: None,
}


def open_meteo(today: date, hot: bool = False) -> dict:
    """21 past days, today and 5 ahead of mild wet-season weather; hot adds a 35 °C day."""
    days = [(today + timedelta(days=k - 21)).isoformat() for k in range(27)]
    tmax = [31.0] * 27
    if hot:
        tmax[22] = 35.0
    return {"daily": {
        "time": days,
        "temperature_2m_mean": [27.0] * 27,
        "temperature_2m_max": tmax,
        "temperature_2m_min": [22.0] * 27,
        "precipitation_sum": [2.0] * 27,
        "et0_fao_evapotranspiration": [4.0] * 27,
    }}


class FakeMower:
    def __init__(self, hass: HomeAssistant, heights: dict[int, float]) -> None:
        self.hass = hass
        self.heights = dict(heights)
        self.writes: list[dict] = []
        self.notifications: list[dict] = []
        self.events: list[dict] = []
        self.fail_write = False

    def install(self, docked: bool = True) -> None:
        hass = self.hass
        hass.states.async_set(MOWER, "docked")
        hass.states.async_set(DOCKED, "on" if docked else "off")
        hass.states.async_set(MAP, "Front (#1)", {"options": MAP_OPTIONS})
        hass.states.async_set(ZONE, "Orchard (#2)", {"options": ZONE_OPTIONS})
        self._show(2)
        hass.services.async_register("select", "select_option", self._select)
        hass.services.async_register("dreame_lawn_mower", "plan_zone_mowing_preference_update", self._write)
        hass.services.async_register("notify", NOTIFY.split(".")[1], self._notify)
        hass.services.async_register("calendar", "get_events", self._get_events,
                                     supports_response=SupportsResponse.ONLY)

    def _show(self, zid: int) -> None:
        self.hass.states.async_set(HEIGHT, self.heights[zid], {"selected_zone_id": zid})

    async def _select(self, call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        entity_id = entity_id[0] if isinstance(entity_id, list) else entity_id
        old = self.hass.states.get(entity_id)
        self.hass.states.async_set(entity_id, call.data["option"], old.attributes)
        if entity_id == ZONE:
            self._show(zone_id(call.data["option"]))

    async def _write(self, call: ServiceCall) -> None:
        if self.fail_write:
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError("cloud error")
        self.writes.append(dict(call.data))
        zid = int(call.data["zone_id"])
        self.heights[zid] = float(call.data["mowing_height_cm"])
        if self.hass.states.get(HEIGHT).attributes.get("selected_zone_id") == zid:
            self._show(zid)

    async def _notify(self, call: ServiceCall) -> None:
        self.notifications.append(dict(call.data))

    async def _get_events(self, call: ServiceCall):
        return {CALENDAR: {"events": self.events}}

    def dock(self, on: bool) -> None:
        self.hass.states.async_set(DOCKED, "on" if on else "off")
