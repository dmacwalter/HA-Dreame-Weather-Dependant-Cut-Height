"""Plan, pending change, per-zone targets and the weather inputs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfPrecipitationDepth, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import CutHeightConfigEntry
from .entity import CutHeightEntity


async def async_setup_entry(hass: HomeAssistant, entry: CutHeightConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    entities: list[SensorEntity] = [
        PlanSensor(c), NextChangeSensor(c), ManagedZonesSensor(c),
        PlanValueSensor(c, "offset", "Offset", UnitOfLength.CENTIMETERS, None, "mdi:arrow-up-down"),
        PlanValueSensor(c, "rain3", "Rain over 3 days", UnitOfPrecipitationDepth.MILLIMETERS,
                        SensorDeviceClass.PRECIPITATION, None),
        PlanValueSensor(c, "t7", "7-day mean temperature", UnitOfTemperature.CELSIUS,
                        SensorDeviceClass.TEMPERATURE, None),
        PlanValueSensor(c, "deficit", "21-day water deficit", UnitOfPrecipitationDepth.MILLIMETERS,
                        None, "mdi:water-minus"),
        WeatherDataSensor(c), ForecastSensor(c), StationSensor(c),
    ]
    entities += [ZoneTargetSensor(c, z) for z in c.zones]
    async_add_entities(entities)


class PlanSensor(CutHeightEntity, SensorEntity):
    _attr_name = "Weather plan"
    _attr_icon = "mdi:grass"
    _unrecorded_attributes = frozenset({"plan"})

    def __init__(self, c) -> None:
        super().__init__(c, "plan")

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get("plan", {}).get("why")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        p = data.get("plan", {})
        managed = [z for z in data.get("zones", []) if z["manage"]]
        return {
            "offset": p.get("offset"),
            "t7": p.get("t7"),
            "rain3": p.get("rain3"),
            "wet_season": p.get("wet_season"),
            "growing": p.get("growing"),
            "dry_spell": p.get("dry"),
            "heat_warning": data.get("heat_warning"),
            "rain_until": p.get("rain_until"),
            "heat_until": p.get("heat_until"),
            "wave_until": p.get("wave_until"),
            "can_lower": p.get("can_lower"),
            "targets": {z["name"]: z["target"] for z in managed},
            "targets_text": ", ".join(f"{z['name']} {z['target']:.1f} cm" for z in managed) or "No zones managed",
            "station_days": data.get("station_days"),
            "forecast_days": data.get("forecast_days"),
            "plan": p,
        }


class NextChangeSensor(CutHeightEntity, SensorEntity):
    _attr_name = "Next change"
    _attr_icon = "mdi:swap-vertical"

    def __init__(self, c) -> None:
        super().__init__(c, "next_change")

    @property
    def native_value(self) -> str:
        pending = self.coordinator.state["pending"]
        if not pending:
            return "None pending"
        return ", ".join(f"{p['name']} {p['from']:.1f} → {p['to']:.1f} cm" for p in pending)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self.coordinator.state
        return {
            "pending": s["pending"],
            "applies_at": s["apply_at"],
            "waiting_for_dock": s["apply_due"],
            "skip_until": s["skip_until"],
            "last_check": s["last_check"],
            "last_apply": s["last_apply"],
            "last_error": s["last_error"],
            "last_heights": s["heights"],
            "heights_read_at": s["heights_at"],
            "last_lower": s["last_lower"],
        }


class ManagedZonesSensor(CutHeightEntity, SensorEntity):
    _attr_name = "Managed zones"
    _attr_icon = "mdi:texture-box"

    def __init__(self, c) -> None:
        super().__init__(c, "managed_zones")

    def _names(self) -> list[str]:
        return [z["name"] for z in (self.coordinator.data or {}).get("zones", []) if z["manage"]]

    @property
    def native_value(self) -> str:
        return ", ".join(self._names()) or "None"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"count": len(self._names()), "zones": self._names()}


class PlanValueSensor(CutHeightEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c, key, name, unit, device_class, icon) -> None:
        super().__init__(c, f"plan_{key}")
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_icon = icon

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("plan", {}).get(self._key)


class ZoneTargetSensor(CutHeightEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_icon = "mdi:grass"

    def __init__(self, c, zone) -> None:
        super().__init__(c, f"zone_{zone['id']}_target")
        self._zid = int(zone["id"])
        self._attr_name = f"{zone['name']} target height"

    @property
    def native_value(self) -> float | None:
        return self._zone(self._zid).get("target")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        z = self._zone(self._zid)
        return {"zone_id": self._zid, "managed": z.get("manage"), "baseline": z.get("baseline"),
                "last_read": z.get("current"), "pending_to": z.get("pending_to")}


class _DiagnosticSensor(CutHeightEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC


class WeatherDataSensor(_DiagnosticSensor):
    _attr_name = "Weather updated"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _unrecorded_attributes = frozenset({"daily"})

    def __init__(self, c) -> None:
        super().__init__(c, "weather_data")

    @property
    def native_value(self) -> datetime | None:
        updated = (self.coordinator.data or {}).get("updated")
        return dt_util.parse_datetime(updated) if updated else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"daily": (self.coordinator.data or {}).get("weather", {})}


class ForecastSensor(_DiagnosticSensor):
    _attr_name = "Forecast days used"
    _attr_icon = "mdi:weather-cloudy-clock"
    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(self, c) -> None:
        super().__init__(c, "forecast")

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("forecast_days")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rows = []
        for f in (self.coordinator.data or {}).get("forecast", []):
            if isinstance(f, dict):
                rows.append({"date": str(f.get("datetime", ""))[:10], "max": f.get("temperature"),
                             "min": f.get("templow"), "rain": f.get("precipitation")})
        return {"forecast": rows}


class StationSensor(_DiagnosticSensor):
    _attr_name = "Weather station days used"
    _attr_icon = "mdi:home-thermometer-outline"
    _unrecorded_attributes = frozenset({"days"})

    def __init__(self, c) -> None:
        super().__init__(c, "station")

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("station_days")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        station = (self.coordinator.data or {}).get("station", {})
        return {"days": [{"date": d, **v} for d, v in sorted(station.items())]}
