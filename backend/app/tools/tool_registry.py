"""Tool registry — defines available tools and their schemas.

Each tool has:
  name:        unique identifier
  description: human-readable purpose
  parameters:  JSON Schema for the input parameters
  run:         async callable (params: dict) -> str
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger("app.tools.tool_registry")

_TOOL_DEFS: dict[str, dict[str, Any]] = {}


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable:
    """Decorator to register a tool's run function."""
    def decorator(func: Callable[..., Coroutine[Any, Any, str]]) -> Callable:
        if name in _TOOL_DEFS:
            raise ValueError(f"Tool '{name}' is already registered")
        _TOOL_DEFS[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "run": func,
        }
        logger.info("[TOOL] registered tool=%s", name)
        return func
    return decorator


def get_tool(name: str) -> dict[str, Any] | None:
    """Get a tool definition by name, or None if not found."""
    return _TOOL_DEFS.get(name)


def list_tools() -> list[dict[str, Any]]:
    """Return all registered tool definitions (without 'run' function)."""
    return [
        {k: v for k, v in t.items() if k != "run"}
        for t in _TOOL_DEFS.values()
    ]


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return tool schemas in OpenAI function-calling format."""
    result = []
    for t in _TOOL_DEFS.values():
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        })
    return result
