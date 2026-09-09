"""v1 tool wrappers: street network fetch, shortest-path routing, isochrones."""

from __future__ import annotations

from geoagent.geospatial.isochrone import compute_isochrone
from geoagent.geospatial.mapping import save_isochrone_map, save_route_map
from geoagent.geospatial.network import get_network_summary
from geoagent.geospatial.routing import compute_shortest_route
from geoagent.tools.registry import ToolSpec, register


def _with_map_export(text: str, save_map) -> str:
    """Appends the saved map's file path to a tool result, or a note if export failed.

    Map export is a nice-to-have alongside the actual routing/isochrone data, so a
    failure here (e.g. an unwritable maps directory) must not lose the real result.
    """
    try:
        map_path = save_map()
    except Exception as exc:
        return f"{text} (map export failed: {exc})"
    return f"{text} Map saved to {map_path}."


def handle_get_street_network(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: float = 1500,
    network_type: str = "drive",
) -> str:
    summary = get_network_summary(
        place=place, lat=lat, lon=lon, radius_m=radius_m, network_type=network_type
    )
    return summary.to_tool_text()


def handle_shortest_route(
    origin: str,
    destination: str,
    network_type: str = "drive",
    weight: str = "length",
) -> str:
    result = compute_shortest_route(
        origin=origin, destination=destination, network_type=network_type, weight=weight
    )
    return _with_map_export(result.to_tool_text(), lambda: save_route_map(result))


def handle_isochrone(
    center: str,
    minutes: float,
    network_type: str = "walk",
) -> str:
    result = compute_isochrone(center=center, minutes=minutes, network_type=network_type)
    return _with_map_export(result.to_tool_text(), lambda: save_isochrone_map(result))


register(
    ToolSpec(
        name="get_street_network",
        description=(
            "Fetch (or load from cache) the street network graph for a place name or a "
            "lat/lon point with a radius. Use this to check network size/coverage before "
            "routing, or to explore an area. Returns a summary (node/edge counts, bounding "
            "box), not the raw graph."
        ),
        parameters={
            "type": "object",
            "properties": {
                "place": {
                    "type": "string",
                    "description": (
                        "A place name geocodable via Nominatim, e.g. 'Pune, India'. "
                        "Mutually exclusive with lat/lon."
                    ),
                },
                "lat": {
                    "type": "number",
                    "description": "Latitude of center point. Requires lon and radius_m.",
                },
                "lon": {
                    "type": "number",
                    "description": "Longitude of center point. Requires lat and radius_m.",
                },
                "radius_m": {
                    "type": "number",
                    "description": "Radius in meters around lat/lon to fetch. Default 1500.",
                    "default": 1500,
                },
                "network_type": {
                    "type": "string",
                    "enum": ["drive", "walk", "bike", "all"],
                    "default": "drive",
                },
            },
            "required": [],
        },
        handler=handle_get_street_network,
    )
)

register(
    ToolSpec(
        name="shortest_route",
        description=(
            "Compute the shortest-path route between two locations on the street network, "
            "by driving/walking/biking distance or travel time. Locations can be place names "
            "or 'lat,lon' strings. Fetches/caches the network automatically."
        ),
        parameters={
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Place name OR 'lat,lon' string for the start point.",
                },
                "destination": {
                    "type": "string",
                    "description": "Place name OR 'lat,lon' string for the end point.",
                },
                "network_type": {
                    "type": "string",
                    "enum": ["drive", "walk", "bike"],
                    "default": "drive",
                },
                "weight": {
                    "type": "string",
                    "enum": ["length", "travel_time"],
                    "default": "length",
                    "description": "Optimize for shortest distance or fastest time.",
                },
            },
            "required": ["origin", "destination"],
        },
        handler=handle_shortest_route,
    )
)

register(
    ToolSpec(
        name="isochrone",
        description=(
            "Compute the reachable area (isochrone) from a point within a given travel time, "
            "on the street network. Returns area, approximate reach radius, and node count "
            "within reach — not raw polygon geometry."
        ),
        parameters={
            "type": "object",
            "properties": {
                "center": {
                    "type": "string",
                    "description": "Place name OR 'lat,lon' for the center point.",
                },
                "minutes": {
                    "type": "number",
                    "description": "Travel time budget in minutes.",
                },
                "network_type": {
                    "type": "string",
                    "enum": ["drive", "walk", "bike"],
                    "default": "walk",
                },
            },
            "required": ["center", "minutes"],
        },
        handler=handle_isochrone,
    )
)
