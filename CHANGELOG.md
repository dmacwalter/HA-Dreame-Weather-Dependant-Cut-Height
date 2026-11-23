# Changelog

## 0.4.0

- Changes are always made automatically before the mow. The Apply now button, the
  notification's Apply now action and the `apply` action are gone; the notification says
  what will change and when, with Skip 2 days as the only button.
- A change found by Check now is a preview; the check before the next mow makes it.
- Icon and logo for the integrations page and the Marketplace (`brand/`, Home Assistant
  2026.3 or newer).
- README: Marketplace and set-up buttons.

## 0.3.0

First release as a Home Assistant integration, replacing the YAML package (kept in
`legacy/`).

- Set up from the UI. The mower's docked sensor, schedule calendar, map and zone
  selectors and zone height are found on the mower's device; zones are read from the
  Dreame zone selector.
- Weather sources (forecast entity, weather station, rain gauge, Smart Irrigation water
  balance, warnings sensor, location) can be changed later under Configure.
- Switches, usual heights, offsets and thresholds are entities on the integration's
  device; the integration keeps its own state instead of input helpers.
- Write to mower switch, off by default: checks and notifications run without changing
  the mower.
- A change found by Check now is applied only on Apply now, not by the next mow's
  schedule.
- A zone whose height was changed in the app after the check is not overwritten.
- Phone actions are `DREAME_CUT_HEIGHT_APPLY_NOW` and `DREAME_CUT_HEIGHT_SKIP`, so they
  don't clash with the package's while migrating.
- On first start, imports the package's settings, holds, last lowering, skip and pending
  change from its helpers.
