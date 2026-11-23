"""Set-up, options, the scheduler and the guarded writes, against a fake mower."""
from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.dreame_smart_cut_height.const import (
    ACTION_APPLY, ACTION_SKIP, CONF_LOCAL_RAIN, CONF_WEATHER, CONF_ZONES, DOMAIN,
)

from .mower import (
    CALENDAR, DOCKED, ENTRY_DATA, HEIGHT, MAP, MOWER, NOTIFY, ZONE, FakeMower, open_meteo,
)

from custom_components.dreame_smart_cut_height.coordinator import OPEN_METEO

START = "2026-12-10 08:00:00+10:00"


@pytest.fixture(autouse=True)
def no_read_back_wait(monkeypatch):
    monkeypatch.setattr("custom_components.dreame_smart_cut_height.coordinator.READ_BACK_DELAY", 0)


async def _setup(hass: HomeAssistant, aioclient_mock, freezer, *, hot=True, heights=None,
                 legacy=None, docked=True):
    freezer.move_to(START)
    await hass.config.async_set_time_zone("Australia/Brisbane")
    aioclient_mock.get(OPEN_METEO, json=open_meteo(dt_util.now().date(), hot))
    mower = FakeMower(hass, heights or {1: 3.5, 2: 4.5, 3: 3.5, 4: 4.5})
    mower.install(docked=docked)
    for entity_id, value in (legacy or {}).items():
        hass.states.async_set(entity_id, value)
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=MOWER, title="Smart cut height")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, mower


async def _switch(hass, entity_id, on=True):
    await hass.services.async_call("switch", "turn_on" if on else "turn_off",
                                   {"entity_id": entity_id}, blocking=True)


async def _press(hass, entity_id):
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)


