# SPDX-License-Identifier: GPL-3.0-only
import pytest

from aurora_core.system.calculator import calculate_local_expression


@pytest.mark.parametrize(
    ("prompt", "answer"),
    [
        ("Quanto é 15 vezes 12?", "O resultado é 180."),
        ("Quanto dá 10,5 dividido por 2?", "O resultado é 5,25."),
        ("Calcule 7 + 8", "O resultado é 15."),
        ("Qual é 15% de 200?", "O resultado é 30."),
        ("Quanto é 2 vezes 3 mais 4?", "O resultado é 10."),
    ],
)
def test_spoken_arithmetic_is_calculated_locally(prompt, answer):
    assert calculate_local_expression(prompt) == answer


@pytest.mark.parametrize(
    "prompt",
    ["Quanto é 1 dividido por 0?", "Quanto é 2 ** 100?", "Quanto custa um café?"],
)
def test_unsupported_or_non_arithmetic_text_is_not_evaluated(prompt):
    assert calculate_local_expression(prompt) is None
