# SPDX-License-Identifier: GPL-3.0-only
import aurora_core.service as service_module
import threading
import time


def test_latest_version_guard_requires_matching_page_versions_on_distinct_hosts():
    source_a = {
        "host": "python.org",
        "snippet": "Trecho da página aberta agora: Python 3.15.1 first released today.",
    }
    source_b = {
        "host": "docs.python.org",
        "snippet": "Trecho da página aberta agora: Python 3.15.1 documentation.",
    }
    conflict = {
        "host": "mirror.example",
        "snippet": "Trecho da página aberta agora: Python 3.14.9 documentation.",
    }

    assert service_module._has_corroborated_version_pages([source_a, source_b])
    assert not service_module._has_corroborated_version_pages([source_a, conflict])
    assert not service_module._has_corroborated_version_pages([source_a, {**source_b, "host": "python.org"}])


def test_latest_version_speech_uses_only_shared_version_and_labels_prerelease():
    items = [
        {
            "host": "obsproject.com",
            "snippet": "Trecho da página aberta agora: Windows release Version: 32.2.2 Released August 14th.",
        },
        {
            "host": "github.com",
            "snippet": "Trecho da página aberta agora: OBS Studio 33.0.0 Release Candidate 3; OBS Studio 33.0.0 Beta 6; OBS Studio 32.2.0 Release Candidate 2; OBS Studio 32.2.2.",
        },
    ]

    answer = service_module._format_latest_version_answer(items)

    assert "32.2.2" in answer
    assert "33.0.0 Release Candidate 3" in answer
    assert "pré-lançamento" in answer
    assert answer.count("33.0.0") == 1
    assert "32.2.0" not in answer


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


def test_screenshot_does_not_request_a_second_aurora_confirmation():
    from aurora_core.system.approval import requires_user_approval
    assert requires_user_approval("take_screenshot", {})
    assert not requires_user_approval("take_screenshot", {}, explicit_user_request=True)
    assert requires_user_approval("open_url", {"url": "https://example.com"})
    assert not requires_user_approval("open_url", {"url": "https://example.com"}, explicit_user_request=True)
    assert requires_user_approval("close_application", {"application": "Editor"})
    assert requires_user_approval("obs_record", {"action": "start"})
    assert requires_user_approval("obs_record", {"action": "stop"})
    assert not requires_user_approval("obs_record", {"action": "stop"}, explicit_user_request=True)

    class Orb:
        pending = False
        def set_mode(self, _mode): pass

    class ServiceStub:
        pending = None
        orb = Orb()
        def _start_screenshot_action(self, detail):
            self.executed = detail["name"] == "take_screenshot"
            detail["event"].set()

    detail = {"name": "take_screenshot", "args": {}, "event": threading.Event(),
              "explicit_user_request": True}
    stub = ServiceStub()
    service_module.AuroraService.request_approval(stub, detail["name"], detail)
    assert stub.executed
    assert detail["event"].is_set()
    assert stub.pending is None


def test_approved_model_screenshot_uses_async_portal_worker():
    detail = {"name": "take_screenshot", "args": {}, "event": threading.Event(),
              "result": "Ação recusada."}

    class Orb:
        pending = True
        def set_mode(self, _mode): pass

    class Speaker:
        def interrupt(self): pass

    class ServiceStub:
        pending = detail
        orb = Orb()
        speaker = Speaker()
        voice = type("Voice", (), {})()
        def _start_screenshot_action(self, received): self.started = received
        def execute_action(self, *_args): raise AssertionError("must use the portal worker")

    stub = ServiceStub()
    service_module.AuroraService.resolve_approval(stub, True)

    assert stub.pending is None
    assert stub.started is detail


def test_obs_approval_runs_off_the_gui_thread(monkeypatch):
    from PySide6.QtCore import QCoreApplication, QObject
    app = QCoreApplication.instance() or QCoreApplication([])
    main_thread = threading.get_ident()
    observed = []

    def slow_obs(action, *_args, **_kwargs):
        observed.append((action, threading.get_ident()))
        time.sleep(0.12)
        return "Gravação iniciada no OBS."

    monkeypatch.setattr(service_module.aurora_integrations, "obs_record", slow_obs)

    class Orb:
        pending = True
        def set_mode(self, _mode): pass
        def isVisible(self): return True

    class Voice:
        def disable_control_cancel(self): pass

    class ServiceStub(service_module.AuroraService):
        def __init__(self):
            QObject.__init__(self)
            self.cfg = {"obs_host": "127.0.0.1", "obs_port": 4455}
            self.action_workers = []
            self.obs_details = {}
            self.action_cancel_event = threading.Event()
            self.request_generation = 0
            self.pending = None
            self.orb = Orb()
            self.voice = Voice()
    detail = {"name": "obs_record", "args": {"action": "start"},
              "event": threading.Event(), "result": "Ação recusada."}
    stub = ServiceStub()
    stub.pending = detail
    started = time.monotonic()
    service_module.AuroraService.resolve_approval(stub, True)
    elapsed = time.monotonic() - started
    assert elapsed < 0.1
    deadline = time.monotonic() + 2
    while not detail["event"].is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert detail["event"].is_set()
    assert observed and observed[0][0] == "start"
    assert observed[0][1] != main_thread
    assert detail["result"] == "Gravação iniciada no OBS."