def _event(start):
    return {"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), "summary": "Mow"}


MANAGE_RAISED_LAWN = {
    "input_boolean.cut_height_manage_zone_1": "on",
    "input_boolean.cut_height_manage_zone_2": "off",
}


async def test_setup_creates_entities_and_adopts_the_old_package(hass, aioclient_mock, freezer):
    entry, _ = await _setup(hass, aioclient_mock, freezer, legacy={
        **MANAGE_RAISED_LAWN,
        "input_number.cut_height_baseline_zone_2": "5.0",
        "input_number.cut_height_hot_max_temp": "33",
        "input_datetime.cut_height_last_lower": "2026-12-01",
    })
    assert entry.state is ConfigEntryState.LOADED
    states = hass.states
    assert states.get("switch.smart_cut_height").state == "off"
    assert states.get("switch.smart_cut_height_write_to_mower").state == "off"
    assert states.get("switch.smart_cut_height_raised_lawn_smart_control").state == "on"
    assert states.get("switch.smart_cut_height_orchard_smart_control").state == "off"
    assert states.get("number.smart_cut_height_orchard_usual_height").state == "5.0"
    assert states.get("number.smart_cut_height_hot_day_from").state == "33.0"
    assert states.get("sensor.smart_cut_height_weather_plan").state == "heat"
    assert states.get("sensor.smart_cut_height_raised_lawn_target_height").state == "4.0"
    assert states.get("sensor.smart_cut_height_managed_zones").state == "Raised Lawn"
    assert states.get("sensor.smart_cut_height_next_change").attributes["last_lower"] == "2026-12-01"
    assert states.get("button.smart_cut_height_check_now") is not None


async def test_settings_change_the_plan_without_a_weather_fetch(hass, aioclient_mock, freezer):
    await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    calls = aioclient_mock.call_count
    await hass.services.async_call("number", "set_value", {
        "entity_id": "number.smart_cut_height_raised_lawn_usual_height", "value": 4.5}, blocking=True)
    assert hass.states.get("sensor.smart_cut_height_raised_lawn_target_height").state == "5.0"
    await hass.services.async_call("number", "set_value", {
        "entity_id": "number.smart_cut_height_hot_day_from", "value": 36}, blocking=True)
    assert hass.states.get("sensor.smart_cut_height_weather_plan").state == "normal"
    assert aioclient_mock.call_count == calls


async def test_check_now_previews_only_and_restores_the_selection(hass, aioclient_mock, freezer):
    _, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    await _press(hass, "button.smart_cut_height_check_now")
    assert hass.states.get("sensor.smart_cut_height_next_change").state == "Raised Lawn 3.5 → 4.0 cm"
    note = mower.notifications[-1]
    assert "Preview only" in note["message"] and "actions" not in note["data"]
    assert mower.writes == []
    assert hass.states.get(ZONE).state == "Orchard (#2)"
    assert hass.states.get(MAP).state == "Front (#1)"
    with pytest.raises(Exception, match="Write to mower"):
        await _press(hass, "button.smart_cut_height_apply_now")


async def test_scheduled_check_then_apply_before_the_mow(hass, aioclient_mock, freezer):
    entry, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    c = entry.runtime_data
    await _switch(hass, "switch.smart_cut_height")
    await _switch(hass, "switch.smart_cut_height_write_to_mower")
    start = dt_util.now() + timedelta(minutes=50)
    mower.events = [_event(start)]
    await c._async_tick()
    assert c.state["pending"] == [{"id": 1, "name": "Raised Lawn", "from": 3.5, "to": 4.0}]
    assert c.state["pending_for"] is not None
    assert c.state["heat_until"] > "2026-12-10"   # the plan's memory is saved at the check
    note = mower.notifications[-1]
    assert "Happens at 08:45" in note["message"]
    assert [a["action"] for a in note["data"]["actions"]] == [ACTION_APPLY, ACTION_SKIP]
    await c._async_tick()                          # same event: no second check
    assert len(mower.notifications) == 1

    freezer.move_to(start - timedelta(minutes=4))
    c._events_at = None
    await c._async_tick()
    assert mower.writes == [{"entity_id": MOWER, "zone_id": 1, "mowing_height_cm": 4.0,
                             "execute": True, "confirm_preference_write": True}]
    assert c.state["pending"] == [] and c.state["last_error"] is None
    assert hass.states.get("sensor.smart_cut_height_next_change").state == "None pending"


async def test_a_manual_preview_is_not_applied_by_the_schedule(hass, aioclient_mock, freezer):
    entry, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN,
                                heights={1: 4.0, 2: 4.5, 3: 3.5, 4: 4.5})
    c = entry.runtime_data
    await _switch(hass, "switch.smart_cut_height")
    await _switch(hass, "switch.smart_cut_height_write_to_mower")
    start = dt_util.now() + timedelta(minutes=50)
    mower.events = [_event(start)]
    await c._async_tick()                          # scheduled check: already 4.0, nothing pending
    assert c.state["pending"] == []
    mower.heights[1] = 3.5                         # changed in the Dreame app afterwards
    await _press(hass, "button.smart_cut_height_check_now")
    assert c.state["pending"] and c.state["pending_for"] is None
    freezer.move_to(start - timedelta(minutes=4))
    c._events_at = None
    await c._async_tick()
    assert mower.writes == []
    await _press(hass, "button.smart_cut_height_apply_now")
    assert len(mower.writes) == 1


async def test_apply_waits_for_the_mower_to_sit_docked(hass, aioclient_mock, freezer):
    entry, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN, docked=False)
    c = entry.runtime_data
    await _switch(hass, "switch.smart_cut_height_write_to_mower")   # master stays off
    await _press(hass, "button.smart_cut_height_check_now")
    await _press(hass, "button.smart_cut_height_apply_now")
    assert mower.writes == [] and c.state["apply_due"] is True
    mower.dock(True)
    await c._async_tick()
    assert mower.writes == []
    freezer.tick(timedelta(minutes=3))
    await c._async_tick()
    assert len(mower.writes) == 1 and c.state["apply_due"] is False


async def test_a_height_changed_since_the_check_is_not_overwritten(hass, aioclient_mock, freezer):
    entry, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    await _switch(hass, "switch.smart_cut_height_write_to_mower")
    await _press(hass, "button.smart_cut_height_check_now")
    mower.heights[1] = 3.0
    await _press(hass, "button.smart_cut_height_apply_now")
    assert mower.writes == []
    assert "changed since the check" in entry.runtime_data.state["last_error"]
    assert "Couldn't set" in mower.notifications[-1]["message"]


