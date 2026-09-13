"""OSMnx graph fetching, using OSMnx's own disk cache (configured in geoagent.config)."""

from __future__ import annotations

import math
import time
from typing import Callable

import networkx as nx


class NetworkFetchError(Exception):
    """Raised when a street network graph cannot be fetched/built."""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Some public Overpass mirrors are served by multiple backend IPs whose
# reachability from a given network can flap within seconds (see
# geoagent.config's DNS re-probing) — a couple of quick retries meaningfully
# improves success odds without risking a long pile-up, since a bad-IP failure
# is a fast "connection refused", not a slow timeout.
_MAX_FETCH_ATTEMPTS = 3
_RETRY_DELAY_S = 3.0


def _fetch_with_retry(fetch_fn: Callable[[], nx.MultiDiGraph], error_prefix: str) -> nx.MultiDiGraph:
    last_exc: Exception | None = None
    for attempt in range(_MAX_FETCH_ATTEMPTS):
        try:
            return fetch_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_FETCH_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_S)
    raise NetworkFetchError(f"{error_prefix}: {last_exc}") from last_exc


def fetch_network_for_place(place: str, network_type: str = "drive") -> nx.MultiDiGraph:
    import osmnx as ox

    graph = _fetch_with_retry(
        lambda: ox.graph_from_place(place, network_type=network_type),
        f"Could not fetch a street network for '{place}'",
    )
    return _add_speeds_and_times(graph, network_type)


def fetch_network_for_point(
    lat: float, lon: float, radius_m: float, network_type: str = "drive"
) -> nx.MultiDiGraph:
    import osmnx as ox

    graph = _fetch_with_retry(
        lambda: ox.graph_from_point((lat, lon), dist=radius_m, network_type=network_type),
        f"Could not fetch a street network around ({lat}, {lon})",
    )
    return _add_speeds_and_times(graph, network_type)


def fetch_network_for_bbox(
    north: float, south: float, east: float, west: float, network_type: str = "drive"
) -> nx.MultiDiGraph:
    import osmnx as ox

    graph = _fetch_with_retry(
        lambda: ox.graph_from_bbox((west, south, east, north), network_type=network_type),
        f"Could not fetch a street network for bbox "
        f"(north={north}, south={south}, east={east}, west={west})",
    )
    return _add_speeds_and_times(graph, network_type)


# Constant travel speeds (km/h) for modes OSMnx's own speed imputation doesn't
# support: add_edge_speeds assumes motor-vehicle speeds (from maxspeed tags or
# highway-type defaults), which is meaningless for walking/cycling.
_NON_DRIVE_SPEEDS_KPH = {"walk": 5.0, "bike": 15.0}


def _add_speeds_and_times(graph: nx.MultiDiGraph, network_type: str) -> nx.MultiDiGraph:
    import osmnx as ox

    if network_type in _NON_DRIVE_SPEEDS_KPH:
        speed_mps = _NON_DRIVE_SPEEDS_KPH[network_type] * 1000.0 / 3600.0
        for _, _, _, data in graph.edges(keys=True, data=True):
            data["speed_kph"] = _NON_DRIVE_SPEEDS_KPH[network_type]
            data["travel_time"] = data.get("length", 0.0) / speed_mps
        return graph

    graph = ox.routing.add_edge_speeds(graph)
    graph = ox.routing.add_edge_travel_times(graph)
    return graph


class NetworkCache:
    """In-process, session-lifetime memoization on top of OSMnx's own disk cache.

    Avoids re-parsing cached JSON into a graph object multiple times within one
    REPL session when the same area is queried repeatedly (e.g. several routes
    within the same city in one conversation).
    """

    def __init__(self) -> None:
        self._by_place: dict[tuple[str, str], nx.MultiDiGraph] = {}
        self._by_point: dict[tuple[float, float, float, str], nx.MultiDiGraph] = {}
        self._by_bbox: dict[tuple[float, float, float, float, str], nx.MultiDiGraph] = {}

    def get_for_place(self, place: str, network_type: str) -> nx.MultiDiGraph:
        key = (place, network_type)
        if key not in self._by_place:
            self._by_place[key] = fetch_network_for_place(place, network_type)
        return self._by_place[key]

    def get_for_point(
        self, lat: float, lon: float, radius_m: float, network_type: str
    ) -> nx.MultiDiGraph:
        key = (round(lat, 4), round(lon, 4), round(radius_m, -1), network_type)
        if key not in self._by_point:
            self._by_point[key] = fetch_network_for_point(lat, lon, radius_m, network_type)
        return self._by_point[key]

    def get_for_bbox(
        self, north: float, south: float, east: float, west: float, network_type: str
    ) -> nx.MultiDiGraph:
        key = (round(north, 4), round(south, 4), round(east, 4), round(west, 4), network_type)
        if key not in self._by_bbox:
            self._by_bbox[key] = fetch_network_for_bbox(north, south, east, west, network_type)
        return self._by_bbox[key]


default_cache = NetworkCache()


def get_network_summary(
    place: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: float = 1500.0,
    network_type: str = "drive",
):
    from geoagent.geospatial.models import NetworkSummary

    if place:
        graph = default_cache.get_for_place(place, network_type)
        label = place
    elif lat is not None and lon is not None:
        graph = default_cache.get_for_point(lat, lon, radius_m, network_type)
        label = f"{lat},{lon}"
    else:
        raise NetworkFetchError("Provide either `place` or both `lat` and `lon`.")

    ys = [data["y"] for _, data in graph.nodes(data=True)]
    xs = [data["x"] for _, data in graph.nodes(data=True)]
    bbox = (max(ys), min(ys), max(xs), min(xs))

    return NetworkSummary(
        place_or_point=label,
        network_type=network_type,
        n_nodes=graph.number_of_nodes(),
        n_edges=graph.number_of_edges(),
        bbox=bbox,
    )
