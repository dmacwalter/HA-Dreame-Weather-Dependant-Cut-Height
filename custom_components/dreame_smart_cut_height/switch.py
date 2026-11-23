"""Master switch, the write safety switch and per-zone smart control."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CutHeightConfigEntry
from .entity import CutHeightEntity


async def async_setup_entry(hass: HomeAssistant, entry: CutHeightConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([MasterSwitch(c), WritesSwitch(c)] + [ZoneSwitch(c, z) for z in c.zones])


class MasterSwitch(CutHeightEntity, SwitchEntity):
    """Runs the check before each scheduled mow and the apply. Off: nothing automatic."""

    _attr_name = None
    _attr_icon = "mdi:robot-mower-outline"

    def __init__(self, c) -> None:
        super().__init__(c, "master")

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_enabled(False)


class WritesSwitch(CutHeightEntity, SwitchEntity):
    """Off: checks and notifications only, nothing is ever sent to the mower."""

    _attr_name = "Write to mower"
    _attr_icon = "mdi:content-save-cog-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, c) -> None:
        super().__init__(c, "allow_writes")

    @property
    def is_on(self) -> bool:
        return self.coordinator.allow_writes

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_allow_writes(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_allow_writes(False)


class ZoneSwitch(CutHeightEntity, SwitchEntity):
    _attr_icon = "mdi:texture-box"

    def __init__(self, c, zone) -> None:
        super().__init__(c, f"zone_{zone['id']}_manage")
        self._zid = int(zone["id"])
        self._attr_name = f"{zone['name']} smart control"

    @property
    def is_on(self) -> bool:
        return self.coordinator.managed(self._zid)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_managed(self._zid, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_managed(self._zid, False)