async def test_failed_write_is_reported(hass, aioclient_mock, freezer):
    entry, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    await _switch(hass, "switch.smart_cut_height_write_to_mower")
    await _press(hass, "button.smart_cut_height_check_now")
    mower.fail_write = True
    await _press(hass, "button.smart_cut_height_apply_now")
    assert "write failed" in entry.runtime_data.state["last_error"]


async def test_phone_buttons(hass, aioclient_mock, freezer):
    entry, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    c = entry.runtime_data
    await _switch(hass, "switch.smart_cut_height_write_to_mower")
    await _press(hass, "button.smart_cut_height_check_now")
    # Master off: taps are ignored. The old package's action names are always ignored.
    hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION_APPLY})
    await _switch(hass, "switch.smart_cut_height")
    hass.bus.async_fire("mobile_app_notification_action", {"action": "CUT_HEIGHT_APPLY_NOW"})
    await hass.async_block_till_done()
    assert mower.writes == []
    hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION_APPLY})
    await hass.async_block_till_done()
    assert len(mower.writes) == 1

    await _press(hass, "button.smart_cut_height_check_now")
    hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION_SKIP})
    await hass.async_block_till_done()
    assert c.state["pending"] == [] and c.state["skip_until"]


async def test_a_skip_holds_the_scheduled_check(hass, aioclient_mock, freezer):
    entry, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    c = entry.runtime_data
    await _switch(hass, "switch.smart_cut_height")
    await _press(hass, "button.smart_cut_height_skip_2_days")
    mower.events = [_event(dt_util.now() + timedelta(minutes=50))]
    await c._async_tick()
    assert c.state["pending"] == [] and mower.notifications == []
    assert c.state["heat_until"] > "2026-12-10"


async def test_services(hass, aioclient_mock, freezer):
    entry, mower = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    result = await hass.services.async_call(DOMAIN, "check", {}, blocking=True, return_response=True)
    assert result["pending"][0]["to"] == 4.0
    with pytest.raises(Exception, match="confirm"):
        await hass.services.async_call(DOMAIN, "apply", {"confirm": False}, blocking=True)
    await _switch(hass, "switch.smart_cut_height_write_to_mower")
    result = await hass.services.async_call(DOMAIN, "apply", {"confirm": True}, blocking=True,
                                            return_response=True)
    assert result == {"result": "applied"} and len(mower.writes) == 1


async def test_weather_sources_station_and_forecast(hass, aioclient_mock, freezer):
    """Station history replaces past temperatures and rain; the forecast replaces ahead."""
    from homeassistant.core import SupportsResponse
    freezer.move_to(START)
    await hass.config.async_set_time_zone("Australia/Brisbane")
    today = dt_util.now().date()
    seen = {}

    async def forecasts(call):
        return {"weather.home": {"forecast": [
            {"datetime": (today + timedelta(days=k)).isoformat() + "T00:00:00+10:00",
             "temperature": 36.0 if k == 1 else 31.0, "templow": 23.0} for k in range(5)]}}

    async def statistics(call):
        seen.update(call.data)
        start = dt_util.start_of_local_day(today - timedelta(days=3))
        rows = [{"start": dt_util.as_utc(start + timedelta(days=k)).isoformat(),
                 "max": 30.0, "min": 24.0, "mean": 27.0} for k in range(3)]
        rain = [{"start": r["start"], "change": 40.0 if k == 2 else 0.0} for k, r in enumerate(rows)]
        return {"statistics": {"sensor.station_temp": rows, "sensor.station_rain": rain}}

    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)
    hass.services.async_register("recorder", "get_statistics", statistics, supports_response=SupportsResponse.ONLY)
    aioclient_mock.get(OPEN_METEO, json=open_meteo(today, hot=False))
    FakeMower(hass, {1: 3.5, 2: 4.5, 3: 3.5, 4: 4.5}).install()
    data = {**ENTRY_DATA, CONF_WEATHER: "weather.home", "station_temperature": "sensor.station_temp",
            "station_rain": "sensor.station_rain"}
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id=MOWER, title="Smart cut height")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    plan = hass.states.get("sensor.smart_cut_height_weather_plan")
    assert plan.state == "heat"                         # 36 °C tomorrow, from the forecast only
    assert plan.attributes["station_days"] == 3 and plan.attributes["forecast_days"] == 5
    assert plan.attributes["rain3"] == 42.0               # 0 + 40 from the station, today from Open-Meteo
    assert seen["types"] == ["max", "min", "mean", "change"]


