# SPDX-License-Identifier: GPL-3.0-only
"""Small, safe evaluator for elementary spoken arithmetic."""
from __future__ import annotations

import ast
from decimal import Decimal, DecimalException, localcontext
import re
import operator

from .text import normalize_words


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _decimal_expression(node):
    if isinstance(node, ast.Expression):
        return _decimal_expression(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _decimal_expression(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left = _decimal_expression(node.left)
        right = _decimal_expression(node.right)
        return _OPERATORS[type(node.op)](left, right)
    raise ValueError("unsupported arithmetic expression")


def calculate_local_expression(prompt: str) -> str | None:
    """Return a deterministic result for a simple numeric calculation, or None."""
    text = normalize_words(prompt)
    if len(text) > 160:
        return None
    text = re.sub(r"^aurora\s*[, ]*", "", text)
    text = re.sub(
        r"^(?:quanto\s+(?:e|da|resulta)|qual\s+(?:e\s+)?(?:o\s+)?resultado\s+(?:de\s+)?|(?:qual\s+e|qual)|"
        r"calcule|calcular|faz(?:er)?\s+a\s+conta(?:\s+de)?|resolva)\s+",
        "",
        text,
    )
    text = text.strip(" ?.!;:")
    percent = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:de|do|da)\s*(\d+(?:[.,]\d+)?)", text)
    if percent:
        text = f"({percent.group(1)}/100)*({percent.group(2)})"
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    substitutions = (
        (r"\b(?:multiplicado|multiplicada|vezes|x)\s*(?:por)?\b", "*"),
        (r"\b(?:dividido|dividida)\s+por\b", "/"),
        (r"\bmais\b", "+"),
        (r"\bmenos\b", "-"),
    )
    for pattern, replacement in substitutions:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s+", "", text)
    if not re.fullmatch(r"[0-9.+*/()\-]+", text) or not re.search(r"[+*/\-]", text):
        return None
    try:
        tree = ast.parse(text, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 64:
            return None
        with localcontext() as context:
            context.prec = 28
            result = _decimal_expression(tree)
        if not result.is_finite() or abs(result) > Decimal("1e15"):
            return None
    except (SyntaxError, ValueError, DecimalException, ZeroDivisionError, OverflowError):
        return None
    formatted = format(result.normalize(), "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    if formatted in {"-0", ""}:
        formatted = "0"
    return f"O resultado é {formatted.replace('.', ',')}."
