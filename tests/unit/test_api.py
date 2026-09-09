import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from geoagent.api import Settings, app, get_openai_client, get_settings
from geoagent.tools.registry import ToolSpec, register


@pytest.fixture(autouse=True)
def clean_registry():
    from geoagent.tools import registry as reg

    saved = dict(reg._REGISTRY)
    reg._REGISTRY.clear()
    yield
    reg._REGISTRY.clear()
    reg._REGISTRY.update(saved)


@pytest.fixture
def fake_settings(tmp_path):
    return Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        cache_dir=tmp_path / "cache",
        maps_dir=tmp_path / "maps",
        max_agent_turns=8,
        overpass_url=None,
        overpass_rate_limit=True,
    )


def _tool_call_message(name, arguments, call_id="call_1"):
    tool_call = SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments))
    )
    message = MagicMock()
    message.tool_calls = [tool_call]
    message.content = None
    message.model_dump.return_value = {"role": "assistant", "tool_calls": [{"id": call_id}]}
    return message


def _final_message(content):
    message = MagicMock()
    message.tool_calls = None
    message.content = content
    message.model_dump.return_value = {"role": "assistant", "content": content}
    return message


def _response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def client(fake_settings):
    app.dependency_overrides[get_settings] = lambda: fake_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_query_returns_reply_and_empty_geojson_when_no_tool_called(client, fake_settings):
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [_response(_final_message("Hello!"))]
    app.dependency_overrides[get_openai_client] = lambda: fake_client

    resp = client.post("/query", json={"message": "hi"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Hello!"
    assert body["geojson"] == {"type": "FeatureCollection", "features": []}
    assert isinstance(body["history"], list)


def test_query_collects_geojson_feature_from_tool_call(client, fake_settings):
    register(
        ToolSpec(
            name="fake_route_tool",
            description="returns a fake feature",
            parameters={"type": "object", "properties": {}},
            handler=lambda: _fake_route_handler(),
        )
    )

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _response(_tool_call_message("fake_route_tool", {})),
        _response(_final_message("Here's your route.")),
    ]
    app.dependency_overrides[get_openai_client] = lambda: fake_client

    resp = client.post("/query", json={"message": "route please"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Here's your route."
    features = body["geojson"]["features"]
    assert len(features) == 1
    assert features[0]["geometry"]["type"] == "LineString"


def _fake_route_handler() -> str:
    from geoagent.tools.geo_context import record_geo_feature

    record_geo_feature(
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            "properties": {"kind": "route"},
        }
    )
    return "a fake route summary"


def test_query_history_round_trip(client, fake_settings):
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [_response(_final_message("second reply"))]
    app.dependency_overrides[get_openai_client] = lambda: fake_client

    prior_history = [
        {"role": "user", "content": "first message"},
        {"role": "assistant", "content": "first reply"},
    ]
    resp = client.post("/query", json={"message": "follow up", "history": prior_history})

    assert resp.status_code == 200
    sent_messages = fake_client.chat.completions.create.call_args.kwargs["messages"]
    # system prompt + 2 prior history messages + new user message
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1] == prior_history[0]
    assert sent_messages[2] == prior_history[1]
    assert sent_messages[3] == {"role": "user", "content": "follow up"}
