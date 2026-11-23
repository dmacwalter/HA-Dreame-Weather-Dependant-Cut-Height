# Notes: cut height for a warm-season lawn in the dry tropics

The Navimow original was written for southern England: lower in summer, higher for
autumn and winter, and a winter pause. None of that fits Townsville, where the grass
never stops growing for winter and the stresses are heat, the dry season and wet-season
downpours. This version keeps the original's machinery (Open-Meteo history, ask then
apply, raise at once and lower slowly, a Python oracle with tests) and replaces the
seasonal rules.

## The rules and why

| Condition | Rule (defaults) | Offset |
| --- | --- | --- |
| Normal | wet season (October to April), none of the below | 0 |
| After heavy rain | wet season only: 25 mm or more in 3 days (Open-Meteo), or 24 h at your gauge, while the 7-day mean is 23 °C or more; held 5 days | -0.5 cm |
| Dry season | May to September, none of the below | +0.5 cm |
| Heat | a BOM forecast max of 34 °C or more today or in the next 2 days; held 3 days | +0.5 cm |
| Dry spell | Smart Irrigation water balance at -15 mm or below, until it is back to 0 | +0.5 cm |
| Heatwave | a current BOM heatwave warning, or a 3-day mean of (max + min) / 2 at 29.5 °C or more in any window ending today to 2 days ahead; held 3 days | +1.0 cm |

Priority, highest first: heatwave, heat or dry spell, heavy rain, dry season, normal.

### Townsville's seasons

The Bureau of Meteorology defines the northern Australian wet season as 1 October to
30 April and the dry season as 1 May to 30 September, and those are the months used
here. Townsville's real rains usually come later than October, so October to December
mostly behave like a hot build-up: heat and dry-spell rules do the work, and the
after-rain drop only fires on a genuine downpour.

- **Wet season.** Warm-season grass grows fastest, and a big fall pushes a surge, so
  heavy rain takes the cut down half a centimetre for five days. The 7-day mean guard
  (23 °C) stops a cool, wet April week from triggering it.
- **Dry season.** Nights are cooler, growth slows, rain is scarce and council watering
  restrictions apply. A slightly taller cut (+0.5 cm by default) shades the soil and
  holds moisture, and with slower growth the mower isn't fighting to keep up. Heavy rain
  doesn't lower the cut in the dry season. Set the dry-season offset to 0 to mow at the
  baseline all year.
- **Coming back.** On 1 October the height steps back down from the dry-season height,
  half a centimetre per apply. Heat wins over
rain on purpose: a hot spell straight after a downpour is when the grass is most
stressed, and cutting low then works against it. Swap the order in `cut_height_plan()` and
`reference/plan.py` if you'd rather.

Each zone's target is its baseline plus the offset, on the A1's 0.5 cm grid, kept within
3.0 to 7.0 cm. Raises happen at once; lowering is one 0.5 cm step per apply, no more than
every 2 days. With mows on Tuesday, Thursday and Saturday, coming down from a heatwave
(4.5 cm) to normal (3.5 cm) takes two mows.

### Raising in heat and drought

Extension guidance for warm-season grasses is consistent: keep to the upper end of the
species' range when stressed, and never take more than a third of the leaf at once. The
University of Arizona says to raise the cut during summer heat stress, for more root
growth and to shelter the crown where new shoots come from. Oklahoma State recommends a
higher height through the growing season ahead of drought, since taller grass shades the
soil and holds moisture. Texas A&M's warm-season mowing publication favours the higher end
of each species' range for stress tolerance. Half a centimetre, or a full one in a
heatwave, is within those ranges.

### Lowering after heavy rain

After a big wet-season fall the grass surges. Taking it down half a centimetre while that
is happening keeps the lawn tidy without breaking the one-third rule, since the mower is
cutting every two days. It only applies while the 7-day mean says the grass is in its
growing season (23 °C by default); a heavy dry-season shower doesn't trigger it.

### Heatwave: the Bureau's definition, simplified

