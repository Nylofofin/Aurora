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


def test_timer_manager_handles_multiple_start_cancel_list_and_completion():
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

    manager = TimerManager(lambda timer_id, seconds: finished.append((timer_id, seconds)), timer_factory=FakeTimer)
    assert manager.start(60) == "Timer 1 iniciado para 1 minuto."
    assert manager.start(90) == "Timer 2 iniciado para 1 minuto e 30 segundos."
    assert made[0].started == 60_000 and made[0].single_shot
    assert "Timer 1:" in manager.list_active() and "Timer 2:" in manager.list_active()
    assert manager.cancel(1) == "Cancelado o timer 1."
    assert made[0].stopped
    made[1].fire()
    assert finished == [(2, 90)]
    assert manager.list_active() == "Não há timers ativos."


def test_timer_manager_rejects_invalid_duration_and_can_cancel_all():
    made = []

    class Signal:
        def connect(self, _callback): pass

    class FakeTimer:
        def __init__(self, _parent): made.append(self); self.timeout = Signal(); self.stopped = False
        def setSingleShot(self, _value): pass
        def start(self, _milliseconds): pass
        def stop(self): self.stopped = True

    manager = TimerManager(lambda *_args: None, timer_factory=FakeTimer)
    assert "entre um segundo" in manager.start(0)
    assert manager.start(10) == "Timer 1 iniciado para 10 segundos."
    assert manager.start(20) == "Timer 2 iniciado para 20 segundos."
    assert manager.cancel() == "Cancelei todos os timers ativos."
    assert all(timer.stopped for timer in made)


def test_timer_duration_speech_is_compact_and_pluralized():
    assert format_duration(3661) == "1 hora e 1 minuto e 1 segundo"
    assert format_duration(120) == "2 minutos"


def test_timer_actions_use_the_local_manager_without_the_model():
    class Manager:
        def start(self, seconds): return f"started {seconds}"
        def cancel(self, timer_id): return f"cancelled {timer_id}"
        def list_active(self): return "active timers"

    service = type("Service", (), {"timer_manager": Manager()})()
    assert actions.execute_action(service, "timer_start", {"seconds": 30}) == "started 30"
    assert actions.execute_action(service, "timer_cancel", {"timer_id": 2}) == "cancelled 2"
    assert actions.execute_action(service, "timer_list", {}) == "active timers"


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
        def _mobile_audio_owned(self): return False

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
