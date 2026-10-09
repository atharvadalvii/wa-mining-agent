"""Resolve a "place name" or "lat,lon" string into coordinates + a display label."""

from __future__ import annotations

import re
from functools import lru_cache

_LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class GeocodeError(Exception):
    """Raised when a place name or coordinate string cannot be resolved."""


class OutsideCoverageError(Exception):
    """Raised when a location is outside Western Australia, the only region this
    tool covers."""


# Nominatim lookups cost ~2s each and OSMnx's own disk cache doesn't avoid that
# on repeats, so memoize successful lookups for the life of the process.
# lru_cache doesn't cache raised exceptions, so failures are retried.
@lru_cache(maxsize=512)
def _geocode_place(text: str) -> tuple[float, float]:
    import osmnx as ox

    lat, lon = ox.geocode(text)
    return lat, lon


def resolve_point(text: str) -> tuple[float, float, str]:
    """Returns (lat, lon, label) for a place name or a "lat,lon" string.

    Raises OutsideCoverageError if the resolved point is outside Western Australia.
    """
    lat, lon, label = _resolve(text)

    from geoagent.geospatial.local_extract import is_within_wa

    if not is_within_wa(lat, lon):
        raise OutsideCoverageError(
            f"'{label}' resolved to ({lat:.3f}, {lon:.3f}), which is outside Western "
            "Australia. This tool only covers Western Australia. If you meant a place "
            "in WA, add the suburb or town and 'WA' to the name (e.g. 'Kalgoorlie, WA')."
        )
    return lat, lon, label


def _resolve(text: str) -> tuple[float, float, str]:
    match = _LATLON_RE.match(text)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        return lat, lon, text.strip()

    try:
        lat, lon = _geocode_place(text.strip())
    except Exception as exc:
        raise GeocodeError(
            f"Could not geocode '{text}'. Check spelling or provide 'lat,lon' coordinates instead."
        ) from exc
    return lat, lon, text
