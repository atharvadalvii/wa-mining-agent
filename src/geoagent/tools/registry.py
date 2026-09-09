"""Tool schema + dispatch registry — the extension point for new tool modules.

To add a new capability (e.g. POI search): create `geospatial/<feature>.py` with the
domain logic, `tools/<feature>.py` that builds ToolSpecs and calls `register()`, and
import that new tools module wherever `geoagent.tools.routing` is imported below.
Nothing in `agent/` needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from geoagent.tools.errors import format_tool_error


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    if spec.name in _REGISTRY:
        raise ValueError(f"tool '{spec.name}' already registered")
    _REGISTRY[spec.name] = spec


def get_tool(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def openai_tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }
        for spec in _REGISTRY.values()
    ]


def dispatch(name: str, arguments: dict) -> str:
    spec = get_tool(name)
    if spec is None:
        return format_tool_error(name, ValueError(f"unknown tool '{name}'"))
    try:
        return spec.handler(**arguments)
    except Exception as exc:
        return format_tool_error(name, exc)
