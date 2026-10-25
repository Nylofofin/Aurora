# SPDX-License-Identifier: GPL-3.0-only
"""Deterministic helpers for bounded spoken conversations."""
from __future__ import annotations
import re
from .system.files import normalize_words

_CLOSING = re.compile(
    r"^(?:obrigad[oa]|valeu|muito obrigad[oa]|tchau|ate mais|ate logo|"
    r"falamos depois|pode descansar|pode dormir|encerra(?: a)? conversa|"
    r"termina(?: a)? conversa|fim da conversa|chega por hoje)$"
)

def is_conversation_closing(text: str) -> bool:
    """Recognize only an unambiguous, standalone closing cue."""
    normalized = re.sub(r"[^\w\s]", " ", normalize_words(text), flags=re.UNICODE)
    return bool(_CLOSING.fullmatch(" ".join(normalized.split())))
