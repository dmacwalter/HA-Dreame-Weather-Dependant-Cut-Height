"""Thresholds, offsets and each zone's usual height."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CutHeightConfigEntry
from .const import TUNABLES
from .entity import CutHeightEntity
from .plan import MAX_CM, MIN_CM, STEP_CM


async def async_setup_entry(hass: HomeAssistant, entry: CutHeightConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([TunableNumber(c, k) for k in TUNABLES] + [BaselineNumber(c, z) for z in c.zones])


class TunableNumber(CutHeightEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, c, key: str) -> None:
        super().__init__(c, f"tunable_{key}")
        self._key = key
        name, low, high, step, unit = TUNABLES[key]
        self._attr_name = name
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float:
        return self.coordinator.tunables()[self._key]

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_tunable(self._key, value)


class BaselineNumber(CutHeightEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_CM
    _attr_native_max_value = MAX_CM
    _attr_native_step = STEP_CM
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_icon = "mdi:ruler"

    def __init__(self, c, zone) -> None:
        super().__init__(c, f"zone_{zone['id']}_baseline")
        self._zid = int(zone["id"])
        self._attr_name = f"{zone['name']} usual height"

    @property
    def native_value(self) -> float:
        return self.coordinator.baseline(self._zid)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_baseline(self._zid, value)
