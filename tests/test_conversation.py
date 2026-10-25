# SPDX-License-Identifier: GPL-3.0-only
from aurora_core.conversation import is_conversation_closing
from aurora_core.config import DEFAULTS


def test_closing_cues_are_standalone_and_language_level():
    assert is_conversation_closing("obrigado")
    assert is_conversation_closing("Até mais!")
    assert is_conversation_closing("pode descansar")
    assert not is_conversation_closing("obrigado, abre o terminal")
    assert not is_conversation_closing("obrigado por explicar")
    assert not is_conversation_closing("tchau, pesquisa o clima")


def test_conversation_defaults_are_bounded_and_do_not_enable_boot_listening():
    assert DEFAULTS["conversation_mode_enabled"] is True
    assert 5 <= DEFAULTS["conversation_idle_seconds"] <= 60
    assert 1 <= DEFAULTS["conversation_max_turns"] <= 12
