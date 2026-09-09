"""Auto-export routes/isochrones as interactive HTML maps via folium."""

from __future__ import annotations

import re
from pathlib import Path

from geoagent.geospatial.models import IsochroneResult, RouteResult

_maps_dir = Path("maps")


def configure_maps_dir(path: Path) -> None:
    global _maps_dir
    _maps_dir = path
    _maps_dir.mkdir(parents=True, exist_ok=True)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:80] or "map"


def save_route_map(result: RouteResult) -> Path:
    import folium

    if not result.coordinates:
        raise ValueError("Route has no coordinates to plot.")

    _maps_dir.mkdir(parents=True, exist_ok=True)
    center = result.coordinates[len(result.coordinates) // 2]
    fmap = folium.Map(location=center, zoom_start=14, tiles="OpenStreetMap")
    folium.PolyLine(result.coordinates, color="#1a73e8", weight=5, opacity=0.85).add_to(fmap)
    folium.Marker(
        result.coordinates[0],
        tooltip=f"Start: {result.origin_label}",
        icon=folium.Icon(color="green"),
    ).add_to(fmap)
    folium.Marker(
        result.coordinates[-1],
        tooltip=f"End: {result.destination_label}",
        icon=folium.Icon(color="red"),
    ).add_to(fmap)
    fmap.fit_bounds(result.coordinates)

    filename = _slugify(f"route-{result.origin_label}-to-{result.destination_label}") + ".html"
    out_path = _maps_dir / filename
    fmap.save(str(out_path))
    return out_path


def save_isochrone_map(result: IsochroneResult) -> Path:
    import folium

    if not result.hull_coords:
        raise ValueError("Isochrone has no boundary to plot.")

    _maps_dir.mkdir(parents=True, exist_ok=True)
    fmap = folium.Map(location=result.center_point, zoom_start=14, tiles="OpenStreetMap")
    folium.Polygon(
        result.hull_coords,
        color="#e8710a",
        weight=2,
        fill=True,
        fill_opacity=0.25,
        tooltip=f"{result.minutes:.0f} min {result.network_type} isochrone",
    ).add_to(fmap)
    folium.Marker(result.center_point, tooltip=f"Center: {result.center_label}").add_to(fmap)
    fmap.fit_bounds(result.hull_coords)

    filename = (
        _slugify(f"isochrone-{result.center_label}-{result.minutes:.0f}min-{result.network_type}")
        + ".html"
    )
    out_path = _maps_dir / filename
    fmap.save(str(out_path))
    return out_path
