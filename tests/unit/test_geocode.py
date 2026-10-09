import pytest

from geoagent.geospatial import geocode
from geoagent.geospatial.geocode import GeocodeError, _pick_result, resolve_point


@pytest.fixture(autouse=True)
def _clear_cache():
    geocode._geocode_place.cache_clear()
    yield
    geocode._geocode_place.cache_clear()


def _hit(name, cls, typ, lat, lon):
    return {"name": name, "class": cls, "type": typ, "lat": str(lat), "lon": str(lon)}


def test_resolve_point_caches_successful_lookups(monkeypatch):
    calls = []

    def fake_search(text):
        calls.append(text)
        return [_hit("Perth Airport", "aeroway", "aerodrome", -31.94, 115.97)]

    monkeypatch.setattr(geocode, "_nominatim_search", fake_search)

    assert resolve_point("Perth Airport") == (-31.94, 115.97, "Perth Airport")
    assert resolve_point("  Perth Airport ") == (-31.94, 115.97, "  Perth Airport ")
    assert calls == ["Perth Airport"]


def test_resolve_point_does_not_cache_failures(monkeypatch):
    calls = []

    def empty_search(text):
        calls.append(text)
        return []

    monkeypatch.setattr(geocode, "_nominatim_search", empty_search)

    for _ in range(2):
        with pytest.raises(GeocodeError):
            resolve_point("Nowhereville")
    assert len(calls) == 2


def test_resolve_point_latlon_skips_geocoder(monkeypatch):
    monkeypatch.setattr(geocode, "_nominatim_search", lambda text: pytest.fail("should not geocode"))
    assert resolve_point("-31.9, 115.9") == (-31.9, 115.9, "-31.9, 115.9")


def test_pick_result_prefers_the_town_over_the_shire_boundary():
    # Regression test for a real bug: Nominatim's first hit for "Leonora, WA" is the
    # Shire of Leonora boundary, whose centre is ~55 km from the town.
    results = [
        _hit("Shire of Leonora", "boundary", "administrative", -28.42, 121.00),
        _hit("Leonora", "place", "town", -28.88, 121.33),
    ]
    assert _pick_result("Leonora, WA", results)["lat"] == "-28.88"


def test_pick_result_skips_council_areas_even_without_a_town_result():
    results = [
        _hit("Shire of Leonora", "boundary", "administrative", -28.42, 121.00),
        _hit("Leonora", "boundary", "administrative", -28.88, 121.33),
    ]
    assert _pick_result("Leonora, WA", results)["lat"] == "-28.88"


def test_pick_result_falls_back_to_the_top_hit():
    results = [_hit("Boulder Pit", "landuse", "quarry", -30.78, 121.50)]
    assert _pick_result("the super pit", results) is results[0]
