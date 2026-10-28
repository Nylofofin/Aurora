# SPDX-License-Identifier: GPL-3.0-only
"""Deterministic helpers for bounded spoken conversations."""
from __future__ import annotations
import re
from .system.files import normalize_words

_CLOSING = re.compile(
    r"^(?:obrigad[oa]|valeu|muito obrigad[oa]|tchau|ate mais|ate logo|"
    r"falamos depois|pode descansar|pode dormir|sair|encerra|encerre|"
    r"encerra a sessao|encerre a sessao|fecha a sessao|feche a sessao|"
    r"pode encerrar|pode encerrar a sessao|encerra a conversa|"
    r"encerre a conversa|termina a conversa|fim da conversa|chega por hoje)$"
)
_AMBIGUOUS_CLOSE = {"fecha", "feche", "pode fechar"}


def session_closing_intent(text: str) -> str:
    """Return close, ambiguous, or none for standalone session-ending phrases."""
    normalized = re.sub(r"[^\w\s]", " ", normalize_words(text), flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    if _CLOSING.fullmatch(normalized):
        return "close"
    if normalized in _AMBIGUOUS_CLOSE:
        return "ambiguous"
    return "none"


def is_conversation_closing(text: str) -> bool:
    """Recognize only an unambiguous, standalone closing cue."""
    return session_closing_intent(text) == "close"