def test_direct_screenshot_runs_off_the_gui_thread_and_uses_natural_confirmation(monkeypatch, tmp_path):
    from PySide6.QtCore import QCoreApplication, QObject
    app = QCoreApplication.instance() or QCoreApplication([])
    main_thread = threading.get_ident()
    observed = []
    saved_path = tmp_path / "Aurora_2026-10-22.png"

    def fake_capture(_pictures, cancel_event=None, parent_window=""):
        observed.append(threading.get_ident())
        observed.append(parent_window)
        time.sleep(0.05)
        saved_path.write_bytes(b"image")
        return saved_path

    monkeypatch.setattr(service_module.aurora_integrations, "capture_screenshot", fake_capture)
    def fail_audit_log(*_a, **_k): raise OSError("state directory unavailable")
    monkeypatch.setattr(service_module.aurora_integrations, "_append_action_log", fail_audit_log)
    monkeypatch.setattr(service_module, "xdg_user_directory", lambda _kind: str(tmp_path))
    monkeypatch.setattr(service_module.QApplication, "platformName", staticmethod(lambda: "xcb"))

    class Orb:
        class View:
            def winId(self): return 0x1234
        view = View()
        def set_mode(self, _mode): pass
        def isVisible(self): return True

    class Voice:
        request_active = threading.Event()
        request_active.set()

    class ServiceStub(service_module.AuroraService):
        def __init__(self):
            QObject.__init__(self)
            self.orb = Orb()
            self.voice = Voice()
            self.action_workers = []
            self.obs_details = {}
            self.action_cancel_event = threading.Event()
            self.request_generation = 3
            self.cfg = {}
        def complete_direct_action(self, text): self.completed = text

    stub = ServiceStub()
    service_module.AuroraService.run_local_action(stub, "take_screenshot", {})
    deadline = time.monotonic() + 2
    while not hasattr(stub, "completed") and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert observed and observed[0] != main_thread
    assert observed[1] == "x11:1234"
    assert saved_path.read_bytes() == b"image"
    assert stub.completed == "Pronto, tirei o print. Salvei em Imagens, na pasta Aurora."
    assert str(saved_path) not in stub.completed


def test_action_worker_exit_without_result_releases_waiting_request():
    from PySide6.QtCore import QCoreApplication, QObject, QThread
    app = QCoreApplication.instance() or QCoreApplication([])

    class Orb:
        def __init__(self): self.modes = []
        def isVisible(self): return True
        def set_mode(self, mode): self.modes.append(mode)

    class ServiceStub(service_module.AuroraService):
        def __init__(self):
            QObject.__init__(self)
            self.orb = Orb()
            self.action_workers = []
            self.obs_details = {}
            self.request_generation = 7
            self.voice = type("Voice", (), {"request_active": threading.Event()})()

    class SilentWorker(QThread):
        def run(self): pass

    stub = ServiceStub()
    worker = SilentWorker()
    detail = {"event": threading.Event(), "request_generation": 7,
              "cancel_event": threading.Event(), "direct": False}
    stub.action_workers.append(worker)
    stub.obs_details[worker] = detail
    worker.finished.connect(stub._action_worker_finished)
    worker.start()
    deadline = time.monotonic() + 2
    while not detail["event"].is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert detail["event"].is_set()
    assert detail["result"] == "A ação terminou sem retornar um resultado confirmado."
    assert not stub.action_workers
    assert stub.orb.modes == ["error"]


