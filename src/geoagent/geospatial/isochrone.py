"""Isochrone (reachable-area) computation via ego-graph + convex hull."""

from __future__ import annotations

from geoagent.geospatial.geocode import resolve_point
from geoagent.geospatial.models import IsochroneResult
from geoagent.geospatial.network import default_cache

# Generous upper-bound speeds (km/h) used only to size the network fetch radius
# so the ego-graph's true travel-time boundary isn't clipped by an
# under-fetched area. Actual travel times still come from real edge data.
_MAX_SPEED_KPH = {"walk": 6.0, "bike": 20.0, "drive": 40.0}
_RADIUS_SAFETY_FACTOR = 1.2
_MIN_RADIUS_M = 500.0
_MAX_RADIUS_M = 8_000.0


def _fetch_radius_m(minutes: float, network_type: str) -> float:
    speed_kph = _MAX_SPEED_KPH.get(network_type, _MAX_SPEED_KPH["drive"])
    distance_m = minutes * 60.0 * (speed_kph * 1000.0 / 3600.0)
    return min(max(distance_m * _RADIUS_SAFETY_FACTOR, _MIN_RADIUS_M), _MAX_RADIUS_M)


def compute_isochrone(
    center: str,
    minutes: float,
    network_type: str = "walk",
) -> IsochroneResult:
    import networkx as nx
    import osmnx as ox

    c_lat, c_lon, c_label = resolve_point(center)

    radius_m = _fetch_radius_m(minutes, network_type)
    graph = default_cache.get_for_point(c_lat, c_lon, radius_m, network_type)
    center_node = ox.nearest_nodes(graph, c_lon, c_lat)

    subgraph = nx.ego_graph(
        graph, center_node, radius=minutes * 60.0, distance="travel_time"
    )
    n_reachable = subgraph.number_of_nodes()

    points_gdf = ox.convert.graph_to_gdfs(subgraph, edges=False)
    projected = ox.projection.project_gdf(points_gdf)
    hull = projected.union_all().convex_hull
    area_km2 = hull.area / 1_000_000.0
    approx_radius_m = (hull.area / 3.14159265) ** 0.5

    # Unprojected hull (lon/lat, as OSMnx stores node x/y) for map rendering;
    # the projected hull above is only for the accurate area_km2 calculation.
    # A tiny/degenerate reachable set can produce a Point or LineString instead
    # of a Polygon, which has no `.exterior` — leave hull_coords empty then.
    hull_lonlat = points_gdf.union_all().convex_hull
    hull_coords = (
        [(lat, lon) for lon, lat in hull_lonlat.exterior.coords]
        if hull_lonlat.geom_type == "Polygon"
        else []
    )

    return IsochroneResult(
        center_label=c_label,
        minutes=minutes,
        network_type=network_type,
        n_reachable_nodes=n_reachable,
        area_km2=area_km2,
        approx_radius_m=approx_radius_m,
        center_point=(c_lat, c_lon),
        hull_coords=hull_coords,
    )
