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


# Settlement types that mean "the actual town" rather than an administrative area.
_SETTLEMENT_TYPES = {"city", "town", "village", "hamlet", "suburb", "locality", "neighbourhood"}
_ADMIN_PREFIXES = ("shire of ", "city of ", "town of ", "municipality of ")


def _nominatim_search(text: str) -> list[dict]:
    from collections import OrderedDict

    from osmnx import _nominatim

    # Goes through OSMnx's own request helper so the user-agent, disk cache and
    # Nominatim's 1 request/second limit are all handled the same as before.
    return _nominatim._nominatim_request(
        OrderedDict([("q", text), ("format", "json"), ("limit", 5)])
    )


def _pick_result(text: str, results: list[dict]) -> dict:
    """Prefers the actual settlement over an administrative boundary.

    Nominatim's first hit for "Leonora, WA" is the *Shire of Leonora* boundary, whose
    centre is ~55 km from the town, so everything computed "around Leonora" would be
    centred in empty bush. Prefer a place/settlement result named like the query,
    then any result named exactly like it that isn't a shire/city/town council area,
    then fall back to Nominatim's own top hit.
    """
    head = text.split(",")[0].strip().lower()

    def name(r: dict) -> str:
        return (r.get("name") or r.get("display_name", "").split(",")[0]).strip().lower()

    for r in results:
        if r.get("class") == "place" and r.get("type") in _SETTLEMENT_TYPES and name(r) == head:
            return r
    for r in results:
        if name(r) == head and not name(r).startswith(_ADMIN_PREFIXES):
            return r
    return results[0]


# Lookups cost ~2s each (Nominatim's mandatory 1 req/s pause plus the request), so
# memoize successful ones for the life of the process. lru_cache doesn't cache
# raised exceptions, so failures are retried.
@lru_cache(maxsize=512)
def _geocode_place(text: str) -> tuple[float, float]:
    results = _nominatim_search(text)
    if not results:
        raise GeocodeError(f"Nominatim returned no results for '{text}'.")
    best = _pick_result(text, results)
    return float(best["lat"]), float(best["lon"])


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