def test_action_watchdog_cancels_worker_and_exits_controlling_state():
    from PySide6.QtCore import QObject

    class Orb:
        def __init__(self): self.modes = []
        def isVisible(self): return True
        def set_mode(self, mode): self.modes.append(mode)

    class ServiceStub(service_module.AuroraService):
        def __init__(self):
            QObject.__init__(self)
            self.orb = Orb()
            self.obs_details = {}
            self.request_generation = 9
            self.voice = type("Voice", (), {"request_active": threading.Event()})()

    stub = ServiceStub()
    worker = object()
    cancel_event = threading.Event()
    detail = {"event": threading.Event(), "request_generation": 9,
              "cancel_event": cancel_event, "direct": False}
    stub.obs_details[worker] = detail

    stub._expire_action_worker(worker, detail, "A captura excedeu o limite de tempo.")

    assert detail["event"].is_set()
    assert cancel_event.is_set()
    assert detail["result"] == "A captura excedeu o limite de tempo."
    assert worker not in stub.obs_details
    assert stub.orb.modes == ["error"]


def test_completed_action_recovers_stale_controlling_mode():
    from PySide6.QtCore import QObject

    class Orb:
        mode = "controlling"
        def __init__(self): self.modes = []
        def isVisible(self): return True
        def set_mode(self, mode): self.mode = mode; self.modes.append(mode)

    class ServiceStub(service_module.AuroraService):
        def __init__(self):
            QObject.__init__(self)
            self.orb = Orb()
            self.action_workers = []
            self.pending = None
            self.inf = None
            self.speaker = type("Speaker", (), {
                "playing": False, "active": False, "q": type("Queue", (), {"empty": lambda _self: True})()
            })()
            self.voice = type("Voice", (), {"request_active": threading.Event()})()
            self.dismiss_delays = []
        def schedule_dismiss(self, delay): self.dismiss_delays.append(delay)

    stub = ServiceStub()
    stub._settle_stale_controlling_mode()

    assert stub.orb.mode == "idle"
    assert stub.dismiss_delays == [900]


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


def test_new_wake_defaults_response_language_to_brazilian_portuguese():
    class Voice:
        def begin_request(self): pass
    class Orb:
        def reveal(self, _mode): pass
    class Feedback:
        def play(self): pass
    class ServiceStub:
        response_language = "Spanish"
        activity_generation = 0
        inf = None
        voice = Voice()
        orb = Orb()
        feedback = Feedback()
        def _mobile_audio_owned(self): return False

    stub = ServiceStub()
    service_module.AuroraService.wake(stub)
    assert stub.response_language == "Português brasileiro"


def test_obs_stop_action_clears_interrupt_listener_without_cancelling_stop(monkeypatch):
    from PySide6.QtCore import QObject
    interrupt = threading.Event()
    interrupt.set()

    class Signal:
        def connect(self, _callback): pass
    class Worker:
        def __init__(self, *_args):
            self.completed = Signal()
            self.finished = Signal()
        def start(self): pass
        def isRunning(self): return False
    monkeypatch.setattr(service_module, "_ObsActionRequest", Worker)

    class Orb:
        def set_mode(self, _mode): pass
    class Voice:
        interrupt_active = interrupt
    class ServiceStub(service_module.AuroraService):
        def __init__(self):
            QObject.__init__(self)
            self.voice = Voice()
            self.orb = Orb()
            self.cfg = {}
            self.action_cancel_event = threading.Event()
            self.request_generation = 1
            self.action_workers = []
            self.obs_details = {}
        def _schedule_action_watchdog(self, *_args): pass

    stub = ServiceStub()
    detail = {"name": "obs_record", "args": {"action": "stop"},
              "event": threading.Event(), "result": "Ação recusada."}
    service_module.AuroraService._start_obs_action(stub, detail)

    assert not interrupt.is_set()
    assert len(stub.action_workers) == 1
    assert stub.obs_details[stub.action_workers[0]] is detail


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


def test_completed_one_shot_request_dismisses_the_orb_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(service_module.QTimer, "singleShot", lambda _delay, callback: callback())

    class Queue:
        def empty(self): return True
    class Speaker:
        active = False
        playing = False
        q = Queue()
    class Voice:
        def end_request(self): calls.append("end_request")
    class Orb:
        def pulse_complete(self): calls.append("pulse")
        def dismiss(self): calls.append("dismiss")
    class ServiceStub:
        activity_generation = 4
        response_finished = True
        speaker = Speaker()
        voice = Voice()
        orb = Orb()
        inf = None
        background_requests = []
        def weather_busy(self): return False
        def _mobile_audio_owned(self): return False
        def listen_once(self): calls.append("listen_once")

    service_module.AuroraService.schedule_dismiss(ServiceStub(), 0)

    assert calls == ["pulse", "end_request", "dismiss"]
