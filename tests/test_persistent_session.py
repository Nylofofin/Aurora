import json
import stat

import pytest

from aurora_core.session import ConversationSession


def test_session_persists_bounded_history_summary_facts_and_topics(tmp_path):
    path = tmp_path / "private" / "conversation-session.json"
    session = ConversationSession(path)

    assert session.load() == []
    for index in range(5):
        user = "Eu moro em Recife e gosto de música local" if index == 0 else (
            f"Quero conversar sobre música local, assunto {index}"
        )
        session.record_exchange(user, f"Resposta {index}")

    restored = ConversationSession(path)
    history = restored.load()

    assert len(history) == 6
    assert history[0]["content"].endswith("assunto 2")
    assert "Eu moro em Recife" in restored.data["summary"]
    assert "Eu moro em Recife" in restored.data["facts"][0]
    context = restored.prompt_context()
    assert "musica" in context
    assert "Recife" in context
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_closed_session_starts_new_without_losing_saved_user_context(tmp_path):
    path = tmp_path / "conversation-session.json"
    session = ConversationSession(path)
    session.load()
    session.record_exchange("Eu trabalho com música", "Entendi.")
    session.close()

    restored = ConversationSession(path)
    restored.load()
    assert restored.data["active"] is False
    restored.start_new()
    assert restored.data["active"] is True
    assert restored.data["history"] == []
    assert "Eu trabalho com música" in restored.data["facts"]
    assert json.loads(path.read_text(encoding="utf-8"))["session_id"] == restored.data["session_id"]


def test_invalid_session_file_is_preserved(tmp_path):
    path = tmp_path / "conversation-session.json"
    original = b'{"version":'
    path.write_bytes(original)

    with pytest.raises(ValueError, match="arquivo foi preservado"):
        ConversationSession(path).load()

    assert path.read_bytes() == original
