from geoagent.config import is_overpass_reachable


def test_is_overpass_reachable_true_when_probe_finds_an_ip(monkeypatch):
    monkeypatch.setattr("geoagent.config._pick_reachable_ip", lambda hostname: "1.2.3.4")
    assert is_overpass_reachable() is True


def test_is_overpass_reachable_false_when_probe_finds_nothing(monkeypatch):
    monkeypatch.setattr("geoagent.config._pick_reachable_ip", lambda hostname: None)
    assert is_overpass_reachable() is False


def test_is_overpass_reachable_probes_the_configured_overpass_host(monkeypatch):
    import osmnx as ox

    monkeypatch.setattr(ox.settings, "overpass_url", "https://my-mirror.example.org/api")
    seen_hostnames = []
    monkeypatch.setattr(
        "geoagent.config._pick_reachable_ip",
        lambda hostname: seen_hostnames.append(hostname) or "1.2.3.4",
    )

    is_overpass_reachable()

    assert seen_hostnames == ["my-mirror.example.org"]
