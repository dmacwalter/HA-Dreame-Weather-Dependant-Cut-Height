"""Base entity: every entity belongs to one service device per mower."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CutHeightCoordinator


class CutHeightEntity(CoordinatorEntity[CutHeightCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CutHeightCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Dreame Smart Cut Height",
            model="Weather-dependent cut height",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _zone(self, zid: int) -> dict:
        data = self.coordinator.data or {}
        return next((z for z in data.get("zones", []) if int(z["id"]) == int(zid)), {})
