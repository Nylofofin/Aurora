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


def test_follow_up_turn_rearms_capture_without_wake_feedback(monkeypatch):
    import aurora_core.service as service_module

    timers = []

    class Timer:
        @staticmethod
        def singleShot(delay, callback):
            timers.append((delay, callback))

    class Voice:
        speaking = False
        def __init__(self):
            self.calls = []
        def end_request(self): self.calls.append("end")
        def begin_request(self): self.calls.append("begin")
        def request_once(self): self.calls.append("once")

    class Orb:
        def reveal(self, mode): self.mode = mode
        def dismiss(self): self.dismissed = True

    class Stub:
        continuous_mode = True
        conversation_turns = 0
        conversation_token = 4
        cfg = {"conversation_max_turns": 8, "conversation_idle_seconds": 18}
        voice = Voice()
        orb = Orb()
        speaker = type("Speaker", (), {"active": False, "q": []})()
        inf = None
        background_requests = []
        def _mobile_audio_owned(self): return False

    monkeypatch.setattr(service_module, "QTimer", Timer)
    stub = Stub()
    service_module.AuroraService._continue_conversation(stub)

    assert stub.voice.calls == ["end", "begin", "once"]
    assert stub.orb.mode == "listening"
    assert timers and timers[0][0] == 18_000
