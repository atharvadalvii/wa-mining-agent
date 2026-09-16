from geoagent.geospatial import local_extract


def test_is_within_wa_perth():
    assert local_extract.is_within_wa(-31.95, 115.86)


def test_is_within_wa_newman():
    assert local_extract.is_within_wa(-23.36, 119.73)


def test_is_within_wa_rejects_nyc():
    assert not local_extract.is_within_wa(40.7573, -73.9860)


def test_is_within_wa_rejects_sydney():
    assert not local_extract.is_within_wa(-33.87, 151.21)


def test_bbox_within_wa_true_for_wa_bbox():
    assert local_extract.bbox_within_wa(-23.35, -23.38, 119.74, 119.71)


def test_bbox_within_wa_false_if_any_corner_outside():
    # north edge outside WA_NORTH
    assert not local_extract.bbox_within_wa(-10.0, -23.38, 119.74, 119.71)


def test_is_extracted_false_when_not_present(tmp_path, monkeypatch):
    monkeypatch.setattr(local_extract, "CACHE_DIR", tmp_path / "nowhere")
    assert not local_extract.is_extracted("drive")
