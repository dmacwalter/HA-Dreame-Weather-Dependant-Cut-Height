"""Set-up and options: the mower, its calendar and selectors, and the weather sources."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_BUCKET,
    CONF_CALENDAR,
    CONF_DOCKED,
    CONF_LATITUDE,
    CONF_LOCAL_RAIN,
    CONF_LONGITUDE,
    CONF_MAP_OPTION,
    CONF_MAP_SELECT,
    CONF_MOWER,
    CONF_NOTIFY,
    CONF_STATION_RAIN,
    CONF_STATION_TEMP,
    CONF_WARNINGS,
    CONF_WEATHER,
    CONF_ZONE_HEIGHT,
    CONF_ZONE_SELECT,
    CONF_ZONES,
    DOMAIN,
    OPTIONAL_KEYS,
    WEATHER_KEYS,
)
from .zones import zones_from_options

TITLE = "Smart cut height"


def _entity(domain: str, **kw) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain, **kw))


def _coordinate() -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=-180, max=180, step="any", mode=selector.NumberSelectorMode.BOX))


def _guess_mower_entities(hass: HomeAssistant, mower: str) -> dict[str, str]:
    """Find the docked sensor, schedule calendar, map and zone selectors and zone height
    among the mower's own entities (the Dreame lawn mower integration's names)."""
    registry = er.async_get(hass)
    mower_entry = registry.async_get(mower)
    if mower_entry is None or mower_entry.device_id is None:
        return {}
    entries = er.async_entries_for_device(registry, mower_entry.device_id)

    def find(domain: str, *names: str) -> str | None:
        wanted = [n.lower() for n in names]
        for entry in entries:
            if entry.domain != domain or entry.disabled_by:
                continue
            original = (entry.original_name or "").lower()
            if original in wanted:
                return entry.entity_id
        for entry in entries:
            if entry.domain != domain or entry.disabled_by:
                continue
            object_id = entry.entity_id.split(".", 1)[1]
            if any(object_id.rstrip("_0123456789").endswith(n.replace(" ", "_")) for n in wanted):
                return entry.entity_id
        return None

    found = {
        CONF_DOCKED: find("binary_sensor", "Docked"),
        CONF_CALENDAR: find("calendar", "Schedule"),
        CONF_MAP_SELECT: find("select", "Map"),
        CONF_ZONE_SELECT: find("select", "Zone"),
        CONF_ZONE_HEIGHT: find("number", "Selected Zone Mowing Height"),
    }
    return {k: v for k, v in found.items() if v}


def _notify_services(hass: HomeAssistant) -> list[str]:
    services = hass.services.async_services_for_domain("notify")
    return sorted(f"notify.{name}" for name in services
                  if name not in ("send_message", "persistent_notification"))


def _mower_schema(hass: HomeAssistant) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_DOCKED): _entity("binary_sensor"),
        vol.Required(CONF_ZONE_SELECT): _entity("select"),
        vol.Required(CONF_ZONE_HEIGHT): _entity("number"),
        vol.Optional(CONF_MAP_SELECT): _entity("select"),
        vol.Optional(CONF_CALENDAR): _entity("calendar"),
        vol.Optional(CONF_NOTIFY): selector.SelectSelector(selector.SelectSelectorConfig(
            options=_notify_services(hass), custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN)),
    })


def _map_schema(hass: HomeAssistant, map_select: str) -> vol.Schema:
    st = hass.states.get(map_select)
    options = list(st.attributes.get("options", [])) if st else []
    return vol.Schema({
        vol.Optional(CONF_MAP_OPTION): selector.SelectSelector(selector.SelectSelectorConfig(
            options=options, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)),
    })


WEATHER_SCHEMA = vol.Schema({
    vol.Optional(CONF_WEATHER): _entity("weather"),
    vol.Required(CONF_LATITUDE): _coordinate(),
    vol.Required(CONF_LONGITUDE): _coordinate(),
    vol.Optional(CONF_STATION_TEMP): _entity("sensor", device_class="temperature"),
    vol.Optional(CONF_STATION_RAIN): _entity("sensor"),
    vol.Optional(CONF_LOCAL_RAIN): _entity("sensor"),
    vol.Optional(CONF_BUCKET): _entity("sensor"),
    vol.Optional(CONF_WARNINGS): _entity("sensor"),
})


def _check_mower(hass: HomeAssistant, data: dict[str, Any], known: list | None) -> tuple[dict, dict]:
    """Errors for the mower step, and the zones found on the zone selector."""
    errors: dict[str, str] = {}
    st = hass.states.get(data.get(CONF_ZONE_SELECT, ""))
    zones = zones_from_options(st.attributes.get("options", []) if st else [], known)
    if not zones:
        errors[CONF_ZONE_SELECT] = "no_zones"
    return errors, {CONF_ZONES: zones}


def _cleared(data: dict[str, Any], keys) -> dict[str, Any]:
    """An optional field left empty is absent from the form's data: store None for it."""
    return {**{k: None for k in keys if k in OPTIONAL_KEYS}, **data}


class CutHeightConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_MOWER])
            self._abort_if_unique_id_configured()
            self._data[CONF_MOWER] = user_input[CONF_MOWER]
            return await self.async_step_mower()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_MOWER): _entity("lawn_mower"),
        }))

    async def async_step_mower(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, zones = _check_mower(self.hass, user_input, None)
            if not errors:
                self._data.update(_cleared(user_input, (CONF_MAP_SELECT, CONF_CALENDAR, CONF_NOTIFY)))
                self._data.update(zones)
                if self._data.get(CONF_MAP_SELECT):
                    return await self.async_step_map()
                self._data[CONF_MAP_OPTION] = None
                return await self.async_step_weather()
        suggested = user_input or _guess_mower_entities(self.hass, self._data[CONF_MOWER])
        return self.async_show_form(
            step_id="mower", errors=errors,
            data_schema=self.add_suggested_values_to_schema(_mower_schema(self.hass), suggested))

    async def async_step_map(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_MAP_OPTION] = user_input.get(CONF_MAP_OPTION)
            return await self.async_step_weather()
        st = self.hass.states.get(self._data[CONF_MAP_SELECT])
        return self.async_show_form(
            step_id="map",
            data_schema=self.add_suggested_values_to_schema(
                _map_schema(self.hass, self._data[CONF_MAP_SELECT]),
                {CONF_MAP_OPTION: st.state} if st else {}))

    async def async_step_weather(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_cleared(user_input, WEATHER_KEYS))
            return self.async_create_entry(title=TITLE, data=self._data)
        weathers = sorted(self.hass.states.async_entity_ids("weather"))
        suggested = {CONF_LATITUDE: self.hass.config.latitude, CONF_LONGITUDE: self.hass.config.longitude}
        if weathers:
            suggested[CONF_WEATHER] = weathers[0]
        return self.async_show_form(
            step_id="weather",
            data_schema=self.add_suggested_values_to_schema(WEATHER_SCHEMA, suggested))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> CutHeightOptionsFlow:
        return CutHeightOptionsFlow()


class CutHeightOptionsFlow(OptionsFlowWithReload):
    """Change the mower entities or the weather sources. Saving reloads the integration."""

    def __init__(self) -> None:
        self._changes: dict[str, Any] = {}

    @property
    def _cfg(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **self._changes})

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["weather", "mower"])

    async def async_step_weather(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._changes.update(_cleared(user_input, WEATHER_KEYS))
            return self._save()
        suggested = {k: v for k, v in self._cfg.items() if v is not None}
        return self.async_show_form(
            step_id="weather",
            data_schema=self.add_suggested_values_to_schema(WEATHER_SCHEMA, suggested))

    async def async_step_mower(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, zones = _check_mower(self.hass, user_input, self._cfg.get(CONF_ZONES))
            if not errors:
                self._changes.update(_cleared(user_input, (CONF_MAP_SELECT, CONF_CALENDAR, CONF_NOTIFY)))
                self._changes.update(zones)
                if self._changes.get(CONF_MAP_SELECT):
                    return await self.async_step_map()
                self._changes[CONF_MAP_OPTION] = None
                return self._save()
        suggested = user_input or {k: v for k, v in self._cfg.items() if v is not None}
        return self.async_show_form(
            step_id="mower", errors=errors,
            data_schema=self.add_suggested_values_to_schema(_mower_schema(self.hass), suggested))

    async def async_step_map(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._changes[CONF_MAP_OPTION] = user_input.get(CONF_MAP_OPTION)
            return self._save()
        return self.async_show_form(
            step_id="map",
            data_schema=self.add_suggested_values_to_schema(
                _map_schema(self.hass, self._changes[CONF_MAP_SELECT]),
                {CONF_MAP_OPTION: self._cfg.get(CONF_MAP_OPTION)}))
