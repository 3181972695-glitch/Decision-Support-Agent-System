"""Tool service — executes registered tools and returns results."""

from __future__ import annotations

import logging
import traceback
from typing import Any

# Import all tools so their @register_tool decorators run
import app.tools.calculator  # noqa: F401
import app.tools.code_analyzer  # noqa: F401
import app.tools.market_analyzer  # noqa: F401
import app.tools.web_search  # noqa: F401

from app.tools.tool_registry import get_tool, get_tool_schemas, list_tools

logger = logging.getLogger("app.services.tool_service")


class ToolService:
    """Executes registered tools with parameter validation."""

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with the given arguments.

        Args:
            tool_name: Name of the registered tool.
            arguments: Dict of parameter names to values.

        Returns:
            String result from the tool.
        """
        tool_def = get_tool(tool_name)
        if tool_def is None:
            raise ValueError(f"Unknown tool: {tool_name!r}")

        logger.info("[TOOL] executing tool=%s args=%s", tool_name, arguments)

        try:
            run_fn = tool_def["run"]
            # Inspect the function signature to match kwargs
            result = await run_fn(**arguments)
            logger.info("[TOOL] completed tool=%s result_len=%d", tool_name, len(result))
            return result
        except TypeError as exc:
            logger.warning("[TOOL] parameter error tool=%s: %s", tool_name, exc)
            raise ValueError(f"Invalid parameters for {tool_name}: {exc}") from exc
        except Exception as exc:
            logger.error("[TOOL] execution error tool=%s: %s", tool_name, exc)
            return f"Error executing {tool_name}: {exc}"

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-format tool schemas for LLM function calling."""
        return get_tool_schemas()

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tool definitions (without run functions)."""
        return list_tools()
