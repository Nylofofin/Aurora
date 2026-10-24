# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import time
from pathlib import Path
from aurora_core.system.agenda import (
    agenda_add,
    agenda_cancel,
    agenda_list,
    agenda_nearest,
    parse_datetime,
    _state_path,
)
from aurora_core.system.commands import parse_local_command


def test_parse_datetime_relative(monkeypatch, tmp_path):
    # Test natural date parsing
    now = time.time()
    ts_amanha = parse_datetime("amanhã às 15h30")
    assert ts_amanha is not None
    assert ts_amanha > now

    ts_date = parse_datetime("dia 15 de dezembro às 10h")
    assert ts_date is not None

    ts_iso = parse_datetime("25/12/2026 às 14:00")
    assert ts_iso is not None


def test_agenda_lifecycle(monkeypatch, tmp_path):
    state_file = tmp_path / "agenda.json"
    monkeypatch.setattr("aurora_core.system.agenda._state_path", lambda: state_file)

    # Empty agenda
    assert "Não há compromissos" in agenda_nearest()
    assert "Nenhum compromisso" in agenda_list(7)

    # Add event in future
    future_time = time.time() + 3600 * 24  # tomorrow
    msg = agenda_add("Reunião de Equipe", future_time, "Discutir sprint")
    assert 'Compromisso "Reunião de Equipe" adicionado' in msg
    assert state_file.exists()

    # Nearest
    nearest = agenda_nearest()
    assert "Reunião de Equipe" in nearest

    # List
    listing = agenda_list(7)
    assert "Reunião de Equipe" in listing
    assert "Discutir sprint" in listing

    # Cancel
    cancel_msg = agenda_cancel(1)
    assert "removido" in cancel_msg
    assert "Nenhum compromisso" in agenda_list(7)


def test_agenda_commands():
    # Direct command checks
    cmd = parse_local_command("Aurora, qual é o meu próximo compromisso?")
    assert cmd == ("agenda_nearest", {})

    cmd = parse_local_command("Aurora, liste meus compromissos")
    assert cmd == ("agenda_list", {"days": 7})

    cmd = parse_local_command("Aurora, cancele o compromisso 3")
    assert cmd == ("agenda_cancel", {"event_id": 3})
