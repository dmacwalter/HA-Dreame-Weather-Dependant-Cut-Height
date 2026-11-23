"""Replay the plan over past weather for your own location.

    python -m tools.replay --lat -19.26 --lon 146.82 --start 2024-07-01 --end 2026-06-30 \
        [--baseline 3.5] [--days tue,thu,sat] [--csv out.csv]

Fetches daily weather from the Open-Meteo archive (free, no key; nothing is stored
unless you pass --csv), runs the integration's plan.py on each mowing day as the integration does
(an hour before the mow) and applies any change before that mow. Prints, per year from
July to June, how many mowing days fell in each condition and every height change. Use
it to tune the thresholds before installing.

The archive has no Smart Irrigation water balance or local gauge, so the replay uses
the Open-Meteo dry-spell fallback; on an irrigated lawn the real thing will report
fewer dry spells.
"""
import argparse
import csv
import json
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date

import importlib.util
import pathlib

# Load plan.py on its own so the replay runs without Home Assistant installed.
_PLAN = (pathlib.Path(__file__).resolve().parent.parent
         / "custom_components" / "dreame_smart_cut_height" / "plan.py")
_spec = importlib.util.spec_from_file_location("cut_height_plan", _PLAN)
_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_plan)
plan, zone_next = _plan.plan, _plan.zone_next

DAILY = ["temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
         "precipitation_sum", "et0_fao_evapotranspiration"]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def fetch(lat, lon, start, end):
    q = urllib.parse.urlencode(dict(latitude=lat, longitude=lon, start_date=start, end_date=end,
                                    daily=",".join(DAILY), timezone="auto"))
    with urllib.request.urlopen(f"https://archive-api.open-meteo.com/v1/archive?{q}", timeout=60) as r:
        return json.load(r)["daily"]


def replay(daily, baseline, days):
    state = dict(dry=False, rain_until="1970-01-01", heat_until="1970-01-01",
                 wave_until="1970-01-01", last_lower="1970-01-01")
    height, rows = baseline, []
    for i in range(21, len(daily["time"])):
        today = daily["time"][i]
        if WEEKDAYS[date.fromisoformat(today).weekday()] not in days:
            continue
        r = plan(daily=daily, i=i, today=today, **state)
        state.update({k: r[k] for k in ("dry", "rain_until", "heat_until", "wave_until")})
        nxt = zone_next(r["offset"], r["can_lower"], baseline, height)
        if nxt < height:
            state["last_lower"] = today
        rows.append(dict(date=today, t7=r["t7"], rain3=r["rain3"], why=r["why"],
                         before=height, after=nxt, changed=int(nxt != height)))
        height = nxt
    return rows


def year(day):
    y, m = int(day[:4]), int(day[5:7])
    return f"{y}/{(y + 1) % 100:02d}" if m >= 7 else f"{y - 1}/{y % 100:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD; the first 21 days only warm up")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--baseline", type=float, default=3.5, help="the zone's usual height (cm)")
    ap.add_argument("--days", default="tue,thu,sat", help="mowing days, e.g. tue,thu,sat")
    ap.add_argument("--csv", help="write each mowing day to this file")
    a = ap.parse_args()
    rows = replay(fetch(a.lat, a.lon, a.start, a.end), a.baseline, a.days.lower().split(","))
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    by = defaultdict(list)
    for r in rows:
        by[year(r["date"])].append(r)
    for y, rs in by.items():
        counts = Counter(r["why"] for r in rs)
        changes = [f"{r['date'][5:]} {r['before']}→{r['after']}" for r in rs if r["changed"]]
        print(f"\n{y}: {len(rs)} mowing days, {len(changes)} changes (each one a question)")
        print("  " + ", ".join(f"{k} {v}" for k, v in counts.most_common()))
        print("  " + ", ".join(changes))


if __name__ == "__main__":
    main()
