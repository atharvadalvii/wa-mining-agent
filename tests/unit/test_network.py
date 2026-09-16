import networkx as nx
import pytest

from geoagent.geospatial.network import NetworkFetchError, _fetch_with_retry


def _make_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    g.add_node(1, x=0.0, y=0.0)
    return g


def test_fetch_with_retry_fails_fast_when_overpass_unreachable(monkeypatch):
    # Regression test for a real bug: OSMnx's own /status rate-limit check
    # falls back to a hardcoded 60s sleep (then still attempts the query
    # anyway) whenever it can't connect, so a genuinely unreachable Overpass
    # mirror turned into minutes of "thinking" across our 3 retries before
    # ever reaching an error. The fast-fail check must raise before fetch_fn
    # is ever called, and without going through the retry/sleep loop at all.
    monkeypatch.setattr("geoagent.config.is_overpass_reachable", lambda: False)
    fetch_fn = lambda: pytest.fail("fetch_fn should not be called when unreachable")  # noqa: E731

    with pytest.raises(NetworkFetchError, match="unreachable"):
        _fetch_with_retry(fetch_fn, "Could not fetch")


def test_fetch_with_retry_proceeds_when_overpass_reachable(monkeypatch):
    monkeypatch.setattr("geoagent.config.is_overpass_reachable", lambda: True)
    graph = _make_graph()
    calls = []

    def fetch_fn():
        calls.append(1)
        return graph

    result = _fetch_with_retry(fetch_fn, "Could not fetch")

    assert result is graph
    assert len(calls) == 1


def test_fetch_with_retry_retries_transient_failures_then_succeeds(monkeypatch):
    monkeypatch.setattr("geoagent.config.is_overpass_reachable", lambda: True)
    monkeypatch.setattr("geoagent.geospatial.network.time.sleep", lambda seconds: None)
    graph = _make_graph()
    attempts = {"n": 0}

    def fetch_fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return graph

    result = _fetch_with_retry(fetch_fn, "Could not fetch")

    assert result is graph
    assert attempts["n"] == 3


def test_fetch_with_retry_raises_after_max_attempts(monkeypatch):
    monkeypatch.setattr("geoagent.config.is_overpass_reachable", lambda: True)
    monkeypatch.setattr("geoagent.geospatial.network.time.sleep", lambda seconds: None)
    attempts = {"n": 0}

    def fetch_fn():
        attempts["n"] += 1
        raise RuntimeError("still failing")

    with pytest.raises(NetworkFetchError, match="Could not fetch"):
        _fetch_with_retry(fetch_fn, "Could not fetch")

    assert attempts["n"] == 3
