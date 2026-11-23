# Dreame weather-dependent cut height

A Home Assistant setup that sets a Dreame robot mower's cutting height per zone from the
weather: lower after heavy wet-season rain, higher in heat, dry spells and heatwaves. It
asks you first, then does it itself. Mowing times stay in the Dreame app.

Based on [edbyford/ha-navimow-weather-cut-height](https://github.com/edbyford/ha-navimow-weather-cut-height),
rewritten for a Dreame A1 and a warm-season lawn in Townsville. The seasonal rules
(autumn raise, winter pause) are gone and the rules are per zone. Notes and sources:
[`docs/tropical-cut-height-notes.md`](docs/tropical-cut-height-notes.md).

> Shared as a reference for how I did it, not a turnkey add-on. Change the entity names
> to match your setup.

## How it decides

Each zone has a **baseline** (Raised Lawn: 3.5 cm). The weather picks an offset, which is
added to every zone's baseline:

| Condition | Default rule | Offset | Raised Lawn |
| --- | --- | --- | --- |
| Normal | | 0 | 3.5 cm |
| After heavy rain | 25 mm in 3 days (or 24 h at your gauge) during the growing season (7-day mean 23 °C or more); held 5 days | -0.5 | 3.0 cm |
| Heat | max 34 °C or more today or in the next 2 days; held 3 days | +0.5 | 4.0 cm |
| Dry spell | Smart Irrigation water balance -15 mm or lower, until it is back to 0 | +0.5 | 4.0 cm |
| Heatwave | 3-day mean of (max + min) / 2 at 29.5 °C or more (Bureau of Meteorology style); held 3 days | +1.0 | 4.5 cm |

- Heatwave beats heat or dry, which beat heavy rain.
- **Raise at once, lower slowly:** one 0.5 cm step at most every 2 days.
- Targets stay on the A1's 3.0 to 7.0 cm range, in 0.5 cm steps.
- Every threshold and offset is a helper you can change from the dashboard.

## Ask, then apply

- **An hour before each scheduled mow** (from `calendar.a1_schedule`, the mower's active
  app schedule), the plan is fixed and each zone's height is read from the mower. Any
  change gets one phone notification with **Apply now** and **Skip 2 days**.
- With no answer, it's written **5 minutes before the mow** if the mower is docked,
  otherwise at its next dock.
- The height is read back 2 minutes after the write, and you're told if it didn't take.

Heights are written with the integration's `dreame_lawn_mower.plan_zone_mowing_preference_update`
action, with an explicit zone id, so only the height for that zone changes. Reading a
zone's height means pointing Home Assistant's zone selector (`select.a1_zone_2`) at it;
that selector is local to Home Assistant and doesn't change anything on the mower.

## Scheduling: leave it in the Dreame app

The Dreame app keeps the schedule, and Home Assistant just follows it through the
calendar. That way the mower still mows on time if Home Assistant is down, and you can
change the schedule in the app without touching this.

My schedule ("Before watering": Tuesday, Thursday and Saturday evenings) already lines up
with the irrigation, which runs in the early hours of Wednesday, Friday and Sunday. The
lawn is cut dry, then watered.

## Smart Irrigation

- **Dry spells** come from Smart Irrigation's water balance for the Raised Lawn
  (`sensor.smart_irrigation_raised_lawn_bucket`). Unlike a plain ET-minus-rain deficit,
  it knows about the watering, so a dry spell means the irrigation is falling behind (for
  example under council restrictions), not just that it hasn't rained.
- **Heavy rain** also counts your own gauge (`sensor.gw3000c_24h_rain_piezo`), so a local
  downpour the model missed still counts.
- Both are optional. If either sensor is unavailable, the plan falls back to Open-Meteo.

## On the mower card

`dashboards/cut_height_card.yaml` is the Dreame
[lawn-mower-card](https://github.com/EvotecIT/lovelace-lawn-mower-card) with the
smart settings added:

- **Zone choice:** left to its own discovery, the card only shows the zone selector
  when the mowing action is "Zone". On "All area" you can't pick which zone's height
  you're editing. Listing the zone selector and the zone height explicitly keeps
  them in the Mower settings sheet.
- **Smart cut height settings** in the same sheet: an on/off switch, each zone's usual
  height, the three offsets and the main thresholds.
- **Tiles** for the weather condition, the target height and the next pending change,
  plus a **Skip height changes 2 days** button.

The card shows only number, switch, select and time entities as controls, so the
package mirrors its `input_number` helpers as `number.cut_height_*` entities, and the
automations as `switch.cut_height_smart`.

## Weather

Daily data from [Open-Meteo](https://open-meteo.com/) (free, no key) for your Home
zone's coordinates: the past 21 days (temperature, rain, evapotranspiration) and 6 days of
forecast. No location is stored in these files; the URL is built from `zone.home`.

## Tested

- `reference/plan.py` is the logic in Python; `custom_templates/cut_height.jinja` is the
  same logic as Jinja macros, which is what Home Assistant runs.
- `tests/test_plan.py`: unit tests for each rule.
- `tests/test_parity_plan_ha.py`: renders the macros on a live Home Assistant and checks
  they match the Python for 67 cases (7 fixed, 60 random). Read-only.
- `tools/replay.py`: replays the rules over past weather, mowing day by mowing day, so
  you can tune the thresholds before installing.

## Layout

- `packages/dreame_cut_height.yaml`: the Open-Meteo sensor, the plan sensor, helpers and
  tunables, the read and notify scripts, and the three automations.
- `custom_templates/cut_height.jinja`: the zone list and the decision macros.
- `reference/plan.py`: the same decision in Python (the test oracle).
- `tools/replay.py`: replay over past weather.
- `dashboards/cut_height_card.yaml`: the lawn-mower-card with zone choice and the
  smart settings.
- `docs/tropical-cut-height-notes.md`: the rules, their reasoning and sources.
- `scripts/`: SSH/API helper and a deploy script (set `HA_IP`, `HA_KEY`, `HA_TOKEN`).

## Setup

1. Install [EvotecIT/homeassistant-dreamelawnmower](https://github.com/EvotecIT/homeassistant-dreamelawnmower)
   (HACS) and check you have `lawn_mower.<mower>`, `calendar.<mower>_schedule`,
   `binary_sensor.<mower>_docked`, `select.<mower>_map`, `select.<mower>_zone` and
   `number.<mower>_selected_zone_mowing_height`.
2. In the app, set the map's mowing preferences to **Custom** (per zone), not Global.
3. Edit the entity IDs at the top of `packages/dreame_cut_height.yaml`, the zone list
   and the two optional sources in `custom_templates/cut_height.jinja`, and the map
   option (`Back Yard (#2)`) in the read script.
4. Copy `custom_templates/cut_height.jinja` to `/config/custom_templates/` and
   `packages/dreame_cut_height.yaml` to `/config/packages/`, with packages enabled:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
5. Check the config and restart.
6. Set the helper values in `packages/cut_height_initial_values.md`, including resetting
   four date helpers.
7. Before trusting it, do one supervised write: with the mower docked, run
   `dreame_lawn_mower.plan_zone_mowing_preference_update` with `zone_id: 1` and a height,
   first with `execute: false` (a dry run, shown in a notification), then for real, and
   check the app shows the new height for that zone.

`scripts/deploy.sh` does steps 4 and 5 if you have the Terminal & SSH app.

The `input_*` helpers can also be created in the UI (Settings > Devices & services >
Helpers) instead of in the package, as long as their entity IDs match. Remove their
sections from the package if you do, or Home Assistant will report duplicates. That's how
they're set up on my install, because the tool I deployed with can't write `input_*`
keys to package files.

## Test

    python3 -m venv .venv && .venv/bin/pip install pytest
    .venv/bin/python -m pytest          # unit tests; live parity test runs if HA_URL/HA_TOKEN set
    .venv/bin/python -m tools.replay --lat -19.26 --lon 146.82 --start 2024-07-01 --end 2026-06-30

## Requirements

- Home Assistant 2025.4 or newer (the read script updates a variable inside a loop).
  Built on 2026.11.
- EvotecIT/homeassistant-dreamelawnmower, built against v0.2.196 on a Dreame A1. It's
  unofficial and uses Dreame's cloud, so it can break if Dreame changes it. Its write
  actions are marked for supervised use, so keep an eye on the read-back messages at
  first.

## Licence

MIT. See `LICENSE`.
