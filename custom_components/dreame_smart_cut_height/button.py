"""Check now and skip."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CutHeightConfigEntry
from .entity import CutHeightEntity


async def async_setup_entry(hass: HomeAssistant, entry: CutHeightConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([CheckButton(c), SkipButton(c)])


class CheckButton(CutHeightEntity, ButtonEntity):
    """Read the managed zones and send the proposed change to the phone. Writes nothing."""

    _attr_name = "Check now"
    _attr_icon = "mdi:refresh"

    def __init__(self, c) -> None:
        super().__init__(c, "check")

    async def async_press(self) -> None:
        await self.coordinator.async_check()


class SkipButton(CutHeightEntity, ButtonEntity):
    _attr_name = "Skip 2 days"
    _attr_icon = "mdi:calendar-remove"

    def __init__(self, c) -> None:
        super().__init__(c, "skip")

    async def async_press(self) -> None:
        await self.coordinator.async_skip()
