import pytest

from geoagent.geospatial.mapping import configure_maps_dir, save_isochrone_map, save_route_map
from geoagent.geospatial.models import IsochroneResult, RouteResult


@pytest.fixture(autouse=True)
def maps_dir(tmp_path):
    configure_maps_dir(tmp_path / "maps")
    yield tmp_path / "maps"


def test_save_route_map_writes_html_with_leaflet(maps_dir):
    result = RouteResult(
        origin_label="A",
        destination_label="B",
        network_type="walk",
        optimized_for="length",
        length_m=500.0,
        estimated_time_min=6.0,
        coordinates=[(0.0, 0.0), (0.001, 0.001), (0.002, 0.002)],
    )
    out_path = save_route_map(result)
    assert out_path.exists()
    assert out_path.parent == maps_dir
    html = out_path.read_text()
    assert "leaflet" in html.lower()


def test_save_route_map_raises_without_coordinates(maps_dir):
    result = RouteResult(
        origin_label="A",
        destination_label="B",
        network_type="walk",
        optimized_for="length",
        length_m=0.0,
        estimated_time_min=None,
        coordinates=[],
    )
    with pytest.raises(ValueError):
        save_route_map(result)


def test_save_isochrone_map_writes_html_with_leaflet(maps_dir):
    result = IsochroneResult(
        center_label="Home",
        minutes=15,
        network_type="walk",
        n_reachable_nodes=10,
        area_km2=1.0,
        approx_radius_m=500.0,
        center_point=(0.0, 0.0),
        hull_coords=[(0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.01), (0.0, 0.0)],
    )
    out_path = save_isochrone_map(result)
    assert out_path.exists()
    html = out_path.read_text()
    assert "leaflet" in html.lower()


def test_save_isochrone_map_raises_without_hull(maps_dir):
    result = IsochroneResult(
        center_label="Home",
        minutes=15,
        network_type="walk",
        n_reachable_nodes=0,
        area_km2=0.0,
        approx_radius_m=0.0,
    )
    with pytest.raises(ValueError):
        save_isochrone_map(result)
