"""Integration tests that hit real OSM/Overpass services. Run with: pytest -m integration"""

import pytest

pytestmark = pytest.mark.integration

# Small fixed radius around a well-mapped landmark (Perth, Australia CBD) to keep
# the Overpass request small, fast, and deterministic.
_LAT, _LON = -31.9523, 115.8613
_NEARBY_LAT, _NEARBY_LON = -31.9505, 115.8605


@pytest.fixture(autouse=True)
def use_temp_cache(tmp_path, monkeypatch):
    from geoagent.config import configure_osmnx

    configure_osmnx(tmp_path / "osmnx_cache")


def test_fetch_network_for_point_returns_nonempty_graph():
    from geoagent.geospatial.network import fetch_network_for_point

    graph = fetch_network_for_point(_LAT, _LON, radius_m=500, network_type="drive")
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0


def test_compute_shortest_route_between_nearby_points():
    from geoagent.geospatial.routing import compute_shortest_route

    result = compute_shortest_route(
        origin=f"{_LAT},{_LON}",
        destination=f"{_NEARBY_LAT},{_NEARBY_LON}",
        network_type="drive",
        weight="length",
    )
    assert result.length_m > 0
    assert len(result.coordinates) > 0
