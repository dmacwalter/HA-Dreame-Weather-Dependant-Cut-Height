from reference.plan import plan, zone_next, zone_want
from tests.plan_fixtures import TODAY, weather

WET = dict(bucket=5.0)  # well watered, so the dry-spell rule stays out of the way


def run(d, today="2026-12-10", **state):
    return plan(daily=d, i=TODAY, today=today, **{**WET, **state})


def raised_lawn(r, height):
    return zone_next(r["offset"], r["can_lower"], 3.5, height)


# A typical Townsville wet-season day: 27 °C mean, 31 °C max, 22 °C min.
NORMAL = dict(mean=27)


def test_normal_day_keeps_baseline():
    r = run(weather(**NORMAL))
    assert (r["why"], r["offset"]) == ("normal", 0.0)
    assert raised_lawn(r, 3.5) == 3.5


def test_heavy_rain_in_growing_season_drops_half_a_centimetre():
    d = weather(**NORMAL, overrides={TODAY - 1: dict(rain=30)})
    r = run(d)
    assert r["heavy"] and r["growing"]
    assert (r["why"], r["rain_until"]) == ("after heavy rain", "2026-12-15")
    assert raised_lawn(r, 3.5) == 3.0


def test_rain_hold_lasts_after_the_rain_has_left_the_window():
    r = run(weather(**NORMAL), rain_until="2026-12-12")
    assert r["why"] == "after heavy rain"
    r = run(weather(**NORMAL), today="2026-12-13", rain_until="2026-12-12")
    assert r["why"] == "normal"
    assert raised_lawn(r, 3.0) == 3.5   # back up at once


def test_local_gauge_counts_as_heavy_rain():
    r = run(weather(**NORMAL), local_rain=28)
    assert r["why"] == "after heavy rain"


def test_heavy_rain_in_the_dry_season_does_not_lower():
    # Warm enough, but July is BOM dry season: no after-rain drop.
    d = weather(mean=24, overrides={TODAY: dict(rain=40)})
    r = run(d, today="2026-07-10")
    assert r["heavy"] and not r["wet_season"] and not r["growing"]
    assert r["why"] == "dry season"


def test_heavy_rain_in_a_cool_wet_season_week_does_not_lower():
    d = weather(mean=21, overrides={TODAY: dict(rain=40)})
    r = run(d, today="2026-04-20")
    assert r["wet_season"] and not r["growing"]
    assert r["why"] == "normal"


def test_wet_season_starts_in_october():
    d = weather(**NORMAL, overrides={TODAY: dict(rain=40)})
    assert run(d, today="2026-10-05")["why"] == "after heavy rain"
    assert run(weather(**NORMAL), today="2026-09-28")["why"] == "dry season"


def test_dry_season_raises_half_a_centimetre():
    r = run(weather(mean=22), today="2026-07-10")
    assert (r["why"], r["offset"]) == ("dry season", 0.5)
    assert raised_lawn(r, 3.5) == 4.0
    # back to the baseline in October, one step
    r = run(weather(**NORMAL), today="2026-10-01")
    assert raised_lawn(r, 4.0) == 3.5


def test_bom_heatwave_warning_counts_as_heatwave():
    r = run(weather(**NORMAL), heat_warning=True)
    assert r["why"] == "heatwave" and r["wave_until"] == "2026-12-13"
    assert raised_lawn(r, 3.5) == 4.5


def test_heat_beats_dry_season():
    d = weather(mean=24, overrides={TODAY + 1: dict(max_=35)})
    r = run(d, today="2026-09-10")
    assert r["why"] == "heat" and r["offset"] == 0.5


def test_hot_forecast_raises_half_a_centimetre_and_holds():
    d = weather(**NORMAL, overrides={TODAY + 2: dict(max_=35)})
    r = run(d)
    assert (r["why"], r["heat_until"]) == ("heat", "2026-12-13")
    assert raised_lawn(r, 3.5) == 4.0
    # heat gone from the forecast but still inside the hold
    r = run(weather(**NORMAL), today="2026-12-12", heat_until="2026-12-13")
    assert r["why"] == "heat"


def test_heat_three_days_out_is_ignored():
    d = weather(**NORMAL, overrides={TODAY + 3: dict(max_=38)})
    assert run(d)["why"] == "normal"


def test_heatwave_raises_a_full_centimetre():
    # 3 nights at 28 and days at 36: daily mean 32 >= 29.5
    o = {k: dict(max_=36, min_=28) for k in (TODAY, TODAY + 1, TODAY + 2)}
    r = run(weather(**NORMAL, overrides=o))
    assert r["wave"] and r["ehi"] >= 0
    assert r["why"] == "heatwave"
    assert raised_lawn(r, 3.5) == 4.5


def test_heat_beats_rain():
    o = {TODAY - 1: dict(rain=40), TODAY + 1: dict(max_=35)}
    r = run(weather(**NORMAL, overrides=o))
    assert r["why"] == "heat" and r["offset"] == 0.5


def test_dry_from_smart_irrigation_water_balance():
    r = run(weather(**NORMAL), bucket=-20)
    assert r["dry"] and r["why"] == "dry spell"
    # stays dry until the balance is back to zero
    assert run(weather(**NORMAL), bucket=-5, dry=True)["dry"] is True
    assert run(weather(**NORMAL), bucket=0, dry=True)["dry"] is False


def test_dry_without_water_balance_uses_open_meteo_deficit():
    r = plan(daily=weather(**NORMAL, et0=4), i=TODAY, today="2026-12-10")
    assert r["deficit"] == 84 and r["dry"]
    d = weather(**NORMAL, et0=4, overrides={TODAY: dict(rain=12)})
    assert plan(daily=d, i=TODAY, today="2026-12-10", dry=True)["dry"] is False


def test_lowering_is_one_step_every_two_days():
    r = run(weather(**NORMAL), last_lower="2026-12-09")
    assert not r["can_lower"]
    assert raised_lawn(r, 4.5) == 4.5
    r = run(weather(**NORMAL), last_lower="2026-12-08")
    assert raised_lawn(r, 4.5) == 4.0


def test_zone_targets_stay_on_the_deck():
    assert zone_want(-0.5, 3.0) == 3.0     # 3.0 cm is the A1's lowest
    assert zone_want(1.0, 6.5) == 7.0
    assert zone_want(0.0, 3.25) == 3.5     # half up onto the 0.5 cm grid


def test_each_zone_uses_its_own_baseline():
    r = run(weather(**NORMAL, overrides={TODAY + 1: dict(max_=35)}))
    assert zone_next(r["offset"], r["can_lower"], 3.5, 3.5) == 4.0
    assert zone_next(r["offset"], r["can_lower"], 5.0, 5.0) == 5.5
