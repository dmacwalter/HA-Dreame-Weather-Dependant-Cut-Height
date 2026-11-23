"""Render the Jinja macros (from this repo, not the deployed copy) through HA's
/api/template and assert they match reference/plan.py. Read-only: nothing is installed
or changed on HA. Skips unless HA_TOKEN is set.

Set HA_URL (e.g. http://homeassistant.local:8123) and HA_TOKEN (a long-lived access
token) in the environment before running.
"""
import json
import os
import pathlib
import random
import urllib.request
from datetime import date, timedelta

import pytest

from reference.plan import DEFAULTS, plan, zone_next
from tests.plan_fixtures import N, TODAY, weather

HA_URL = os.environ.get("HA_URL", "http://homeassistant.local:8123").rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
MACRO = (pathlib.Path(__file__).parent.parent / "custom_templates" / "cut_height.jinja").read_text()
MACRO = MACRO.split("{#- Live inputs.")[0]
KEYS = ["temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
        "precipitation_sum", "et0_fao_evapotranspiration"]
COMPARE = ("why", "offset", "can_lower", "growing", "heavy", "hot", "wave", "dry",
           "rain_until", "heat_until", "wave_until")


def _render(template):
    if not HA_TOKEN:
        pytest.skip("set HA_URL and HA_TOKEN to run the live parity test")
    req = urllib.request.Request(
        f"{HA_URL}/api/template",
        data=json.dumps({"template": template}).encode(),
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"HA unreachable: {e}")


def random_case(seed):
    rng = random.Random(seed)
    today = (date(2026, 1, 1) + timedelta(days=rng.randrange(365))).isoformat()
    base = rng.uniform(18, 31)
    mean = [round(base + rng.uniform(-3, 3), 1) for _ in range(N)]
    d = {
        "temperature_2m_mean": mean,
        "temperature_2m_max": [round(t + rng.uniform(3, 9), 1) for t in mean],
        "temperature_2m_min": [round(t - rng.uniform(3, 8), 1) for t in mean],
        "precipitation_sum": [round(max(0, rng.uniform(-30, 25)), 1) for _ in range(N)],
        "et0_fao_evapotranspiration": [round(rng.uniform(2, 7), 2) for _ in range(N)],
    }
    t = date.fromisoformat(today)
    day = lambda lo, hi: (t + timedelta(days=rng.randrange(lo, hi))).isoformat()  # noqa: E731
    return dict(daily=d, today=today, dry=rng.random() < 0.3,
                rain_until=day(-6, 4), heat_until=day(-4, 3), wave_until=day(-4, 3),
                last_lower=day(-4, 1),
                bucket=rng.choice([None, round(rng.uniform(-30, 10), 1)]),
                local_rain=rng.choice([None, round(rng.uniform(0, 40), 1)]),
                baseline=rng.choice([3.0, 3.5, 4.0, 5.0, 6.5]),
                height=rng.choice([x / 2 for x in range(6, 15)]))


CASES = [
    dict(daily=weather(27), today="2026-12-10", bucket=5.0, baseline=3.5, height=3.5),
    dict(daily=weather(27, overrides={TODAY - 1: dict(rain=30)}), today="2026-12-10",
         bucket=5.0, baseline=3.5, height=3.5),
    dict(daily=weather(27, overrides={TODAY + 2: dict(max_=35)}), today="2026-12-10",
         bucket=5.0, baseline=3.5, height=3.5),
    dict(daily=weather(27, overrides={k: dict(max_=36, min_=28) for k in (TODAY, TODAY + 1, TODAY + 2)}),
         today="2026-12-10", bucket=5.0, baseline=3.5, height=3.5),
    dict(daily=weather(27), today="2026-12-10", bucket=-20.0, baseline=3.5, height=3.5),
    dict(daily=weather(27, et0=4), today="2026-12-10", bucket=None, baseline=3.5, height=4.5,
         last_lower="2026-12-08"),
    dict(daily=weather(20, overrides={TODAY: dict(rain=40)}), today="2026-07-10",
         bucket=None, baseline=3.0, height=3.0),
] + [random_case(s) for s in range(60)]


def _j(x):
    return "none" if x is None else json.dumps(x)


@pytest.mark.parametrize("c", CASES)
def test_jinja_matches_oracle(c):
    c = {"dry": False, "rain_until": "1970-01-01", "heat_until": "1970-01-01",
         "wave_until": "1970-01-01", "last_lower": "1970-01-01",
         "bucket": None, "local_rain": None, **c}
    state = {k: c[k] for k in ("dry", "rain_until", "heat_until", "wave_until", "last_lower",
                               "bucket", "local_rain")}
    expected = plan(daily=c["daily"], i=TODAY, today=c["today"], p=DEFAULTS, **state)
    expected_next = zone_next(expected["offset"], expected["can_lower"], c["baseline"], c["height"])
    args = ", ".join([
        json.dumps({k: c["daily"][k] for k in KEYS}), str(TODAY), json.dumps(c["today"]),
        json.dumps(c["rain_until"]), json.dumps(c["heat_until"]), json.dumps(c["wave_until"]),
        json.dumps(c["dry"]), json.dumps(c["last_lower"]), _j(c["bucket"]), _j(c["local_rain"]),
        json.dumps(DEFAULTS),
    ])
    template = (MACRO + "{% set r = cut_height_plan(" + args + ") | from_json %}"
                "{{ dict(plan=r, next=cut_height_zone_next(r.offset, r.can_lower, "
                + json.dumps(c["baseline"]) + ", " + json.dumps(c["height"]) + ") | float) | to_json }}")
    got = json.loads(_render(template))
    for k in COMPARE:
        assert got["plan"][k] == expected[k], (k, c["today"], got["plan"], expected)
    assert got["next"] == expected_next, (c["today"], got, expected, expected_next)
