import networkx as nx
import pytest

from geoagent.geospatial.network import NetworkFetchError, _add_speeds_and_times, _fetch_with_retry


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
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        return graph

    result = _fetch_with_retry(fetch_fn, "Could not fetch")

    assert result is graph
    assert attempts["n"] == 2


def test_fetch_with_retry_raises_after_max_attempts(monkeypatch):
    monkeypatch.setattr("geoagent.config.is_overpass_reachable", lambda: True)
    monkeypatch.setattr("geoagent.geospatial.network.time.sleep", lambda seconds: None)
    attempts = {"n": 0}

    def fetch_fn():
        attempts["n"] += 1
        raise RuntimeError("still failing")

    with pytest.raises(NetworkFetchError, match="Could not fetch"):
        _fetch_with_retry(fetch_fn, "Could not fetch")

    assert attempts["n"] == 2


def test_fetch_with_retry_bounds_a_hanging_fetch(monkeypatch):
    # Regression test for a real, more severe bug than plain unreachability:
    # osmnx._overpass._overpass_request recursively retries FOREVER (sleeping
    # 55s each time, no cap) whenever Overpass responds 429/504 — observed in
    # practice to turn a single fetch into 851s once our own testing tripped
    # the public server's rate limit. Since that retry-forever loop lives
    # inside OSMnx and isn't bounded by requests_timeout, fetch_fn must be run
    # under an independent hard wall-clock cap that gives up on it rather than
    # ever actually waiting that long.
    monkeypatch.setattr("geoagent.config.is_overpass_reachable", lambda: True)
    monkeypatch.setattr("geoagent.geospatial.network.time.sleep", lambda seconds: None)
    monkeypatch.setattr("geoagent.geospatial.network._HARD_FETCH_TIMEOUT_S", 0.05)

    def fetch_fn():
        import threading

        # Simulates OSMnx's own unbounded internal retry loop. threading.Event
        # rather than time.sleep(): this test mocks
        # geoagent.geospatial.network.time.sleep to skip the real retry-delay
        # wait between attempts — but `network.time` IS the process-wide time
        # module (not a copy), so that mock would silently make a time.sleep
        # call here a no-op too, defeating the point of simulating a hang.
        # Kept short (not e.g. 10s) just to keep this test itself fast — the
        # orphaned daemon thread this leaves running doesn't block
        # process/test-suite exit either way (see _run_with_hard_timeout's
        # docstring).
        threading.Event().wait(0.3)
        return _make_graph()

    with pytest.raises(NetworkFetchError, match="Could not fetch"):
        _fetch_with_retry(fetch_fn, "Could not fetch")


def test_add_speeds_and_times_handles_graph_with_no_maxspeed_tags():
    # Regression test for a real bug: in remote areas (e.g. Leonora, WA) no edge
    # has a maxspeed tag, and OSMnx's add_edge_speeds raised ValueError unless
    # hwy_speeds/fallback were passed, breaking every drive isochrone there.
    g = nx.MultiDiGraph(crs="EPSG:4326")
    g.add_node(1, x=0.0, y=0.0)
    g.add_node(2, x=0.01, y=0.0)
    g.add_edge(1, 2, length=1000.0, highway="trunk")
    g.add_edge(2, 1, length=1000.0, highway="some_unknown_type")

    result = _add_speeds_and_times(g, "drive")

    assert result[1][2][0]["speed_kph"] == 100
    assert result[2][1][0]["speed_kph"] == 50
    assert result[1][2][0]["travel_time"] == pytest.approx(36.0)
