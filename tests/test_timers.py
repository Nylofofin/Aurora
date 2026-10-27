# SPDX-License-Identifier: GPL-3.0-only
import threading

from aurora_core.system.commands import parse_local_command
from aurora_core.system import actions
from aurora_core.service import AuroraService
from aurora_core.system.timers import TimerManager, format_duration, parse_timer_command, parse_timer_duration


def test_timer_duration_parses_digits_words_and_combined_units():
    assert parse_timer_duration("10 minutos") == 600
    assert parse_timer_duration("uma hora e vinte e cinco minutos") == 5100
    assert parse_timer_duration("1h 30m e 5s") == 5405
    assert parse_timer_duration("trinta segundos") == 30
    assert parse_timer_duration("sem duração") is None
    assert parse_timer_duration("oito dias") is None


def test_timer_commands_are_local_and_support_start_cancel_and_list():
    assert parse_local_command("Aurora, coloque um timer para dez minutos") == (
        "timer_start", {"seconds": 600}
    )
    assert parse_timer_command("timer de 5 minutos e 30 segundos") == (
        "timer_start", {"seconds": 330}
    )
    assert parse_local_command("cancele o timer 2") == (
        "timer_cancel", {"timer_id": 2}
    )
    assert parse_local_command("cancele todos os timers") == (
        "timer_cancel", {"timer_id": None}
    )
    assert parse_local_command("quais timers estão ativos?") == ("timer_list", {})
    assert parse_local_command("quanto tempo falta no temporizador?") == ("timer_list", {})
    assert parse_local_command("Aurora, tem timer?") == ("timer_list", {})
    assert parse_local_command("Aurora, coloque um timer") is None
    assert parse_timer_command(
        'Continuando a solicitação “coloque um timer”. A resposta é “dez minutos”.'
    ) == ("timer_start", {"seconds": 600})


def test_timer_pause_and_resume_commands_are_local_and_accept_timer_id():
    assert parse_local_command("pausa o timer 2") == ("timer_pause", {"timer_id": 2})
    assert parse_local_command("suspenda o temporizador") == ("timer_pause", {"timer_id": None})
    assert parse_local_command("retome o timer número 3") == ("timer_resume", {"timer_id": 3})
    assert parse_local_command("continue o temporizador") == ("timer_resume", {"timer_id": None})


def test_timer_manager_handles_multiple_start_cancel_list_and_completion(tmp_path):
    finished = []
    made = []

    class Signal:
        def connect(self, callback): self.callback = callback

    class FakeTimer:
        def __init__(self, _parent):
            self.timeout = Signal()
            self.started = None
            self.stopped = False
            made.append(self)
        def setSingleShot(self, value): self.single_shot = value
        def start(self, milliseconds): self.started = milliseconds
        def stop(self): self.stopped = True
        def fire(self): self.timeout.callback()

    manager = TimerManager(lambda timer_id, seconds: finished.append((timer_id, seconds)), timer_factory=FakeTimer,
                           state_path=tmp_path / "timers.json")
    assert manager.start(60) == "Timer 1 iniciado para 1 minuto."
    assert manager.start(90) == "Timer 2 iniciado para 1 minuto e 30 segundos."
    assert made[0].started == 60_000 and made[0].single_shot
    assert "Timer 1:" in manager.list_active() and "Timer 2:" in manager.list_active()
    assert manager.cancel(1) == "Cancelado o timer 1."
    assert made[0].stopped
    made[1].fire()
    assert finished == [(2, 90)]
    assert manager.list_active() == "Não há timers ativos."


