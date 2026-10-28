# SPDX-License-Identifier: GPL-3.0-only
from aurora_core.conversation import is_conversation_closing, session_closing_intent
from aurora_core.config import DEFAULTS


def test_closing_cues_are_standalone_and_language_level():
    assert is_conversation_closing("obrigado")
    assert is_conversation_closing("Até mais!")
    assert is_conversation_closing("pode descansar")
    assert is_conversation_closing("fecha a sessão")
    assert is_conversation_closing("encerra")
    assert is_conversation_closing("sair")
    assert not is_conversation_closing("obrigado, abre o terminal")
    assert not is_conversation_closing("obrigado por explicar")
    assert not is_conversation_closing("tchau, pesquisa o clima")
    assert session_closing_intent("fecha") == "ambiguous"
    assert session_closing_intent("fecha o navegador") == "none"


def test_ambiguous_session_close_requires_a_clear_confirmation():
    import aurora_core.service as service_module

    class Stub:
        pending_clarification = {"kind": "session_close"}
        closed = False
        response_finished = False

        def _close_conversation_session(self):
            self.closed = True
        def speak_in_selected_language(self, text):
            self.spoken = text

    stub = Stub()
    assert service_module.AuroraService._handle_clarification_reply(stub, "não")
    assert not stub.closed

    stub.pending_clarification = {"kind": "session_close"}
    assert service_module.AuroraService._handle_clarification_reply(stub, "sim")
    assert stub.closed


def test_closing_session_persists_closed_state_and_cancels_pending_action():
    import threading
    import aurora_core.service as service_module

    class Store:
        closed = False
        def close(self): self.closed = True

    class Voice:
        ended = False
        def end_request(self): self.ended = True

    class Orb:
        pending = True

    class Stub:
        continuous_mode = True
        conversation_token = 2
        pending_clarification = {"kind": "session_close"}
        pending = {"event": threading.Event(), "result": ""}
        session_store = Store()
        context_history = [{"role": "user", "content": "Oi"}]
        inferences = []
        action_cancel_event = threading.Event()
        voice = Voice()
        orb = Orb()
        response_finished = False

        def speak_in_selected_language(self, text): self.spoken = text

    stub = Stub()
    pending = stub.pending
    service_module.AuroraService._close_conversation_session(stub)

    assert stub.session_store.closed
    assert not stub.continuous_mode
    assert stub.context_history == []
    assert stub.pending is None
    assert pending["event"].is_set()
    assert pending["result"] == "Sessão encerrada; ação cancelada."
    assert stub.action_cancel_event.is_set()
    assert stub.spoken == "Tudo bem. Até logo."


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

    monkeypatch.setattr(service_module, "QTimer", Timer)
    stub = Stub()
    service_module.AuroraService._continue_conversation(stub)

    assert stub.voice.calls == ["end", "begin", "once"]
    assert stub.orb.mode == "listening"
    assert timers and timers[0][0] == 18_000
