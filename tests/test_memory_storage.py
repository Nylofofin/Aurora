# SPDX-License-Identifier: GPL-3.0-only
import json
import stat

import pytest

import aurora_core.memory as memory


def test_loading_existing_memory_restricts_permissions(tmp_path, monkeypatch):
    path = tmp_path / "aurora-memory.json"
    path.write_text('{"preferences": ["Responda em português"]}', encoding="utf-8")
    path.chmod(0o644)
    monkeypatch.setattr(memory, "MEMORY_FILE", path)

    assert memory.user_memory_load() == ["Responda em português"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_memory_update_writes_private_file_atomically(tmp_path, monkeypatch):
    path = tmp_path / "state" / "aurora-memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", path)

    assert memory.user_memory_update("Prefiro respostas curtas") == (
        "Salvei essa preferência localmente para as próximas conversas."
    )
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "preferences": ["Prefiro respostas curtas"]
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert not path.with_suffix(".tmp").exists()


def test_memory_update_secures_an_existing_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "aurora-memory.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text("old temporary data", encoding="utf-8")
    temporary.chmod(0o644)
    monkeypatch.setattr(memory, "MEMORY_FILE", path)

    memory.user_memory_update("Não exponha preferências")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not temporary.exists()


def test_memory_update_preserves_corrupted_json(tmp_path, monkeypatch):
    path = tmp_path / "aurora-memory.json"
    original = b'{"preferences": ['
    path.write_bytes(original)
    monkeypatch.setattr(memory, "MEMORY_FILE", path)

    with pytest.raises(ValueError, match="arquivo foi preservado"):
        memory.user_memory_update("Nova preferência")

    assert path.read_bytes() == original
    assert not path.with_suffix(".tmp").exists()
