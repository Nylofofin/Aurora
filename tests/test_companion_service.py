from concurrent.futures import Future
import threading

import aurora_core.routing as routing
from aurora_core.service import AuroraService


class _Orb:
    def isVisible(self): return True
    def reveal(self, _mode): pass
    def set_mode(self, _mode): pass
    def dismiss(self): pass


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


def test_companion_routes_without_local_wake_and_refuses_pc_automation(monkeypatch):
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
        def run_local_action(self, *_args): raise AssertionError("mobile request must not execute local actions")

    service = Service()
    routing.route_request(service, "Tire uma captura de tela")
    assert service.result[0] == "O controle do computador pelo celular ainda não está habilitado nesta Alpha."


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
