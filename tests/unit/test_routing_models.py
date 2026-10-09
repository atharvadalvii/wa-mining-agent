import networkx as nx
import pytest

from geoagent.geospatial.models import IsochroneResult, NetworkSummary, RouteResult
from geoagent.geospatial.routing import RouteTooFarError, compute_shortest_route, path_to_route_result


@pytest.fixture
def fixture_graph():
    g = nx.MultiDiGraph()
    g.add_node(1, x=0.0, y=0.0)
    g.add_node(2, x=0.0, y=0.001)
    g.add_node(3, x=0.0, y=0.002)
    g.add_edge(1, 2, key=0, length=100.0, travel_time=20.0)
    g.add_edge(2, 3, key=0, length=150.0, travel_time=30.0)
    return g


def test_path_to_route_result_sums_length_and_time(fixture_graph):
    result = path_to_route_result(
        fixture_graph, [1, 2, 3], "A", "B", network_type="walk", weight="length"
    )
    assert result.length_m == pytest.approx(250.0)
    assert result.estimated_time_min == pytest.approx(50.0 / 60.0)
    assert result.n_waypoints == 3
    assert result.coordinates == [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)]


def test_route_result_to_tool_text_contains_key_facts(fixture_graph):
    result = path_to_route_result(
        fixture_graph, [1, 2, 3], "Start", "End", network_type="drive", weight="length"
    )
    text = result.to_tool_text()
    assert "Start" in text
    assert "End" in text
    assert "0.25 km" in text


def test_route_result_to_tool_text_handles_missing_time():
    result = RouteResult(
        origin_label="A",
        destination_label="B",
        network_type="walk",
        optimized_for="length",
        length_m=1000.0,
        estimated_time_min=None,
        coordinates=[(0.0, 0.0), (0.01, 0.01)],
    )
    text = result.to_tool_text()
    assert "min" not in text


def test_network_summary_to_tool_text():
    summary = NetworkSummary(
        place_or_point="Testville",
        network_type="drive",
        n_nodes=10,
        n_edges=15,
        bbox=(1.0, 0.0, 1.0, 0.0),
    )
    text = summary.to_tool_text()
    assert "Testville" in text
    assert "10 nodes" in text
    assert "15 edges" in text


def test_isochrone_result_to_tool_text():
    result = IsochroneResult(
        center_label="Home",
        minutes=15,
        network_type="walk",
        n_reachable_nodes=42,
        area_km2=1.23,
        approx_radius_m=600.0,
    )
    text = result.to_tool_text()
    assert "Home" in text
    assert "15" in text
    assert "42" in text


def test_compute_shortest_route_rejects_points_too_far_apart():
    # "lat,lon" strings skip geocoding entirely, so this raises before any
    # network call — regression test for a real bug: two bare street names with
    # no city context geocoded to opposite sides of the planet, and the missing
    # span cap meant the tool tried to fetch a ~10,000km-radius street network
    # instead of failing fast.
    with pytest.raises(RouteTooFarError):
        compute_shortest_route("39.6383482,-119.8542626", "-23.3648736,119.7306373")


def test_isochrone_tool_text_flags_truncated_result():
    kwargs = dict(
        center_label="Leonora",
        minutes=60,
        network_type="drive",
        n_reachable_nodes=10,
        area_km2=5.0,
        approx_radius_m=1000.0,
    )
    assert "underestimate" not in IsochroneResult(**kwargs).to_tool_text()
    assert "underestimate" in IsochroneResult(**kwargs, truncated=True).to_tool_text()


def _fragmented_graph():
    import networkx as nx

    g = nx.MultiDiGraph(crs="EPSG:4326")
    # Main network: nodes 1-2 (~110 m apart). Stranded fragment: node 3, ~55 m
    # from node 2 but not connected to it (e.g. a jetty way not joined to the path).
    g.add_node(1, x=115.8500, y=-32.0000)
    g.add_node(2, x=115.8500, y=-32.0010)
    g.add_node(3, x=115.8500, y=-32.0015)
    g.add_edge(1, 2, length=111.0)
    g.add_edge(2, 1, length=111.0)
    return g


def test_resnap_moves_stranded_endpoint_into_connected_component():
    from geoagent.geospatial.routing import _resnap_to_connected

    result = _resnap_to_connected(
        _fragmented_graph(), 1, 3, (-32.0000, 115.8500), (-32.0015, 115.8500)
    )

    assert result is not None
    o_node, d_node, notes = result
    assert (o_node, d_node) == (1, 2)
    assert notes[0] == "" and "nearest connected path" in notes[1]


def test_resnap_gives_up_when_nothing_connected_is_nearby():
    from geoagent.geospatial.routing import _resnap_to_connected

    # Destination point is ~1.1 km from the nearest connected node.
    assert (
        _resnap_to_connected(_fragmented_graph(), 1, 3, (-32.0, 115.85), (-32.012, 115.85))
        is None
    )
