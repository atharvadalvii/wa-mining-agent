"""Convert exceptions into structured, model-readable error strings."""

from __future__ import annotations

import json


def format_tool_error(tool_name: str, exc: Exception) -> str:
    return json.dumps(
        {
            "error": type(exc).__name__,
            "tool": tool_name,
            "message": str(exc),
        }
    )
