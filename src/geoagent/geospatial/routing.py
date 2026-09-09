"""Shortest-path route computation on OSMnx street networks."""

from __future__ import annotations

from geoagent.geospatial.geocode import resolve_point
from geoagent.geospatial.models import RouteResult
from geoagent.geospatial.network import default_cache, haversine_m

_RADIUS_BUFFER_M = 500.0
_RADIUS_SAFETY_FACTOR = 0.75


class RouteNotFoundError(Exception):
    """Raised when no path exists between the origin and destination on the network."""


def path_to_route_result(
    graph,
    path: list,
    origin_label: str,
    destination_label: str,
    network_type: str,
    weight: str,
) -> RouteResult:
    """Pure summarization: turns a computed node path on `graph` into a RouteResult.

    Contains no OSMnx/network calls, so it's fully unit-testable against a
    hand-built networkx.MultiDiGraph fixture.
    """
    length_m = 0.0
    travel_time_s = 0.0
    for u, v in zip(path[:-1], path[1:]):
        edge_data = min(graph.get_edge_data(u, v).values(), key=lambda d: d.get(weight, 0))
        length_m += edge_data.get("length", 0.0)
        travel_time_s += edge_data.get("travel_time", 0.0)

    coordinates = [(graph.nodes[n]["y"], graph.nodes[n]["x"]) for n in path]

    return RouteResult(
        origin_label=origin_label,
        destination_label=destination_label,
        network_type=network_type,
        optimized_for=weight,
        length_m=length_m,
        estimated_time_min=(travel_time_s / 60.0) if travel_time_s else None,
        coordinates=coordinates,
    )


def compute_shortest_route(
    origin: str,
    destination: str,
    network_type: str = "drive",
    weight: str = "length",
) -> RouteResult:
    import networkx as nx
    import osmnx as ox

    o_lat, o_lon, o_label = resolve_point(origin)
    d_lat, d_lon, d_label = resolve_point(destination)

    mid_lat = (o_lat + d_lat) / 2
    mid_lon = (o_lon + d_lon) / 2
    span_m = haversine_m(o_lat, o_lon, d_lat, d_lon)
    radius_m = max(span_m * _RADIUS_SAFETY_FACTOR + _RADIUS_BUFFER_M, _RADIUS_BUFFER_M)

    graph = default_cache.get_for_point(mid_lat, mid_lon, radius_m, network_type)

    o_node = ox.nearest_nodes(graph, o_lon, o_lat)
    d_node = ox.nearest_nodes(graph, d_lon, d_lat)

    try:
        path = ox.routing.shortest_path(graph, o_node, d_node, weight=weight)
    except nx.NetworkXNoPath:
        path = None

    if path is None:
        raise RouteNotFoundError(
            f"No {network_type} route found between '{o_label}' and '{d_label}'."
        )

    return path_to_route_result(graph, path, o_label, d_label, network_type, weight)
