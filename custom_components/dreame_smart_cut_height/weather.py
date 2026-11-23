"""Merge Open-Meteo, the weather entity's forecast and a garden weather station (pure)."""
from __future__ import annotations


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def merge_weather_sources(open_meteo_daily, forecast, station_by_date, today_index):
    """Return (daily, station_days, forecast_days).

    Past days: the station's max, min and mean temperature when it has all three.
    Today and ahead: the forecast entity's max and min when it has both (the mean stays
    Open-Meteo's). Rain up to today: the station's when it has a value. Everything else,
    including ET0, comes from Open-Meteo.
    """
    merged = {key: list(value) for key, value in open_meteo_daily.items() if isinstance(value, list)}
    by_date = {}
    for item in forecast or []:
        if isinstance(item, dict) and item.get("datetime"):
            by_date[str(item["datetime"])[:10]] = item
    station_days = forecast_days = 0
    for index, day in enumerate(open_meteo_daily["time"]):
        past = index < today_index
        station = station_by_date.get(day, {})
        ahead = by_date.get(day, {})
        if past and all(_num(station.get(k)) for k in ("max", "min", "mean")):
            merged["temperature_2m_max"][index] = station["max"]
            merged["temperature_2m_min"][index] = station["min"]
            merged["temperature_2m_mean"][index] = station["mean"]
            station_days += 1
        elif not past and _num(ahead.get("temperature")) and _num(ahead.get("templow")):
            merged["temperature_2m_max"][index] = ahead["temperature"]
            merged["temperature_2m_min"][index] = ahead["templow"]
            forecast_days += 1
        if index <= today_index and _num(station.get("rain")):
            merged["precipitation_sum"][index] = station["rain"]
    return merged, station_days, forecast_days