async def test_config_flow_finds_the_mower_entities(hass, aioclient_mock):
    aioclient_mock.get(OPEN_METEO, json=open_meteo(dt_util.now().date()))
    dreame = MockConfigEntry(domain="dreame_lawn_mower")
    dreame.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=dreame.entry_id,
                                                    identifiers={("dreame_lawn_mower", "a1")}, name="A1")
    registry = er.async_get(hass)
    for entity_id, name in [(MOWER, None), (DOCKED, "Docked"), (CALENDAR, "Schedule"),
                            ("calendar.a1_all_schedules", "All Schedules"), (MAP, "Map"),
                            (ZONE, "Zone"), (HEIGHT, "Selected Zone Mowing Height"),
                            ("number.a1_selected_map_mowing_height", "Selected Map Mowing Height")]:
        domain, object_id = entity_id.split(".")
        registry.async_get_or_create(domain, "dreame_lawn_mower", object_id, device_id=device.id,
                                     suggested_object_id=object_id, original_name=name,
                                     config_entry=dreame)
    FakeMower(hass, {1: 3.5, 2: 4.5, 3: 3.5, 4: 4.5}).install()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"mower": MOWER})
    assert result["step_id"] == "mower"
    suggested = {str(k): k.description["suggested_value"] for k in result["data_schema"].schema
                 if k.description}
    assert suggested == {"docked": DOCKED, "zone_select": ZONE, "zone_height": HEIGHT,
                         "map_select": MAP, "calendar": CALENDAR}
    result = await hass.config_entries.flow.async_configure(result["flow_id"],
                                                            {**suggested, "notify_service": NOTIFY})
    assert result["step_id"] == "map"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"map_option": "Back Yard (#2)"})
    assert result["step_id"] == "weather"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"latitude": -19.25, "longitude": 146.79})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_ZONES][0] == {"id": 1, "name": "Raised Lawn"} and len(data[CONF_ZONES]) == 4
    assert data["map_option"] == "Back Yard (#2)" and data[CONF_WEATHER] is None

    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    again = await hass.config_entries.flow.async_configure(again["flow_id"], {"mower": MOWER})
    assert again["type"] is FlowResultType.ABORT and again["reason"] == "already_configured"


async def test_config_flow_rejects_a_selector_without_zones(hass):
    FakeMower(hass, {1: 3.5, 2: 4.5, 3: 3.5, 4: 4.5}).install()
    hass.states.async_set("select.other", "a", {"options": ["a", "b"]})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"mower": MOWER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "docked": DOCKED, "zone_select": "select.other", "zone_height": HEIGHT})
    assert result["errors"] == {"zone_select": "no_zones"}


async def test_options_change_weather_sources_and_pick_up_renamed_zones(hass, aioclient_mock, freezer):
    entry, _ = await _setup(hass, aioclient_mock, freezer, legacy=MANAGE_RAISED_LAWN)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "weather"})
    assert result["step_id"] == "weather"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "latitude": -19.25, "longitude": 146.79, "local_rain_24h": "sensor.gauge_24h"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_LOCAL_RAIN] == "sensor.gauge_24h" and entry.options[CONF_WEATHER] is None
    assert entry.state is ConfigEntryState.LOADED

    hass.states.async_set(ZONE, "Orchard (#2)", {"options": ["Raised Lawn (#1)", "Orchard (#2)",
                                                             "Back Lawn (#5)"]})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "mower"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "docked": DOCKED, "zone_select": ZONE, "zone_height": HEIGHT, "map_select": MAP,
        "calendar": CALENDAR, "notify_service": NOTIFY})
    assert result["step_id"] == "map"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"map_option": "Back Yard (#2)"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert [z["id"] for z in entry.options[CONF_ZONES]] == [1, 2, 3, 4, 5]
    assert hass.states.get("switch.smart_cut_height_back_lawn_smart_control").state == "off"
    # Settings survive the reload.
    assert hass.states.get("switch.smart_cut_height_raised_lawn_smart_control").state == "on"


async def test_unload(hass, aioclient_mock, freezer):
    entry, _ = await _setup(hass, aioclient_mock, freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