The Bureau of Meteorology defines a heatwave as three days where maximum and minimum
temperatures are both unusually high for the place. It measures this with the excess heat
factor (EHF). The significant part of the EHF compares the 3-day mean of daily mean
temperature, (max + min) / 2, against the 95th percentile of daily mean temperature for
that location (T95).

This setup uses only that significant part: heatwave when the 3-day mean is at or above
T95. It leaves out the acclimatisation term (how the last 3 days compare with the previous
30), so it will now and then call a heatwave that the Bureau wouldn't.

**T95 for Townsville is an estimate.** The default of 29.5 °C comes from Townsville Aero's
summer averages (January mean max 31.5 °C, mean min 24.4 °C, so a typical daily mean near
28 °C), not from the Bureau's own percentile. Check it with `tools/replay.py` against past
summers. It should flag the real heatwaves you remember, and not every warm week in
January.

### Bureau of Meteorology data

The forecast max and min for today and the next days come from the BOM forecast for
the lawn's location (through the `bureau_of_meteorology` integration), with Open-Meteo
as the fallback and the source for past days, rain history and evapotranspiration. A
BOM heatwave warning current for the location counts as a heatwave on its own, whatever
the 29.5 °C estimate says, because the Bureau's warning uses the full excess heat factor
and the real local percentile.

### Local measurement for past days

Past days come from the weather station in the garden, through Home Assistant's
long-term statistics, rather than from a weather model. Over 2 to 23 November 2026 the
station and Open-Meteo agreed closely on temperature, but on 20 November the station
measured 10.6 mm of rain and Open-Meteo reported 20.1 mm. A model can easily double or
halve a tropical shower at one address, and the after-rain rule keys off exactly that
figure. OpenWeatherMap History was considered and not used: it keeps only 5 past days,
fewer than the 7-day mean needs.

### Hot day threshold

34 °C is a little above Townsville's summer typical maximum (31.5 °C in January at the
airport) and below its record highs, so it marks a properly hot day rather than a normal
wet-season one. Belgian Gardens sits nearer the coast than the airport, so tune it to
your own sensors if needed.

### Dry spells and Smart Irrigation

The original measured a dry spell as 21 days of reference evapotranspiration minus rain.
On an irrigated lawn that overstates it, because it can't see the watering. Smart
Irrigation's water balance can: it counts ET, rain and the watering Hydrawise has done.
So when the water balance is available it is used instead. A dry spell is then a lawn the
irrigation is falling behind on, for example under council restrictions. The Open-Meteo
deficit is only a fallback, for when the Smart Irrigation sensor is unavailable.

## What the mower already handles

The A1's own rain protection (with its after-rain delay) still decides whether to mow on a
wet day. This setup only changes the height. It doesn't start, stop or reschedule mowing,
and it never touches the app schedule.

## Sources

- Bureau of Meteorology, *Climate in Australia* (northern wet season 1 October to
  30 April, dry season 1 May to 30 September):
  https://www.bom.gov.au/resources/learn-and-explore/climate-knowledge-centre

- Bureau of Meteorology, *What is a heatwave?* (heatwave definition and use of the EHF):
  https://www.bom.gov.au/resources/learn-and-explore/heatwave-knowledge-centre/what-is-a-heatwave
- EHF formula, significant excess heat index against T95: appendix of *Evaluation and
  statistical correction of area-based heat index forecasts that drive a heatwave warning
  service*, https://arxiv.org/pdf/2407.10434
- Townsville Aero (032040) climate statistics:
  https://www.bom.gov.au/climate/averages/tables/cw_032040.shtml
- University of Arizona Cooperative Extension, AZ1681 (raise the cut in summer heat stress;
  one-third rule): https://www.extension.arizona.edu/sites/default/files/2024-08/az1681-2015.pdf
- Oklahoma State Extension, *Preparing your lawn for drought*:
  https://extension.okstate.edu/fact-sheets/preparing-your-lawn-for-drought.html
- Texas A&M AgriLife, *Mowing recommendations for warm-season turfgrass lawns*:
  https://mytexas.ag.tamu.edu/wp-content/uploads/2026/03/mowing-recommendations-for-warm-season-turfgrasses.pdf
