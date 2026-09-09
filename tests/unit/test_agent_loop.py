import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from geoagent.agent.conversation import Conversation
from geoagent.agent.loop import run_turn
from geoagent.tools.registry import ToolSpec, register


@pytest.fixture(autouse=True)
def clean_registry():
    from geoagent.tools import registry as reg

    saved = dict(reg._REGISTRY)
    reg._REGISTRY.clear()
    yield
    reg._REGISTRY.clear()
    reg._REGISTRY.update(saved)


def _tool_call_message(name: str, arguments: dict, call_id: str = "call_1"):
    tool_call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )
    message = MagicMock()
    message.tool_calls = [tool_call]
    message.content = None
    message.model_dump.return_value = {"role": "assistant", "tool_calls": [{"id": call_id}]}
    return message


def _final_message(content: str):
    message = MagicMock()
    message.tool_calls = None
    message.content = content
    message.model_dump.return_value = {"role": "assistant", "content": content}
    return message


def _response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_run_turn_dispatches_tool_call_then_returns_final_text():
    register(
        ToolSpec(
            name="get_thing",
            description="gets a thing",
            parameters={"type": "object", "properties": {}},
            handler=lambda: "the thing",
        )
    )

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response(_tool_call_message("get_thing", {})),
        _response(_final_message("Here is the thing.")),
    ]

    conversation = Conversation.start("system prompt")
    conversation.add_user("what's the thing?")

    reply = run_turn(client, "gpt-4o", conversation, max_turns=8)

    assert reply == "Here is the thing."
    assert client.chat.completions.create.call_count == 2
    tool_messages = [m for m in conversation.messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"] == "the thing"
    assert tool_messages[0]["tool_call_id"] == "call_1"


def test_run_turn_returns_immediately_without_tool_calls():
    client = MagicMock()
    client.chat.completions.create.side_effect = [_response(_final_message("Direct answer."))]

    conversation = Conversation.start("system prompt")
    conversation.add_user("hello")

    reply = run_turn(client, "gpt-4o", conversation, max_turns=8)

    assert reply == "Direct answer."
    assert client.chat.completions.create.call_count == 1


def test_run_turn_respects_max_turns():
    register(
        ToolSpec(
            name="loop_tool",
            description="always calls itself",
            parameters={"type": "object", "properties": {}},
            handler=lambda: "still going",
        )
    )

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _response(_tool_call_message("loop_tool", {})) for _ in range(5)
    ]

    conversation = Conversation.start("system prompt")
    conversation.add_user("loop forever")

    reply = run_turn(client, "gpt-4o", conversation, max_turns=3)

    assert "wasn't able to finish" in reply
    assert client.chat.completions.create.call_count == 3
