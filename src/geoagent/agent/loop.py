"""Framework-free OpenAI tool-calling loop."""

from __future__ import annotations

import json
import sys

from geoagent.agent.conversation import Conversation
from geoagent.tools.registry import dispatch, openai_tool_schemas


def run_turn(
    client, model: str, conversation: Conversation, max_turns: int = 8, debug: bool = False
) -> str:
    """Runs the tool-calling loop for one user turn, mutating conversation.messages,
    and returns the final assistant text reply."""
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
            if debug:
                print(f"[tool call] {tool_call.function.name}({args})", file=sys.stderr)
            result_text = dispatch(tool_call.function.name, args)
            if debug:
                print(f"[tool result] {result_text}", file=sys.stderr)
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
