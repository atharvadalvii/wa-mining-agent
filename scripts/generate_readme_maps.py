"""Regenerates the README's three example maps from the real tools.

For each example question this runs the actual geospatial functions (live DMIRS
queries, local WA street network), writes a self-contained interactive HTML map
to assets/maps/, and takes a screenshot of it to assets/ for the README to show
(GitHub strips scripts from READMEs, so the screenshot links to the HTML).

Needs the local WA extract (python -m geoagent.setup_local_wa), network access for
map tiles and DMIRS, and Playwright with Google Chrome installed.

Run from the repo root: python scripts/generate_readme_maps.py
"""

from __future__ import annotations

import os
from pathlib import Path

import folium

os.environ.setdefault("OPENAI_API_KEY", "unused")  # settings loader requires one

from geoagent.config import configure_osmnx, load_settings  # noqa: E402
from geoagent.geospatial import local_extract  # noqa: E402
from geoagent.geospatial.isochrone import compute_isochrone  # noqa: E402
from geoagent.geospatial.routing import compute_shortest_route  # noqa: E402
from geoagent.geospatial.wa_mining import find_mining_deposits  # noqa: E402

ASSETS = Path("assets")
MAPS = ASSETS / "maps"

ISOCHRONE_QUESTION = "How far can a crew drive from Leonora in 60 minutes?"
DEPOSITS_QUESTION = "Gold deposits within 25 km of Kalgoorlie"
ROUTE_QUESTION = "Fastest driving route from Kalgoorlie to Kambalda"


def _banner(fmap: folium.Map, question: str, answer: str) -> None:
    html = f"""
    <div style="position:fixed;top:12px;left:56px;right:12px;z-index:9999;max-width:640px;
                background:rgba(255,255,255,.95);padding:10px 14px;border-radius:8px;
                box-shadow:0 1px 6px rgba(0,0,0,.3);font-family:system-ui,sans-serif">
      <div style="font-size:12px;color:#666">Question</div>
      <div style="font-size:15px;font-weight:600;margin-bottom:6px">{question}</div>
      <div style="font-size:13px;color:#222">{answer}</div>
    </div>"""
    fmap.get_root().html.add_child(folium.Element(html))


def build_isochrone() -> folium.Map:
    r = compute_isochrone("Leonora, Western Australia", 60, "drive")
    fmap = folium.Map(location=r.center_point, zoom_start=9, tiles="OpenStreetMap")
    folium.Polygon(
        r.hull_coords,
        color="#e8710a",
        weight=2,
        fill=True,
        fill_opacity=0.25,
        tooltip=f"{r.minutes:.0f}-minute drive area",
    ).add_to(fmap)
    folium.Marker(r.center_point, tooltip="Leonora").add_to(fmap)
    fmap.fit_bounds(r.hull_coords, padding=(30, 30))
    _banner(
        fmap,
        ISOCHRONE_QUESTION,
        f"Reachable area: about {r.area_km2:,.0f} km² (roughly {r.approx_radius_m / 1000:.0f} km "
        "radius) over the road network.",
    )
    return fmap


def build_deposits() -> folium.Map:
    r = find_mining_deposits("Kalgoorlie, Western Australia", radius_km=25, commodity="gold")
    points = [
        (s["latitude"], s["longitude"], s)
        for s in r.sites
        if s.get("latitude") is not None and s.get("longitude") is not None
    ]
    centre = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
    fmap = folium.Map(location=centre, zoom_start=11, tiles="OpenStreetMap")
    for lat, lon, s in points:
        folium.CircleMarker(
            (lat, lon),
            radius=6,
            color="#b8860b",
            fill=True,
            fill_opacity=0.85,
            tooltip=f"{s.get('site_title')} — {s.get('site_type_')}, {s.get('site_stage')}",
        ).add_to(fmap)
    fmap.fit_bounds([(p[0], p[1]) for p in points], padding=(40, 40))
    _banner(
        fmap,
        DEPOSITS_QUESTION,
        f"{r.total_count:,} gold sites found; the {len(points)} shown are the first returned. "
        "Hover a point for its name, type and stage.",
    )
    return fmap


def build_route() -> folium.Map:
    r = compute_shortest_route("Kalgoorlie, WA", "Kambalda, WA", "drive", "travel_time")
    fmap = folium.Map(location=r.coordinates[len(r.coordinates) // 2], zoom_start=11)
    folium.PolyLine(r.coordinates, color="#1a73e8", weight=5, opacity=0.85).add_to(fmap)
    folium.Marker(r.coordinates[0], tooltip="Start: Kalgoorlie", icon=folium.Icon(color="green")).add_to(fmap)
    folium.Marker(r.coordinates[-1], tooltip="End: Kambalda", icon=folium.Icon(color="red")).add_to(fmap)
    fmap.fit_bounds(r.coordinates, padding=(40, 40))
    _banner(
        fmap,
        ROUTE_QUESTION,
        f"{r.length_m / 1000:.1f} km, about {r.estimated_time_min:.0f} minutes by road.",
    )
    return fmap


EXAMPLES = {
    "example-isochrone": build_isochrone,
    "example-deposits": build_deposits,
    "example-route": build_route,
}


def main() -> None:
    settings = load_settings()
    configure_osmnx(
        settings.cache_dir,
        overpass_url=settings.overpass_url,
        overpass_rate_limit=settings.overpass_rate_limit,
    )
    local_extract.warm_up()
    MAPS.mkdir(parents=True, exist_ok=True)

    for name, build in EXAMPLES.items():
        print(f"building {name} ...", flush=True)
        build().save(str(MAPS / f"{name}.html"))

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1200, "height": 700})
        for name in EXAMPLES:
            page.goto((MAPS / f"{name}.html").resolve().as_uri())
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)  # let map tiles finish painting
            page.screenshot(path=str(ASSETS / f"{name}.png"))
            print(f"screenshot assets/{name}.png", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
