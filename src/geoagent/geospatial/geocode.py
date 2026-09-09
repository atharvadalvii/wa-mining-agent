"""Resolve a "place name" or "lat,lon" string into coordinates + a display label."""

from __future__ import annotations

import re

_LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class GeocodeError(Exception):
    """Raised when a place name or coordinate string cannot be resolved."""


def resolve_point(text: str) -> tuple[float, float, str]:
    """Returns (lat, lon, label) for a place name or a "lat,lon" string."""
    match = _LATLON_RE.match(text)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        return lat, lon, text.strip()

    import osmnx as ox

    try:
        lat, lon = ox.geocode(text)
    except Exception as exc:
        raise GeocodeError(
            f"Could not geocode '{text}'. Check spelling or provide 'lat,lon' coordinates instead."
        ) from exc
    return lat, lon, text
