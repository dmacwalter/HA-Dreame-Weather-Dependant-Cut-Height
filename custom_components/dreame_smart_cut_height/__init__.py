"""Dreame Smart Cut Height: weather-dependent, per-zone cut height for Dreame mowers."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import CutHeightCoordinator

type CutHeightConfigEntry = ConfigEntry[CutHeightCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_ENTRY = "config_entry_id"
ATTR_CONFIRM = "confirm"
BASE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY): cv.string})
APPLY_SCHEMA = BASE_SCHEMA.extend({vol.Required(ATTR_CONFIRM): cv.boolean})


@callback
def _coordinator(hass: HomeAssistant, call: ServiceCall) -> CutHeightCoordinator:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    wanted = call.data.get(ATTR_ENTRY)
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if not entries:
        raise ServiceValidationError("Dreame Smart Cut Height isn't set up (or that entry isn't loaded)")
    if len(entries) > 1:
        raise ServiceValidationError("More than one mower is set up; give config_entry_id")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def check(call: ServiceCall):
        pending = await _coordinator(hass, call).async_check()
        return {"pending": pending}

    async def apply(call: ServiceCall):
        if not call.data[ATTR_CONFIRM]:
            raise ServiceValidationError("Set confirm: true to change the mower's cut heights")
        return {"result": await _coordinator(hass, call).async_apply()}

    async def skip(call: ServiceCall) -> None:
        await _coordinator(hass, call).async_skip()

    hass.services.async_register(DOMAIN, "check", check, BASE_SCHEMA,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "apply", apply, APPLY_SCHEMA,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "skip", skip, BASE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CutHeightConfigEntry) -> bool:
    coordinator = CutHeightCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CutHeightConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
