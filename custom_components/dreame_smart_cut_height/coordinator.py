"""Weather plan, mowing-calendar scheduler and guarded mower writes."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_SKIP,
    APPLY_BEFORE,
    CALENDAR_CACHE,
    CALENDAR_LOOKAHEAD,
    CHECK_BEFORE,
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
    DEFAULT_BASELINE,
    DOCKED_FOR,
    DOMAIN,
    LEGACY_BASELINE,
    LEGACY_MANAGE,
    LEGACY_PENDING,
    LEGACY_STATE,
    LEGACY_TUNABLES,
    NOTIFY_TAG,
    READ_BACK_DELAY,
    SELECT_TIMEOUT,
    SKIP_FOR,
    STORAGE_VERSION,
    TICK_INTERVAL,
    UPDATE_INTERVAL,
)
from .plan import DEFAULTS, plan, zone_next, zone_want
from .weather import merge_weather_sources
from .zones import option_for

_LOGGER = logging.getLogger(__name__)

EPOCH = "1970-01-01"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
DAILY = "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration"
UNAVAILABLE = ("unknown", "unavailable", "none", "")


def _number(state: State | None) -> float | None:
    if state is None or state.state in UNAVAILABLE:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    """A local, timezone-aware datetime from a datetime, an ISO string or a date string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = dt_util.parse_datetime(str(value))
        if parsed is None:
            day = dt_util.parse_date(str(value))
            if day is None:
                return None
            return dt_util.start_of_local_day(day)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_local(parsed)


def _default_state() -> dict[str, Any]:
    return {
        "enabled": False,         # master switch: run the pre-mow check and apply
        "allow_writes": False,    # without it nothing is ever sent to the mower
        "tunables": {},
        "zones": {},              # "1": {"manage": bool, "baseline": float}
        "dry": False,
        "rain_until": EPOCH,
        "heat_until": EPOCH,
        "wave_until": EPOCH,
        "last_lower": EPOCH,
        "skip_until": None,
        "pending": [],            # [{"id", "name", "from", "to"}]
        "pending_for": None,      # calendar event key the pending change was made for
        "apply_at": None,
        "apply_due": False,       # write as soon as the mower has been docked a while
        "processed_check": [],
        "processed_apply": [],
        "heights": {},            # last heights read from the mower, by zone id
        "heights_at": None,
        "last_check": None,
        "last_apply": None,
        "last_error": None,
        "legacy_imported": False,
    }


class CutHeightCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches the weather, plans the offset, and checks and writes zone heights."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=UPDATE_INTERVAL)
        self.store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.state: dict[str, Any] = _default_state()
        self._lock = asyncio.Lock()
        self._inputs: dict[str, Any] | None = None
        self._events: list[dict[str, Any]] = []
        self._events_at: datetime | None = None

    # ----- configuration and stored settings -------------------------------------------

    @property
    def cfg(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def zones(self) -> list[dict[str, Any]]:
        return list(self.cfg.get(CONF_ZONES, []))

    def zone_name(self, zid: int) -> str:
        return next((z["name"] for z in self.zones if int(z["id"]) == int(zid)), f"Zone {zid}")

    def _zone_settings(self, zid: int) -> dict[str, Any]:
        return self.state["zones"].setdefault(str(zid), {"manage": False, "baseline": DEFAULT_BASELINE})

    def baseline(self, zid: int) -> float:
        return float(self._zone_settings(zid).get("baseline", DEFAULT_BASELINE))

    def managed(self, zid: int) -> bool:
        return bool(self._zone_settings(zid).get("manage", False))

    def tunables(self) -> dict[str, float]:
        return {**DEFAULTS, **self.state["tunables"]}

    @property
    def enabled(self) -> bool:
        return bool(self.state["enabled"])

    @property
    def allow_writes(self) -> bool:
        return bool(self.state["allow_writes"])

    async def async_set_enabled(self, value: bool) -> None:
        self.state["enabled"] = bool(value)
        await self._save_and_recompute()

    async def async_set_allow_writes(self, value: bool) -> None:
        self.state["allow_writes"] = bool(value)
        if not value:
            self.state["apply_due"] = False
        await self._save_and_recompute()

    async def async_set_tunable(self, key: str, value: float) -> None:
        self.state["tunables"][key] = float(value)
        await self._save_and_recompute()

    async def async_set_baseline(self, zid: int, value: float) -> None:
        self._zone_settings(zid)["baseline"] = float(value)
        await self._save_and_recompute()

    async def async_set_managed(self, zid: int, value: bool) -> None:
        self._zone_settings(zid)["manage"] = bool(value)
        if not value:
            self.state["pending"] = [p for p in self.state["pending"] if int(p["id"]) != int(zid)]
        await self._save_and_recompute()

    # ----- storage -----------------------------------------------------------------------

    async def async_load(self) -> None:
        saved = await self.store.async_load()
        if saved:
            self.state.update(saved)
        else:
            self._import_legacy()
        for zone in self.zones:
            self._zone_settings(zone["id"])
        await self._save()

    def _import_legacy(self) -> None:
        """Adopt the old YAML package's helpers, if they exist, on the first start."""
        states = self.hass.states
        found = False
        for key, entity_id in LEGACY_TUNABLES.items():
            value = _number(states.get(entity_id))
            if value is not None:
                self.state["tunables"][key] = value
                found = True
        for zone in self.zones:
            zid = int(zone["id"])
            settings = self._zone_settings(zid)
            baseline = _number(states.get(LEGACY_BASELINE.format(zid)))
            if baseline is not None:
                settings["baseline"] = baseline
                found = True
            manage = states.get(LEGACY_MANAGE.format(zid))
            if manage is not None and manage.state in ("on", "off"):
                settings["manage"] = manage.state == "on"
                found = True
        for key, entity_id in LEGACY_STATE.items():
            st = states.get(entity_id)
            if st is None or st.state in UNAVAILABLE:
                continue
            found = True
            if key == "dry":
                self.state[key] = st.state == "on"
            elif key == "skip_until":
                when = _parse_dt(st.state)
                self.state[key] = when.isoformat() if when else None
            else:
                self.state[key] = st.state[:10]
        pending = states.get(LEGACY_PENDING)
        if pending is not None and pending.state not in UNAVAILABLE:
            try:
                items = json.loads(pending.state)
                self.state["pending"] = [
                    {"id": int(x["id"]), "name": self.zone_name(int(x["id"])),
                     "from": float(x["from"]), "to": float(x["to"])}
                    for x in items
                ]
            except (ValueError, TypeError, KeyError):
                _LOGGER.warning("Could not read the old package's pending changes")
        self.state["legacy_imported"] = found
        if found:
            _LOGGER.info("Imported settings and state from the cut-height YAML package helpers")

    async def _save(self) -> None:
        await self.store.async_save(self.state)

    async def _save_and_recompute(self) -> None:
        await self._save()
        self.recompute()

    # ----- weather and the plan ----------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        cfg = self.cfg
        today = dt_util.now().date()
        params = {
            "latitude": float(cfg.get(CONF_LATITUDE, self.hass.config.latitude)),
            "longitude": float(cfg.get(CONF_LONGITUDE, self.hass.config.longitude)),
            "daily": DAILY,
            "past_days": 21,
            "forecast_days": 6,
            "timezone": self.hass.config.time_zone or "auto",
        }
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(OPEN_METEO, params=params,
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                body = await resp.json()
            daily = body["daily"]
            index = daily["time"].index(today.isoformat())
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Open-Meteo unavailable: {err}") from err
        except (KeyError, ValueError, TypeError) as err:
            raise UpdateFailed(f"Unexpected Open-Meteo response: {err}") from err

        forecast = await self._forecast()
        station = await self._station(today)
        merged, station_days, forecast_days = merge_weather_sources(daily, forecast, station, index)
        self._inputs = {
            "daily": merged,
            "index": index,
            "today": today.isoformat(),
            "forecast": forecast,
            "station": station,
            "station_days": station_days,
            "forecast_days": forecast_days,
        }
        return self._compute()

    async def _forecast(self) -> list[dict[str, Any]]:
        entity_id = self.cfg.get(CONF_WEATHER)
        if not entity_id:
            return []
        try:
            response = await self.hass.services.async_call(
                "weather", "get_forecasts", {"type": "daily", "entity_id": entity_id},
                blocking=True, return_response=True)
        except HomeAssistantError as err:
            _LOGGER.warning("No forecast from %s, using Open-Meteo: %s", entity_id, err)
            return []
        data = (response or {}).get(entity_id) or {}
        forecast = data.get("forecast") if isinstance(data, dict) else None
        return forecast if isinstance(forecast, list) else []

    async def _station(self, today) -> dict[str, dict[str, Any]]:
        """Daily max/min/mean temperature and rain from long-term statistics."""
        temp_id = self.cfg.get(CONF_STATION_TEMP)
        rain_id = self.cfg.get(CONF_STATION_RAIN)
        ids = [x for x in (temp_id, rain_id) if x]
        if not ids:
            return {}
        start = dt_util.start_of_local_day(today - timedelta(days=22))
        try:
            response = await self.hass.services.async_call(
                "recorder", "get_statistics",
                {"start_time": start.isoformat(), "statistic_ids": ids, "period": "day",
                 "types": ["max", "min", "mean", "change"]},
                blocking=True, return_response=True)
        except HomeAssistantError as err:
            _LOGGER.warning("No weather-station statistics, using Open-Meteo: %s", err)
            return {}
        stats = (response or {}).get("statistics") or {}
        out: dict[str, dict[str, Any]] = {}

        def day_of(stamp) -> str | None:
            when = _parse_dt(stamp)
            return when.date().isoformat() if when else None

        for row in stats.get(temp_id, []) if temp_id else []:
            day = day_of(row.get("start"))
            if day:
                out.setdefault(day, {}).update(
                    {"max": row.get("max"), "min": row.get("min"), "mean": row.get("mean")})
        for row in stats.get(rain_id, []) if rain_id else []:
            day = day_of(row.get("start"))
            if day:
                out.setdefault(day, {})["rain"] = row.get("change")
        return out

    def _heat_warning(self) -> bool:
        entity_id = self.cfg.get(CONF_WARNINGS)
        st = self.hass.states.get(entity_id) if entity_id else None
        if st is None:
            return False
        text = f"{st.state} {st.attributes.get('warnings', '')}".lower()
        return "heatwave" in text

    def _compute(self) -> dict[str, Any]:
        """Run the plan on the last fetched weather and the current settings and state."""
        inputs = self._inputs
        if inputs is None:
            return self.data or {}
        cfg = self.cfg
        heat_warning = self._heat_warning()
        result = plan(
            daily=inputs["daily"], i=inputs["index"], today=inputs["today"],
            bucket=_number(self.hass.states.get(cfg[CONF_BUCKET])) if cfg.get(CONF_BUCKET) else None,
            local_rain=_number(self.hass.states.get(cfg[CONF_LOCAL_RAIN])) if cfg.get(CONF_LOCAL_RAIN) else None,
            heat_warning=heat_warning, p=self.tunables(), dry=self.state["dry"],
            rain_until=self.state["rain_until"], heat_until=self.state["heat_until"],
            wave_until=self.state["wave_until"], last_lower=self.state["last_lower"])
        rows = []
        for zone in self.zones:
            zid = int(zone["id"])
            baseline = self.baseline(zid)
            pending = next((p for p in self.state["pending"] if int(p["id"]) == zid), None)
            rows.append({
                "id": zid,
                "name": zone["name"],
                "manage": self.managed(zid),
                "baseline": baseline,
                "target": zone_want(result["offset"], baseline),
                "current": self.state["heights"].get(str(zid)),
                "pending_to": pending["to"] if pending else None,
            })
        return {
            "plan": result,
            "zones": rows,
            "heat_warning": heat_warning,
            "weather": inputs["daily"],
            "forecast": inputs["forecast"],
            "station": inputs["station"],
            "station_days": inputs["station_days"],
            "forecast_days": inputs["forecast_days"],
            "updated": dt_util.now().isoformat(),
        }

    @callback
    def recompute(self) -> None:
        """Refresh entities after a setting changes, without fetching the weather again."""
        if self._inputs is not None:
            self.async_set_updated_data(self._compute())
        else:
            self.async_update_listeners()

    # ----- the mower ---------------------------------------------------------------------

    def _docked_for(self) -> timedelta | None:
        st = self.hass.states.get(self.cfg.get(CONF_DOCKED, ""))
        if st is None or st.state != "on":
            return None
        return dt_util.utcnow() - st.last_changed

    async def _select(self, entity_id: str, option: str) -> None:
        st = self.hass.states.get(entity_id)
        if st is None:
            raise HomeAssistantError(f"{entity_id} not found")
        if st.state != option:
            await self.hass.services.async_call(
                "select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True)
        async with asyncio.timeout(SELECT_TIMEOUT):
            while (st := self.hass.states.get(entity_id)) is None or st.state != option:
                await asyncio.sleep(0.25)

    async def _zone_height(self, zid: int) -> float:
        entity_id = self.cfg[CONF_ZONE_HEIGHT]
        async with asyncio.timeout(SELECT_TIMEOUT):
            while True:
                st = self.hass.states.get(entity_id)
                value = _number(st)
                if st is not None and value is not None and st.attributes.get("selected_zone_id") == zid:
                    return value
                await asyncio.sleep(0.25)

    async def async_read_heights(self, zone_ids: list[int]) -> tuple[dict[str, float], dict[str, str]]:
        """Select the mowing map, then each zone, and read the height the mower reports.

        Only Home Assistant's own selection changes; nothing is sent to the mower. The
        map and zone that were selected before are put back afterwards.
        """
        cfg = self.cfg
        zone_select = cfg.get(CONF_ZONE_SELECT)
        if not zone_select or not cfg.get(CONF_ZONE_HEIGHT):
            raise HomeAssistantError("Set the zone selector and zone height entities first")
        map_select, map_option = cfg.get(CONF_MAP_SELECT), cfg.get(CONF_MAP_OPTION)
        before_map = self.hass.states.get(map_select) if map_select else None
        before_zone = self.hass.states.get(zone_select)
        heights: dict[str, float] = {}
        errors: dict[str, str] = {}
        try:
            if map_select and map_option:
                await self._select(map_select, map_option)
            zone_state = self.hass.states.get(zone_select)
            options = zone_state.attributes.get("options", []) if zone_state else []
            for zid in zone_ids:
                option = option_for(options, zid)
                if option is None:
                    errors[str(zid)] = "not in the mower's zone list"
                    continue
                try:
                    await self._select(zone_select, option)
                    heights[str(zid)] = await self._zone_height(zid)
                except (HomeAssistantError, TimeoutError) as err:
                    errors[str(zid)] = str(err) or "timed out"
        finally:
            try:
                if before_map is not None and map_option and before_map.state != map_option:
                    await self._select(map_select, before_map.state)
                if before_zone is not None and before_zone.state not in UNAVAILABLE:
                    await self._select(zone_select, before_zone.state)
            except (HomeAssistantError, TimeoutError):
                _LOGGER.warning("Could not put the mower's map and zone selection back")
        if heights:
            self.state["heights"].update(heights)
            self.state["heights_at"] = dt_util.now().isoformat()
        return heights, errors

    # ----- check, apply, skip ------------------------------------------------------------

    async def async_check(self, event: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Plan, read the managed zones' heights and propose changes.

        For a scheduled check (event given) the plan's memory is saved and a skip is
        honoured, as the YAML package did; a manual check only previews.
        """
        async with self._lock:
            return await self._check(event)

    async def _check(self, event: dict[str, Any] | None) -> list[dict[str, Any]]:
        await self.async_refresh()
        if not self.last_update_success or not self.data:
            await self.async_notify("Couldn't get the weather, so cut heights were left as they are.")
            return []
        result = self.data["plan"]
        now = dt_util.now()
        if event is not None:
            for key in ("dry", "rain_until", "heat_until", "wave_until"):
                self.state[key] = result[key]
            self.state["apply_due"] = False
            skip = _parse_dt(self.state.get("skip_until"))
            if skip is not None and skip > now:
                self.state.update(pending=[], pending_for=None, apply_at=None)
                await self._save_and_recompute()
                return []
        managed = [z for z in self.zones if self.managed(z["id"])]
        heights, errors = await self.async_read_heights([int(z["id"]) for z in managed])
        pending, unread = [], []
        for zone in managed:
            zid = int(zone["id"])
            current = heights.get(str(zid))
            if current is None:
                unread.append(zone["name"])
                continue
            target = zone_next(result["offset"], result["can_lower"], self.baseline(zid), current)
            if target != current:
                pending.append({"id": zid, "name": zone["name"], "from": current, "to": target})
        apply_at = event["start"] - APPLY_BEFORE if event is not None else None
        self.state.update(
            pending=pending,
            pending_for=event["key"] if event is not None and pending else None,
            apply_at=apply_at.isoformat() if apply_at and pending else None,
            last_check=now.isoformat(),
        )
        await self._save_and_recompute()
        if errors:
            _LOGGER.warning("Could not read zone heights: %s", errors)
        if unread:
            await self.async_notify(
                f"Couldn't read the height of {', '.join(unread)}; left as it is.")
        if pending:
            text = " ".join(f"{p['name']}: {p['from']:.1f} → {p['to']:.1f} cm." for p in pending)
            text += (f" ({result['why']}; 7-day mean {result['t7']:.1f} °C, "
                     f"rain {result['rain3']:.1f} mm in 3 days).")
            if not self.allow_writes:
                text += " Preview only: writes to the mower are off."
                await self.async_notify(text)
            elif apply_at is not None:
                text += (f" It will be set at {dt_util.as_local(apply_at).strftime('%H:%M')} "
                         "while the mower is docked, unless you skip.")
                await self.async_notify(text, ask=True)
            else:
                text += " The check before the next mow will set it."
                await self.async_notify(text)
        return pending

    async def async_apply(self) -> str:
        """Write the pending heights now if the mower is docked, else queue them for the dock.

        Only the scheduler calls this: changes are made automatically before a mow, never
        on request. Returns "applied", "queued", "nothing" or "off".
        """
        if not self.allow_writes:
            return "off"
        async with self._lock:
            return await self._apply()

    async def _apply(self) -> str:
        pending = list(self.state["pending"])
        if not pending:
            self.state["apply_due"] = False
            await self._save_and_recompute()
            return "nothing"
        if self._docked_for() is None:
            self.state["apply_due"] = True
            await self._save_and_recompute()
            return "queued"
        before, _ = await self.async_read_heights([int(p["id"]) for p in pending])
        written, failed = [], []
        for item in pending:
            zid = int(item["id"])
            now_height = before.get(str(zid))
            if now_height is None or abs(now_height - float(item["from"])) > 0.001:
                failed.append(f"{item['name']} (height changed since the check)")
                continue
            try:
                await self.hass.services.async_call(
                    "dreame_lawn_mower", "plan_zone_mowing_preference_update",
                    {"entity_id": self.cfg[CONF_MOWER], "zone_id": zid,
                     "mowing_height_cm": float(item["to"]), "execute": True,
                     "confirm_preference_write": True},
                    blocking=True)
                written.append(item)
            except HomeAssistantError as err:
                _LOGGER.error("Writing zone %s height failed: %s", zid, err)
                failed.append(f"{item['name']} (write failed: {err})")
        after: dict[str, float] = {}
        if written:
            # Give the Dreame integration time to fetch the mower's preferences again.
            await asyncio.sleep(READ_BACK_DELAY)
            after, _ = await self.async_read_heights([int(p["id"]) for p in written])
        lowered = False
        for item in written:
            got = after.get(str(item["id"]))
            if got is None or abs(got - float(item["to"])) > 0.001:
                failed.append(f"{item['name']} (wanted {item['to']:.1f}, reports "
                              f"{'nothing' if got is None else f'{got:.1f}'})")
            elif float(item["to"]) < float(item["from"]):
                lowered = True
        if lowered:
            self.state["last_lower"] = dt_util.now().date().isoformat()
        self.state.update(pending=[], pending_for=None, apply_at=None, apply_due=False,
                          last_apply=dt_util.now().isoformat(),
                          last_error="; ".join(failed) if failed else None)
        await self._save_and_recompute()
        if failed:
            await self.async_notify(
                f"Couldn't set {'; '.join(failed)}. Set it in the Dreame app; the check "
                "before the next mow will otherwise try again.")
        return "applied"

    async def async_skip(self) -> None:
        self.state.update(skip_until=(dt_util.now() + SKIP_FOR).isoformat(), pending=[],
                          pending_for=None, apply_at=None, apply_due=False)
        await self._save_and_recompute()

    async def async_notify(self, message: str, ask: bool = False) -> None:
        service = self.cfg.get(CONF_NOTIFY)
        if not service:
            return
        domain, _, name = service.partition(".")
        if not name:
            domain, name = "notify", domain
        data: dict[str, Any] = {"tag": NOTIFY_TAG}
        if ask:
            data["actions"] = [{"action": ACTION_SKIP, "title": "Skip 2 days"}]
        try:
            await self.hass.services.async_call(
                domain, name, {"title": "Mower cut height", "message": message, "data": data},
                blocking=True)
        except HomeAssistantError as err:
            _LOGGER.warning("Notification via %s failed: %s", service, err)

    # ----- scheduler ---------------------------------------------------------------------

    @callback
    def async_start(self) -> None:
        entry = self.config_entry
        entry.async_on_unload(
            async_track_time_interval(self.hass, self._async_tick, TICK_INTERVAL,
                                      name=f"{DOMAIN} scheduler", cancel_on_shutdown=True))
        entry.async_on_unload(
            self.hass.bus.async_listen("mobile_app_notification_action", self._async_phone_action))

    async def _calendar_events(self) -> list[dict[str, Any]]:
        entity_id = self.cfg.get(CONF_CALENDAR)
        if not entity_id:
            return []
        now = dt_util.now()
        if self._events_at is not None and now - self._events_at < CALENDAR_CACHE:
            return self._events
        self._events_at = now
        try:
            response = await self.hass.services.async_call(
                "calendar", "get_events",
                {"entity_id": entity_id, "start_date_time": (now - timedelta(hours=1)).isoformat(),
                 "end_date_time": (now + CALENDAR_LOOKAHEAD).isoformat()},
                blocking=True, return_response=True)
        except HomeAssistantError as err:
            _LOGGER.warning("Could not read the mowing calendar %s: %s", entity_id, err)
            self._events = []
            return []
        self._events = ((response or {}).get(entity_id) or {}).get("events", [])
        return self._events

    def _mark(self, key: str, name: str) -> None:
        self.state[name] = (self.state.get(name, []) + [key])[-50:]

    async def _async_tick(self, _now: datetime | None = None) -> None:
        if self._lock.locked():
            return
        try:
            await self._tick()
        except Exception:  # noqa: BLE001 - a bad tick must not stop the scheduler
            _LOGGER.exception("Cut-height scheduler tick failed")

    async def _tick(self) -> None:
        now = dt_util.now()
        events = await self._calendar_events() if self.enabled else []
        for event in events:
            start = _parse_dt(event.get("start"))
            if start is None:
                continue
            key = f"{event.get('summary', 'mow')}|{start.isoformat()}"
            if start - CHECK_BEFORE <= now < start and key not in self.state["processed_check"]:
                self._mark(key, "processed_check")
                await self._save()
                await self.async_check({"key": key, "start": start})
            if (start - APPLY_BEFORE <= now and key not in self.state["processed_apply"]
                    and self.state["pending"] and self.state["pending_for"] == key):
                self._mark(key, "processed_apply")
                await self._save()
                if self.allow_writes:
                    await self.async_apply()
        # A change that was due while the mower was out: write it once the mower has sat
        # docked for a while.
        if self.enabled and self.allow_writes and self.state["apply_due"] and self.state["pending"]:
            docked = self._docked_for()
            if docked is not None and docked >= DOCKED_FOR:
                await self.async_apply()

    async def _async_phone_action(self, event: Event) -> None:
        if event.data.get("action") == ACTION_SKIP and self.enabled:
            await self.async_skip()
