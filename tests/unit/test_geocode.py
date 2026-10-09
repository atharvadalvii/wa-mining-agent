import pytest

from geoagent.geospatial import geocode
from geoagent.geospatial.geocode import GeocodeError, resolve_point


@pytest.fixture(autouse=True)
def _clear_cache():
    geocode._geocode_place.cache_clear()
    yield
    geocode._geocode_place.cache_clear()


def test_resolve_point_caches_successful_lookups(monkeypatch):
    calls = []

    def fake_geocode(text):
        calls.append(text)
        return -31.94, 115.97

    monkeypatch.setattr("osmnx.geocode", fake_geocode)

    assert resolve_point("Perth Airport") == (-31.94, 115.97, "Perth Airport")
    assert resolve_point("  Perth Airport ") == (-31.94, 115.97, "  Perth Airport ")
    assert calls == ["Perth Airport"]


def test_resolve_point_does_not_cache_failures(monkeypatch):
    calls = []

    def failing_geocode(text):
        calls.append(text)
        raise ValueError("no result")

    monkeypatch.setattr("osmnx.geocode", failing_geocode)

    for _ in range(2):
        with pytest.raises(GeocodeError):
            resolve_point("Nowhereville")
    assert len(calls) == 2


def test_resolve_point_latlon_skips_geocoder(monkeypatch):
    monkeypatch.setattr("osmnx.geocode", lambda text: pytest.fail("should not geocode"))
    assert resolve_point("-31.9, 115.9") == (-31.9, 115.9, "-31.9, 115.9")
