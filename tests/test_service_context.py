import aurora_core.service as service_module
import threading


def test_fast_search_answer_keeps_evidence_in_followup_context(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "ground_search_answer",
        lambda _question, answer, _evidence, _sources: answer,
    )

    class ServiceStub:
        current_prompt = "Quais são as notícias recentes?"
        request_generation = 7
        active_search_context = "Resultados da web usados como evidência: fonte e data"

        def quick_summary_done(self, summary, generation, context_extra=""):
            self.saved = (summary, generation, context_extra)

    stub = ServiceStub()
    service_module.AuroraService.quick_search_answer_done(
        stub, "Resumo confirmado.", 7, ["evidência"], ["fonte"],
    )

    assert stub.saved[0:2] == ("Resumo confirmado.", 7)
    assert "fonte e data" in stub.saved[2]
    assert stub.active_search_context == ""


def test_stale_fast_search_answer_does_not_consume_context(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "ground_search_answer",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must be ignored")),
    )

    class ServiceStub:
        current_prompt = "question"
        request_generation = 8
        active_search_context = "new request evidence"

    stub = ServiceStub()
    service_module.AuroraService.quick_search_answer_done(
        stub, "stale answer", 7, [], [],
    )

    assert stub.active_search_context == "new request evidence"


def test_finished_signal_from_old_inference_only_releases_its_reference():
    old_inference = type("Worker", (), {"request_generation": 7})()

    class ServiceStub:
        inferences = [old_inference]
        inf = object()
        request_generation = 8
        def sender(self): return old_inference

    stub = ServiceStub()
    service_module.AuroraService.inference_finished(stub)

    assert stub.inferences == []


def test_expired_approval_cannot_be_executed_by_a_late_click(monkeypatch):
    now = [100.0]
    timers = []
    executed = []
    monkeypatch.setattr(service_module.time, "monotonic", lambda: now[0])

    class FakeTimer:
        @staticmethod
        def singleShot(milliseconds, callback):
            timers.append((milliseconds, callback))

    class Orb:
        pending = True
        def isVisible(self): return False
        def reveal(self, _mode): pass
        def set_mode(self, _mode): pass

    class ServiceStub:
        pending = None
        orb = Orb()
        def speak_in_selected_language(self, _text): pass
        def execute_action(self, *_args): executed.append(True)
        def complete_direct_action(self, text): self.completed = text
        def expire_approval(self, detail):
            service_module.AuroraService.expire_approval(self, detail)

    monkeypatch.setattr(service_module, "QTimer", FakeTimer)
    detail = {"name": "obs_record", "args": {"action": "start"},
              "event": threading.Event(), "direct": True}
    stub = ServiceStub()

    service_module.AuroraService.request_approval(stub, "obs_record", detail)
    assert timers[0][0] == 90_000
    assert detail["expires_at"] == 190.0

    now[0] = 191.0
    service_module.AuroraService.resolve_approval(stub, True)

    assert not executed
    assert stub.pending is None
    assert detail["event"].is_set()
    assert "expirou" in detail["result"]
    assert "Não executei" in stub.completed


def test_screen_approval_explains_voice_cancellation(monkeypatch):
    monkeypatch.setattr(service_module.QTimer, "singleShot", lambda *_args: None)

    class Voice:
        enabled = False
        def enable_control_cancel(self): self.enabled = True

    class Orb:
        def isVisible(self): return True
        def set_mode(self, _mode): pass

    class ServiceStub:
        pending = None
        voice = Voice()
        orb = Orb()
        def speak_in_selected_language(self, text): self.spoken = text

    stub = ServiceStub()
    detail = {"name": "type_accessible_text", "args": {"field": "Search", "application": "Editor"},
              "event": threading.Event()}

    service_module.AuroraService.request_approval(stub, detail["name"], detail)

    assert stub.voice.enabled
    assert "Diga “parar”" in stub.spoken
    assert "clique com o botão direito" in stub.spoken


def test_tapping_pending_approval_interrupts_voice_before_execution():
    sequence = []
    class Speaker:
        def interrupt(self): sequence.append("interrupt")
    class Voice:
        request_active = threading.Event()
    class ServiceStub:
        pending = {"action": "pending"}
        speaker = Speaker()
        voice = Voice()
        def resolve_approval(self, approved):
            sequence.append(("resolve", approved))
    service_module.AuroraService.listen_once(ServiceStub())
    assert sequence == ["interrupt", ("resolve", True)]


def test_expiration_callback_for_old_approval_does_not_clear_new_one():
    old = {"event": threading.Event()}
    current = {"event": threading.Event()}

    class Orb:
        pending = True
        def set_mode(self, _mode): pass

    class ServiceStub:
        pending = current
        orb = Orb()
        def complete_direct_action(self, _text): raise AssertionError("not a direct approval")

    service_core = ServiceStub()
    service_module.AuroraService.expire_approval(service_core, old)

    assert service_core.pending is current
    assert not old["event"].is_set()
