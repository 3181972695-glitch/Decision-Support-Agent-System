"""Calculator tool — evaluates mathematical expressions safely."""

import ast
import logging
import operator

from app.tools.tool_registry import register_tool

logger = logging.getLogger("app.tools.calculator")

# Allowed operators for safe eval
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr: str) -> float:
    """Evaluate a mathematical expression safely using AST."""
    tree = ast.parse(expr.strip(), mode="eval")
    if not isinstance(tree, ast.Expression):
        raise ValueError("Not a valid expression")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Unsupported constant: {type(node.value).__name__}")
        if isinstance(node, ast.BinOp):
            op_func = _ALLOWED_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op_func(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op_func = _ALLOWED_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
            return op_func(_eval(node.operand))
        raise ValueError(f"Unsupported node: {type(node).__name__}")

    return _eval(tree.body)


@register_tool(
    name="calculator",
    description="Evaluate a mathematical expression. Supports +, -, *, /, **, floor division, and modulo.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The mathematical expression to evaluate, e.g. '50000 * 12' or '(150 + 200) / 3'",
            }
        },
        "required": ["expression"],
    },
)
async def run_calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the result."""
    try:
        result = _safe_eval(expression)
        # Format: int if whole number, float otherwise
        if result == int(result):
            formatted = str(int(result))
        else:
            formatted = f"{result:.4f}"
        logger.info("[TOOL] calculator(%r) = %s", expression, formatted)
        return formatted
    except Exception as exc:
        logger.warning("[TOOL] calculator error: %s", exc)
        return f"Error calculating '{expression}': {exc}"
