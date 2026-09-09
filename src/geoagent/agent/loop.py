"""Framework-free OpenAI tool-calling loop."""

from __future__ import annotations

import json
from typing import Callable

from geoagent.agent.conversation import Conversation
from geoagent.tools.registry import dispatch, openai_tool_schemas


def run_turn(
    client,
    model: str,
    conversation: Conversation,
    max_turns: int = 8,
    on_tool_call: Callable[[str, dict], None] | None = None,
    on_tool_result: Callable[[str, str], None] | None = None,
) -> str:
    """Runs the tool-calling loop for one user turn, mutating conversation.messages,
    and returns the final assistant text reply.

    `on_tool_call`/`on_tool_result` are optional UI hooks (e.g. for a CLI to render
    tool activity); this function has no rendering opinion of its own so it stays
    reusable from a future non-CLI caller (e.g. a FastAPI endpoint).
    """
    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=model,
            messages=conversation.messages,
            tools=openai_tool_schemas(),
        )
        message = response.choices[0].message
        conversation.messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            return message.content or ""

        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments or "{}")
            if on_tool_call:
                on_tool_call(tool_call.function.name, args)
            result_text = dispatch(tool_call.function.name, args)
            if on_tool_result:
                on_tool_result(tool_call.function.name, result_text)
            conversation.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_text,
                }
            )

    return (
        "I wasn't able to finish this within the allotted number of tool calls. "
        "Try rephrasing or breaking the request into smaller steps."
    )
