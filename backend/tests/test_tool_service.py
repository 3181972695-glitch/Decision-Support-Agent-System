"""Tests for tool registry and tool service."""

import pytest

from app.services.tool_service import ToolService
from app.tools.tool_registry import list_tools, get_tool, get_tool_schemas


@pytest.fixture
def tool_service() -> ToolService:
    return ToolService()


@pytest.mark.asyncio
async def test_list_tools_contains_expected(tool_service: ToolService) -> None:
    """List tools should contain the 4 built-in tools."""
    tools = tool_service.list_tools()
    names = [t["name"] for t in tools]
    assert "calculator" in names
    assert "web_search" in names
    assert "code_analyzer" in names
    assert "market_analyzer" in names


@pytest.mark.asyncio
async def test_tool_schemas_have_function_format(tool_service: ToolService) -> None:
    """Tool schemas should be in OpenAI function-calling format."""
    schemas = tool_service.get_tool_schemas()
    for s in schemas:
        assert s["type"] == "function"
        assert "function" in s
        fn = s["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


@pytest.mark.asyncio
async def test_calculator_basic_arithmetic(tool_service: ToolService) -> None:
    """Calculator should evaluate basic expressions."""
    result = await tool_service.execute("calculator", {"expression": "2 + 3"})
    assert result == "5"


@pytest.mark.asyncio
async def test_calculator_complex(tool_service: ToolService) -> None:
    """Calculator should handle complex expressions."""
    result = await tool_service.execute("calculator", {"expression": "(150 + 50) * 2"})
    assert result == "400"


@pytest.mark.asyncio
async def test_calculator_division(tool_service: ToolService) -> None:
    """Calculator should handle division."""
    result = await tool_service.execute("calculator", {"expression": "10 / 3"})
    assert "3.333" in result


@pytest.mark.asyncio
async def test_calculator_invalid_expression(tool_service: ToolService) -> None:
    """Calculator should handle errors gracefully."""
    result = await tool_service.execute("calculator", {"expression": "hello + world"})
    assert "Error" in result


@pytest.mark.asyncio
async def test_web_search_returns_results(tool_service: ToolService) -> None:
    """Web search should return results for known topics."""
    result = await tool_service.execute("web_search", {"query": "microservices migration"})
    assert len(result) > 0
    assert "microservices" in result.lower() or "Microservices" in result


@pytest.mark.asyncio
async def test_web_search_unknown_topic(tool_service: ToolService) -> None:
    """Web search should return no-results message for unknown topics."""
    result = await tool_service.execute("web_search", {"query": "xyzzy_nonexistent_42"})
    assert "No results" in result


@pytest.mark.asyncio
async def test_code_analyzer_returns_stats(tool_service: ToolService) -> None:
    """Code analyzer should return estimated statistics."""
    result = await tool_service.execute("code_analyzer", {"repository": "monolithic Rails e-commerce app"})
    assert "Estimated" in result
    assert "Ruby" in result


@pytest.mark.asyncio
async def test_market_analyzer_known_topic(tool_service: ToolService) -> None:
    """Market analyzer should return data for known topics."""
    result = await tool_service.execute("market_analyzer", {"topic": "AWS"})
    assert "Market Analysis" in result
    assert "Amazon" in result or "AWS" in result


@pytest.mark.asyncio
async def test_market_analyzer_unknown_topic(tool_service: ToolService) -> None:
    """Market analyzer should return generic response for unknown topics."""
    result = await tool_service.execute("market_analyzer", {"topic": "Quantum AI startups"})
    assert len(result) > 0


@pytest.mark.asyncio
async def test_unknown_tool_raises_error(tool_service: ToolService) -> None:
    """Unknown tool should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown tool"):
        await tool_service.execute("nonexistent_tool", {})


@pytest.mark.asyncio
async def test_tool_registry_list_and_get() -> None:
    """Tool registry list/get should work correctly."""
    tools = list_tools()
    assert len(tools) >= 4
    calc = get_tool("calculator")
    assert calc is not None
    assert calc["name"] == "calculator"
    assert "run" in calc  # run function should be present


@pytest.mark.asyncio
async def test_tool_schemas() -> None:
    """get_tool_schemas should return OpenAI-compatible schemas."""
    schemas = get_tool_schemas()
    assert len(schemas) >= 4
    names = [s["function"]["name"] for s in schemas]
    assert "calculator" in names