def test_timer_manager_rejects_invalid_duration_and_can_cancel_all(tmp_path):
    made = []

    class Signal:
        def connect(self, _callback): pass

    class FakeTimer:
        def __init__(self, _parent): made.append(self); self.timeout = Signal(); self.stopped = False
        def setSingleShot(self, _value): pass
        def start(self, _milliseconds): pass
        def stop(self): self.stopped = True

    manager = TimerManager(lambda *_args: None, timer_factory=FakeTimer, state_path=tmp_path / "timers.json")
    assert "entre um segundo" in manager.start(0)
    assert manager.start(10) == "Timer 1 iniciado para 10 segundos."
    assert manager.start(20) == "Timer 2 iniciado para 20 segundos."
    assert manager.cancel() == "Cancelei todos os timers ativos."
    assert all(timer.stopped for timer in made)


def test_timer_manager_restores_active_timer_after_restart(tmp_path):
    made = []

    class Signal:
        def connect(self, callback): self.callback = callback

    class FakeTimer:
        def __init__(self, _parent): self.timeout = Signal(); self.started = None; made.append(self)
        def setSingleShot(self, value): self.single_shot = value
        def start(self, milliseconds): self.started = milliseconds
        def stop(self): pass

    state_path = tmp_path / "timers.json"
    first = TimerManager(lambda *_args: None, timer_factory=FakeTimer, state_path=state_path)
    assert first.start(60) == "Timer 1 iniciado para 1 minuto."

    restored = TimerManager(lambda *_args: None, timer_factory=FakeTimer, state_path=state_path)
    assert "Timer 1:" in restored.list_active()
    assert made[-1].started > 0

    restored.cancel(1)
    after_cancel = TimerManager(lambda *_args: None, timer_factory=FakeTimer, state_path=state_path)
    assert after_cancel.list_active() == "Não há timers ativos."


def test_timer_manager_pause_resume_persists_and_restores_paused_state(tmp_path, monkeypatch):
    made = []

    class Signal:
        def connect(self, callback): self.callback = callback

    class FakeTimer:
        def __init__(self, _parent): self.timeout = Signal(); self.started = None; self.stopped = False; made.append(self)
        def setSingleShot(self, _value): pass
        def start(self, milliseconds): self.started = milliseconds; self.stopped = False
        def stop(self): self.stopped = True

    now = [1000.0]
    monkeypatch.setattr("aurora_core.system.timers.time.time", lambda: now[0])
    state_path = tmp_path / "timers.json"
    first = TimerManager(lambda *_args: None, timer_factory=FakeTimer, state_path=state_path)
    assert first.start(60) == "Timer 1 iniciado para 1 minuto."
    now[0] += 12.2
    assert first.pause() == "Pausei o timer 1; faltavam 48 segundos."
    assert made[0].stopped
    assert "Timer 1: pausado, faltam 48 segundos." == first.list_active()

    restored = TimerManager(lambda *_args: None, timer_factory=FakeTimer, state_path=state_path)
    assert "Timer 1: pausado, faltam 48 segundos." == restored.list_active()
    assert made[-1].started is None
    now[0] += 500
    assert restored.resume(1) == "Retomei o timer 1 por mais 48 segundos."
    assert made[-1].started == 48_000
    now[0] += 10
    assert restored.pause(1) == "Pausei o timer 1; faltavam 38 segundos."


def test_timer_pause_requires_unambiguous_timer_and_resume_requires_paused_state(tmp_path):
    class Signal:
        def connect(self, _callback): pass

    class FakeTimer:
        def __init__(self, _parent): self.timeout = Signal()
        def setSingleShot(self, _value): pass
        def start(self, _milliseconds): pass
        def stop(self): pass

    manager = TimerManager(lambda *_args: None, timer_factory=FakeTimer, state_path=tmp_path / "timers.json")
    assert manager.pause() == "Não há timers ativos."
    manager.start(60); manager.start(90)
    assert manager.pause() == "Há vários timers ativos; diga o número do timer."
    assert manager.resume(1) == "O timer 1 já está em andamento."
    assert "Pausei o timer 1" in manager.pause(1)
    assert manager.resume() == "Há vários timers ativos; diga o número do timer."


