# First-run values

YAML helpers without `initial:` start at their slider minimum, then keep whatever you set
across restarts. Set these once after the first load (Settings > Devices & Services >
Helpers, or `input_number.set_value`):

| Helper | Value | Meaning |
| --- | --- | --- |
| `input_number.cut_height_baseline_zone_1` | 3.5 | Raised Lawn's usual height (cm) |
| `input_number.cut_height_rain_offset` | -0.5 | added after heavy rain while growing (3.5 → 3.0) |
| `input_number.cut_height_hot_offset` | 0.5 | added in heat or a dry spell (3.5 → 4.0) |
| `input_number.cut_height_heatwave_offset` | 1.0 | added in a heatwave (3.5 → 4.5) |
| `input_number.cut_height_dry_season_offset` | 0.5 | added May to September when nothing else applies (3.5 → 4.0) |
| `input_number.cut_height_grow_temp` | 23 | wet season only: 7-day mean (°C) at or above which heavy rain lowers the cut |
| `input_number.cut_height_heavy_rain` | 25 | rain (mm) in 3 days, or 24 h at your gauge, that counts as heavy |
| `input_number.cut_height_hot_max_temp` | 34 | a day this hot (max), today or the next 2 days, counts as heat |
| `input_number.cut_height_heatwave_temp` | 29.5 | heatwave when 3 days average this, using (max + min) / 2 |
| `input_number.cut_height_dry_bucket` | -15 | dry when the Smart Irrigation water balance is at or below this (mm) |
| `input_number.cut_height_dry_deficit` | 60 | fallback with no water balance: 21-day ET0 minus rain (mm) |

New YAML `input_datetime`s start at **today**, not 1970. Set
`input_datetime.cut_height_rain_until`, `input_datetime.cut_height_heat_until`,
`input_datetime.cut_height_heatwave_until` and `input_datetime.cut_height_last_lower` to
`1970-01-01`, or the first check will think there is a hold running.

## Adding a zone

1. Add `cut_height_baseline_zone_2` (or the zone's id) under `input_number:` in the package.
2. Add the zone to `cut_height_zones()` in `custom_templates/cut_height.jinja`, with its
   option exactly as `select.a1_zone_2` shows it (for example `Orchard (#2)`).
3. Reload custom templates and input numbers, then set the new baseline.

The offsets apply to every zone. The dry-spell rule reads one Smart Irrigation water
balance (the Raised Lawn's); point it at another zone's in `cut_height_plan_live()` if
that zone matters more.
