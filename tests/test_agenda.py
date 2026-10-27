# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import queue
import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from aurora_core.system.agenda import (
    agenda_add,
    agenda_cancel,
    agenda_clear,
    agenda_list,
    agenda_nearest,
    parse_datetime,
    agenda_take_due,
    _load,
    _state_path,
)
from aurora_core.system.commands import parse_local_command
from aurora_core.system.approval import requires_user_approval
from aurora_core.llm.inference import _agenda_add_needs_followup
from aurora_core.llm.warmup import ModelWarmup
from aurora_core import service as service_module


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

    assert parse_local_command("Aurora, cancele o compromisso de sexta às 9h") is None
    cmd = parse_local_command("Aurora, remova o item número 12 da agenda")
    assert cmd == ("agenda_cancel", {"event_id": 12})

    cmd = parse_local_command("Aurora, apague todos os meus compromissos")
    assert cmd == ("agenda_clear", {})


def test_agenda_parser_rejects_invalid_times_without_raising():
    assert parse_datetime("amanhã às 99h99") is None
    assert parse_datetime("hoje às 25h") is None
    assert parse_datetime("sexta dia 25 às 9h") is not None


def test_agenda_parser_uses_time_after_day_number():
    from datetime import datetime
    ts = parse_datetime("amanhã dia 25 às 9h")
    assert ts is not None
    assert datetime.fromtimestamp(ts).hour == 9


def test_explicit_past_year_is_not_silently_rolled_forward():
    from datetime import datetime
    ts = parse_datetime("25/12/2020 às 10:00")
    assert ts is not None
    assert datetime.fromtimestamp(ts).year == 2020


def test_corrupt_agenda_entries_are_ignored(monkeypatch, tmp_path):
    state_file = tmp_path / "agenda.json"
    state_file.write_text(json.dumps([
        {"id": 1, "when": time.time() + 600, "title": "válido", "created": time.time()},
        {"id": 2, "when": "NaN", "title": "data inválida", "created": time.time()},
        "registro inválido",
    ]), encoding="utf-8")
    monkeypatch.setattr("aurora_core.system.agenda._state_path", lambda: state_file)
    assert [event["title"] for event in _load()] == ["válido"]


def test_cancel_without_id_does_not_delete_and_clear_is_approval_gated(monkeypatch, tmp_path):
    state_file = tmp_path / "agenda.json"
    monkeypatch.setattr("aurora_core.system.agenda._state_path", lambda: state_file)
    agenda_add("Consulta", time.time() + 3600)
    assert "Informe o número" in agenda_cancel()
    assert "Consulta" in agenda_list()
    assert requires_user_approval("agenda_clear")
    assert "Limpei todos" in agenda_clear()


def test_failed_agenda_add_is_routed_back_to_model_for_clarification():
    assert _agenda_add_needs_followup("A data ou hora do compromisso não foi reconhecida ou já passou.")
    assert _agenda_add_needs_followup("Precisa de um título para o compromisso.")
    assert not _agenda_add_needs_followup('Compromisso "Data ou hora do compromisso" adicionado.')


def test_warmup_loads_conversation_model_before_agent_model(monkeypatch):
    warmup = ModelWarmup({
        "model": "gemma3:1b-it-qat", "agent_model": "gemma4:e2b-it-q4_K_M",
        "num_ctx": 4096, "agent_num_ctx": 2048,
    })
    calls = []
    monkeypatch.setattr(warmup, "_warmup_one", lambda model, ctx: calls.append((model, ctx)))
    warmup.run()
    assert calls == [("gemma3:1b-it-qat", 4096), ("gemma4:e2b-it-q4_K_M", 4096)]


def test_due_agenda_event_is_claimed_once_with_small_lateness_window(monkeypatch, tmp_path):
    state_file = tmp_path / "agenda.json"
    monkeypatch.setattr("aurora_core.system.agenda._state_path", lambda: state_file)
    due_at = time.time() + 3600
    assert "adicionado" in agenda_add("Consulta", due_at)
    claimed = agenda_take_due(now=due_at + 30)
    assert len(claimed) == 1
    assert claimed[0]["title"] == "Consulta"
    assert claimed[0]["notified_at"] == due_at + 30
    assert agenda_take_due(now=due_at + 30) == []
    assert agenda_take_due(now=due_at + 3600) == []


def test_service_announces_due_agenda_event_when_idle(monkeypatch):
    spoken = []
    modes = []
    stub = SimpleNamespace(
        session_unlock_monitor=SimpleNamespace(active=False),
        voice=SimpleNamespace(request_active=Event()),
        speaker=SimpleNamespace(active=False, q=queue.Queue(), say=spoken.append),
        inf=None, pending=None, background_requests=[], activity_generation=0,
        response_finished=False, response_summary="",
        orb=SimpleNamespace(reveal=modes.append),
    )
    monkeypatch.setattr(service_module, "agenda_take_due", lambda: [{
        "id": 1, "title": "Dentista", "when": time.time(),
    }])
    service_module.AuroraService._check_due_agenda(stub)
    assert spoken and "Dentista" in spoken[0] and "Passando para lembrar" in spoken[0]
    assert modes == ["speaking"]
    assert stub.response_finished and stub.activity_generation == 1
