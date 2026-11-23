"""Synthetic daily weather for the plan tests: 21 past days, today, 5 ahead."""

N = 27
TODAY = 21


def weather(mean, max_=None, min_=None, rain=0.0, et0=4.0, overrides=None):
    """Flat weather at `mean` °C (max mean+4, min mean-5 by default).
    overrides: {index: dict(mean=, max_=, min_=, rain=, et0=)}."""
    d = {
        "temperature_2m_mean": [float(mean)] * N,
        "temperature_2m_max": [float(max_ if max_ is not None else mean + 4)] * N,
        "temperature_2m_min": [float(min_ if min_ is not None else mean - 5)] * N,
        "precipitation_sum": [float(rain)] * N,
        "et0_fao_evapotranspiration": [float(et0)] * N,
    }
    keys = dict(mean="temperature_2m_mean", max_="temperature_2m_max", min_="temperature_2m_min",
                rain="precipitation_sum", et0="et0_fao_evapotranspiration")
    for k, o in (overrides or {}).items():
        for name, value in o.items():
            d[keys[name]][k] = float(value)
    return d
