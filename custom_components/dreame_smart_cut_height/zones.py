"""Zone names and ids from the Dreame zone selector's options (pure, no HA imports).

The Dreame integration labels zones like "Raised Lawn (#1)", or "Zone #3" for a zone
with no name in the app. The number after # is the zone id its services use.
"""
from __future__ import annotations

import re

_ID = re.compile(r"#(\d+)\)?\s*$")
_SUFFIX = re.compile(r"\s*\(#\d+\)\s*$")


def zone_id(option: str) -> int | None:
    match = _ID.search(str(option))
    return int(match.group(1)) if match else None


def zone_name(option: str) -> str:
    name = _SUFFIX.sub("", str(option)).strip()
    return name or str(option)


def zones_from_options(options, known=None) -> list[dict]:
    """[{id, name}] for every option with a zone id, keeping zones already known.

    A zone the selector no longer lists (the mower was offline, say) stays, so its
    settings and entities survive; ids are unique and sorted.
    """
    zones = {int(z["id"]): dict(z) for z in (known or [])}
    for option in options or []:
        zid = zone_id(option)
        if zid is not None:
            zones[zid] = {"id": zid, "name": zone_name(option)}
    return [zones[k] for k in sorted(zones)]


def option_for(options, zid: int) -> str | None:
    """The selector option for a zone id, under whatever label the app gives it now."""
    for option in options or []:
        if zone_id(option) == int(zid):
            return option
    return None
