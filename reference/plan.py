"""Weather-dependent cut height for a Dreame mower in the tropics (test oracle).

The Jinja macros in custom_templates/cut_height.jinja mirror these two functions, and
tests/test_parity_plan_ha.py checks that they agree.

plan() runs once before each scheduled mow on daily weather covering at least the 20
days before today and, ideally, the next 2. It reads its state (a dry-spell latch and
four dates) and returns the new state plus a weather condition with a height offset in
centimetres. zone_next() turns that offset into the next height for one zone, from the
zone's own baseline and its current height.

Heights are in centimetres because that is what the Dreame integration uses (3.0 to
7.0 cm in 0.5 cm steps on the A1). Notes and sources: docs/tropical-cut-height-notes.md.
"""
import math
from datetime import date, timedelta

DEFAULTS = dict(
    grow=23.0,          # T7 (°C) at or above which warm-season grass is growing fast
    heavy_rain=25.0,    # rain (mm) in 3 days, or at the local gauge in 24 h, that counts as heavy
    hot_max=34.0,       # a day with max (°C) at or above this, today or the next 2 days, is hot
    t95=29.5,           # heatwave: 3-day mean of daily mean temperature (°C) at or above this
    dry_bucket=-15.0,   # Smart Irrigation water balance (mm) at or below which the lawn is dry
    dry_deficit=60.0,   # without a water balance: 21-day ET0 minus rain (mm) for a dry spell
    rain_offset=-0.5,   # cm added to the baseline after heavy rain while growing
    hot_offset=0.5,     # cm added in heat or a dry spell
    wave_offset=1.0,    # cm added in a heatwave
)

RAIN_HOLD_DAYS = 5    # low height held this long after heavy rain
HEAT_HOLD_DAYS = 3    # raised height held this long after forecast heat
DRY_RELEASE_MM = 10.0 # without a water balance: rain in 3 days that ends a dry spell
LOWER_EVERY_DAYS = 2  # at most one step down per this many days
STEP_CM = 0.5
MIN_CM = 3.0
MAX_CM = 7.0


def _mean(xs):
    return sum(xs) / len(xs)


def _plus(today, days):
    return (date.fromisoformat(today) + timedelta(days=days)).isoformat()


def plan(*, daily, i, today, rain_until="1970-01-01", heat_until="1970-01-01",
         wave_until="1970-01-01", dry=False, last_lower="1970-01-01",
         bucket=None, local_rain=None, p=None):
    """daily: dict of lists with keys temperature_2m_mean, temperature_2m_max,
    temperature_2m_min, precipitation_sum, et0_fao_evapotranspiration.
    i: index of today (>= 20). Dates are 'YYYY-MM-DD'.
    bucket: Smart Irrigation water balance in mm (negative = deficit), or None.
    local_rain: rain in the last 24 h at your own gauge in mm, or None."""
    p = {**DEFAULTS, **(p or {})}
    tm = [float(x or 0) for x in daily["temperature_2m_mean"]]
    tx = [float(x or 0) for x in daily["temperature_2m_max"]]
    tn = [float(x or 0) for x in daily["temperature_2m_min"]]
    rain = [float(x or 0) for x in daily["precipitation_sum"]]
    et0 = [float(x or 0) for x in daily["et0_fao_evapotranspiration"]]
    n = len(tm)

    t7 = _mean(tm[i - 6:i + 1])
    growing = t7 >= p["grow"]
    rain3 = sum(rain[i - 2:i + 1])
    deficit = sum(et0[i - 20:i + 1]) - sum(rain[i - 20:i + 1])

    # Heavy rain while growing: hold the low height for a few days.
    heavy = max(rain3, float(local_rain or 0)) >= p["heavy_rain"]
    if heavy and growing:
        rain_until = _plus(today, RAIN_HOLD_DAYS)

    # Heat: any day today..+2 at or above hot_max.
    ahead = range(i, min(i + 3, n))
    hot_ahead = any(tx[k] >= p["hot_max"] for k in ahead)
    # Heatwave (BoM excess heat): a 3-day mean of daily mean temperature, (max + min) / 2,
    # at or above t95, for any 3-day window ending today..+2.
    dmt = [(a + b) / 2 for a, b in zip(tx, tn)]
    ehi = max(_mean(dmt[k - 2:k + 1]) for k in ahead) - p["t95"]
    wave_ahead = ehi >= 0
    if hot_ahead or wave_ahead:
        heat_until = _plus(today, HEAT_HOLD_DAYS)
    if wave_ahead:
        wave_until = _plus(today, HEAT_HOLD_DAYS)

    # Dry spell: from the Smart Irrigation water balance when there is one.
    if bucket is not None:
        if float(bucket) <= p["dry_bucket"]:
            dry = True
        elif float(bucket) >= 0:
            dry = False
    else:
        if deficit >= p["dry_deficit"]:
            dry = True
        if dry and rain3 >= DRY_RELEASE_MM:
            dry = False

    wave = today <= wave_until
    hot = today <= heat_until
    wet = growing and today <= rain_until
    if wave:
        why, offset = "heatwave", p["wave_offset"]
    elif hot or dry:
        why, offset = ("heat" if hot else "dry spell"), p["hot_offset"]
    elif wet:
        why, offset = "after heavy rain", p["rain_offset"]
    else:
        why, offset = "normal", 0.0

    since_lower = (date.fromisoformat(today) - date.fromisoformat(last_lower)).days
    return dict(t7=round(t7, 1), rain3=round(rain3, 1), deficit=round(deficit, 1),
                ehi=round(ehi, 1), growing=growing, heavy=heavy, hot=hot, wave=wave, dry=dry,
                rain_until=rain_until, heat_until=heat_until, wave_until=wave_until,
                offset=float(offset), why=why, can_lower=since_lower >= LOWER_EVERY_DAYS)


def zone_want(offset, baseline):
    """Baseline plus offset, on the 0.5 cm grid, inside the deck's range."""
    x = math.floor((float(baseline) + float(offset)) * 2 + 0.5) / 2  # half up, as in Jinja
    return min(MAX_CM, max(MIN_CM, x))


def zone_next(offset, can_lower, baseline, height):
    """Raise at once; lower one 0.5 cm step at a time, at most every 2 days."""
    want = zone_want(offset, baseline)
    height = float(height)
    if want > height:
        return want
    if want < height and can_lower:
        return max(want, height - STEP_CM)
    return height
