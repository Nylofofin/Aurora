from concurrent.futures import Future
import threading

import aurora_core.routing as routing
from aurora_core.service import AuroraService


class _Orb:
    def isVisible(self): return True
    def reveal(self, _mode): pass
    def set_mode(self, _mode): pass
    def dismiss(self): pass
    def hide(self): pass


class _Voice:
    def __init__(self, active=False):
        self.request_active = threading.Event()
        if active: self.request_active.set()
        self.speaking = False


def test_companion_completion_returns_remote_context_and_restores_desktop_context():
    future = Future()

    class Service:
        companion_request = {"future": future, "previous": {"history": [{"role": "user", "content": "local"}], "prompt": "local prompt", "search": "local search", "language": "Português brasileiro"}}
        context_history = [{"role": "user", "content": "remote"}, {"role": "assistant", "content": "resposta e fontes"}]
        current_prompt = "remote prompt"
        active_search_context = "remote search"
        response_language = "English"
        voice = _Voice()
        orb = _Orb()

    service = Service()
    AuroraService._finish_companion_request(service, "answer")
    result = future.result()
    assert result["answer"] == "answer"
    assert result["context_history"][-1]["content"] == "resposta e fontes"
    assert service.context_history == [{"role": "user", "content": "local"}]
    assert service.current_prompt == "local prompt"
    assert service.active_search_context == "local search"
    assert service.response_language == "Português brasileiro"
    assert service.voice.speaking is False


def test_companion_routes_explicit_local_action_without_desktop_wake(monkeypatch):
    monkeypatch.setattr(routing, "local_datetime_answer", lambda _prompt: "Agora são dez horas.")
    monkeypatch.setattr(routing, "parse_local_command", lambda _prompt: ("take_screenshot", {}))

    class Service:
        voice = _Voice()
        orb = _Orb()
        inf = None
        cfg = {"model": "gemma3:1b"}
        context_history = []
        activity_generation = 0
        request_generation = 0
        response_language = "Português brasileiro"
        companion_request = {"future": Future()}

        def quick_summary_done(self, text, generation): self.result = (text, generation)
        def run_local_action(self, *args): self.action = args

    service = Service()
    routing.route_request(service, "Tire uma captura de tela")
    assert service.action == ("take_screenshot", {})


def test_mobile_action_requiring_desktop_approval_is_refused_without_hanging():
    class Service:
        companion_request = {"future": Future()}
        current_prompt = "Feche o navegador"
        response_summary = ""
        response_finished = False
        orb = _Orb()
        def remember_exchange(self, *_args): pass
        def complete_direct_action(self, result): self.result = result
        def request_approval(self, *_args): raise AssertionError("desktop approval UI must not be opened")

    service = Service()
    AuroraService.run_local_action(service, "close_application", {"application": "browser"})
    assert "confirmação na bolha do computador" in service.result


def test_companion_request_can_enter_shared_router_without_local_voice(monkeypatch):
    monkeypatch.setattr(routing, "parse_local_command", lambda _prompt: None)
    monkeypatch.setattr(routing, "local_datetime_answer", lambda _prompt: "Agora são dez horas.")

    class Service:
        voice = _Voice()
        orb = _Orb()
        inf = None
        cfg = {"model": "gemma3:1b"}
        context_history = []
        activity_generation = 0
        request_generation = 0
        response_language = "Português brasileiro"
        companion_request = {"future": Future()}

        def quick_summary_done(self, text, generation): self.result = (text, generation)

    service = Service()
    routing.route_request(service, "Que horas são?")
    assert service.result[0] == "Agora são dez horas."


def test_mobile_control_suspends_pc_microphone_and_disconnect_resumes_it():
    class Voice(_Voice):
        def __init__(self):
            super().__init__()
            self.mobile_owned = threading.Event()
        def end_request(self): pass

    class Speaker:
        interrupted = False
        def interrupt(self): self.interrupted = True

    class Service:
        voice = Voice()
        speaker = Speaker()
        orb = _Orb()
        pending = None
        companion_request = None
        inf = None
        background_requests = []
        companion_server = None

    service = Service()
    accepted = Future()
    AuroraService._set_companion_control(service, True, accepted)
    assert accepted.result() is True
    assert service.voice.mobile_owned.is_set()
    assert service.speaker.interrupted

    released = Future()
    AuroraService._set_companion_control(service, False, released)
    assert released.result() is True
    assert not service.voice.mobile_owned.is_set()


def test_mobile_control_cannot_preempt_active_pc_request():
    class Service:
        voice = _Voice(active=True)
        companion_request = None
        pending = None
        inf = None
        background_requests = []

    future = Future()
    AuroraService._set_companion_control(Service(), True, future)
    assert future.result() is False