def test_timer_pause_and_resume_roll_back_when_state_cannot_be_saved(tmp_path, monkeypatch):
    made = []

    class Signal:
        def connect(self, _callback): pass

    class FakeTimer:
        def __init__(self, _parent): self.timeout = Signal(); self.started = None; self.stopped = False; made.append(self)
        def setSingleShot(self, _value): pass
        def start(self, milliseconds): self.started = milliseconds; self.stopped = False
        def stop(self): self.stopped = True

    monkeypatch.setattr("aurora_core.system.timers.time.time", lambda: 1000.0)
    manager = TimerManager(lambda *_args: None, timer_factory=FakeTimer, state_path=tmp_path / "timers.json")
    manager.start(60)
    monkeypatch.setattr(manager, "_persist", lambda: (_ for _ in ()).throw(OSError("disk full")))
    assert "continua ativo" in manager.pause(1)
    assert not made[0].stopped and manager._timers[1]["paused_remaining"] is None

    monkeypatch.undo()
    assert "Pausei o timer 1" in manager.pause(1)
    monkeypatch.setattr(manager, "_persist", lambda: (_ for _ in ()).throw(OSError("disk full")))
    assert "continua pausado" in manager.resume(1)
    assert made[0].stopped and manager._timers[1]["paused_remaining"] is not None


def test_corrupt_nonfinite_paused_timer_state_does_not_break_startup(tmp_path):
    state_path = tmp_path / "timers.json"
    state_path.write_text(
        '{"next_id": 2, "timers": [{"id": 1, "deadline": 1000, '
        '"seconds": 60, "paused_remaining": 1e999}]}',
        encoding="utf-8",
    )
    manager = TimerManager(lambda *_args: None, state_path=state_path)
    assert manager.list_active() == "Não há timers ativos."


def test_timer_duration_speech_is_compact_and_pluralized():
    assert format_duration(3661) == "1 hora e 1 minuto e 1 segundo"
    assert format_duration(120) == "2 minutos"


def test_timer_actions_use_the_local_manager_without_the_model():
    class Manager:
        def start(self, seconds): return f"started {seconds}"
        def cancel(self, timer_id): return f"cancelled {timer_id}"
        def list_active(self): return "active timers"
        def pause(self, timer_id): return f"paused {timer_id}"
        def resume(self, timer_id): return f"resumed {timer_id}"

    service = type("Service", (), {"timer_manager": Manager()})()
    assert actions.execute_action(service, "timer_start", {"seconds": 30}) == "started 30"
    assert actions.execute_action(service, "timer_cancel", {"timer_id": 2}) == "cancelled 2"
    assert actions.execute_action(service, "timer_list", {}) == "active timers"
    assert actions.execute_action(service, "timer_pause", {"timer_id": 1}) == "paused 1"
    assert actions.execute_action(service, "timer_resume", {"timer_id": 1}) == "resumed 1"


def test_timer_completion_announces_locally_and_does_not_reset_an_active_request():
    spoken = []
    revealed = []

    class Voice:
        request_active = threading.Event()

    class Orb:
        def reveal(self, mode): revealed.append(mode)

    class Speaker:
        def say(self, text): spoken.append(text)

    class Service:
        voice = Voice()
        orb = Orb()
        speaker = Speaker()
        activity_generation = 3
        response_finished = False
        response_summary = "in progress"

    service = Service()
    AuroraService._timer_finished(service, 1, 60)
    assert spoken == ["O timer 1, de 1 minuto, terminou."]
    assert revealed == ["speaking"]
    assert service.activity_generation == 4
    assert service.response_finished

    Voice.request_active.set()
    service.response_finished = False
    service.response_summary = "in progress"
    AuroraService._timer_finished(service, 2, 30)
    assert spoken[-1] == "O timer 2, de 30 segundos, terminou."
    assert service.activity_generation == 4
    assert not service.response_finished
    assert service.response_summary == "in progress"
