# SPDX-License-Identifier: GPL-3.0-only
from datetime import datetime
import base64
import hashlib
import json
import time
import socket
import threading
import pytest

import aurora
import aurora_integrations as integrations
import aurora_core.system.obs as obs
import aurora_core.system.screenshot as screenshot
import aurora_core.service as service_module
import aurora_core.system.actions as system_actions
import aurora_core.system.apps as apps_module


def test_screenshot_portal_request_path_preserves_sender_prefix():
    assert screenshot._portal_request_object_path(":1.42", "aurora_token") == (
        "/org/freedesktop/portal/desktop/request/_1_42/aurora_token"
    )


def test_screenshot_parent_identifier_uses_x11_hex_window_id():
    assert screenshot.screenshot_parent_identifier(0x12AB) == "x11:12ab"
    assert screenshot.screenshot_parent_identifier(0) == ""
    assert screenshot.screenshot_parent_identifier(None) == ""
    assert screenshot.screenshot_parent_identifier(0x12AB, "wayland") == ""


def test_gnome_saved_screenshot_is_recovered_after_lost_portal_reply(tmp_path):
    source = tmp_path / "Screenshot-5.png"
    source.write_bytes(b"portal-created-image")
    recovered = screenshot._recover_gnome_saved_screenshot(
        tmp_path, time.time() - 2)

    assert recovered is not None
    assert recovered.parent == tmp_path / "Aurora"
    assert recovered.read_bytes() == b"portal-created-image"
    assert source.exists()


def test_gnome_screenshot_recovery_does_not_guess_between_multiple_files(tmp_path):
    (tmp_path / "Screenshot-5.png").write_bytes(b"one")
    (tmp_path / "Screenshot-6.png").write_bytes(b"two")

    assert screenshot._recover_gnome_saved_screenshot(
        tmp_path, time.time() - 2) is None


def test_screenshot_portal_uses_qt_encoded_slot_signature():
    from PySide6.QtCore import QObject, Slot

    class Response(QObject):
        @Slot(screenshot._portal_response_code_type(), "QVariantMap")
        def receive(self, _code, _data):
            pass

    assert screenshot._portal_response_slot().startswith("1receive(")
    assert Response.staticMetaObject.indexOfSlot("receive(uint,QVariantMap)") >= 0


def test_cancelled_screenshot_closes_portal_request_without_saving(monkeypatch, tmp_path):
    from PySide6 import QtDBus
    cancelled = threading.Event()
    cancelled.set()
    calls = []

    class Message:
        class MessageType:
            ErrorMessage = object()
        def __init__(self, path, interface, method):
            self.path, self.interface, self.method = path, interface, method
        @staticmethod
        def createMethodCall(_service, path, interface, method):
            return Message(path, interface, method)
        def setArguments(self, _args): pass
        def type(self): return object()
        def errorMessage(self): return ""

    class Bus:
        def isConnected(self): return True
        def baseService(self): return ":1.42"
        def connect(self, *_args): return True
        def disconnect(self, *_args): pass
        def call(self, message, *_args):
            calls.append((message.path, message.interface, message.method))
            return type("Reply", (), {"type": lambda _self: object(),
                                      "errorMessage": lambda _self: ""})()

    monkeypatch.setattr(QtDBus, "QDBusMessage", Message)
    monkeypatch.setattr(QtDBus.QDBusConnection, "sessionBus", lambda: Bus())
    try:
        screenshot.capture_screenshot(tmp_path, cancel_event=cancelled)
    except RuntimeError as exc:
        assert "cancelada" in str(exc)
    else:
        raise AssertionError("cancelled screenshots must not be saved")
    assert calls[-1][1:] == ("org.freedesktop.portal.Request", "Close")
    assert not (tmp_path / "Aurora").exists()


def test_screenshot_is_saved_if_portal_completed_before_cancel_arrived(monkeypatch, tmp_path):
    from PySide6 import QtCore, QtDBus
    source = tmp_path / "portal-shot.png"
    source.write_bytes(b"completed capture")
    cancelled = threading.Event()
    holder = {}

    class Loop:
        def quit(self): pass
        def exec(self):
            holder["receiver"].receive(0, {"uri": source.as_uri()})
            cancelled.set()  # Cancellation races after the portal's success.

    class Timer:
        class Timeout:
            def connect(self, _callback): pass
        def __init__(self): self.timeout = self.Timeout()
        def setSingleShot(self, _value): pass
        def setInterval(self, _value): pass
        def start(self, *_args): pass
        def stop(self): pass

    class Message:
        class MessageType:
            ErrorMessage = object()
        @staticmethod
        def createMethodCall(*_args): return Message()
        def setArguments(self, args): self.arguments = args
        def type(self): return object()
        def errorMessage(self): return ""

    class Bus:
        calls = []
        def isConnected(self): return True
        def baseService(self): return ":1.42"
        def connect(self, _service, _path, _interface, _signal, receiver, _slot):
            holder["receiver"] = receiver
            return True
        def disconnect(self, *_args): pass
        def call(self, message, *_args):
            self.calls.append(message)
            return Message()

    bus = Bus()
    monkeypatch.setattr(QtCore, "QEventLoop", Loop)
    monkeypatch.setattr(QtCore, "QTimer", Timer)
    monkeypatch.setattr(QtDBus, "QDBusMessage", Message)
    monkeypatch.setattr(QtDBus.QDBusConnection, "sessionBus", lambda: bus)
    saved = screenshot.capture_screenshot(tmp_path / "Pictures", cancel_event=cancelled,
                                            parent_window="x11:abcd")

    assert saved.is_file()
    assert saved.read_bytes() == b"completed capture"
    assert bus.calls[0].arguments[0] == "x11:abcd"


def test_screenshot_recovers_gnome_file_during_portal_wait(monkeypatch, tmp_path):
    from PySide6 import QtCore, QtDBus
    holder = {"timers": [], "quit": False}
    expected = tmp_path / "Aurora" / "capture.png"

    class Loop:
        def quit(self): holder["quit"] = True
        def exec(self):
            recovery = next(timer for timer in holder["timers"] if timer.interval == 100)
            recovery.callback()
            recovery.callback()
            assert holder["quit"]

    class Timer:
        def __init__(self):
            self.interval = 0
            self.callback = lambda: None
            self.timeout = self
            holder["timers"].append(self)
        def connect(self, callback): self.callback = callback
        def setSingleShot(self, _value): pass
        def setInterval(self, value): self.interval = value
        def start(self, *_args): pass
        def stop(self): pass

    class Message:
        class MessageType:
            ErrorMessage = object()
        @staticmethod
        def createMethodCall(*_args): return Message()
        def setArguments(self, _args): pass
        def type(self): return object()
        def errorMessage(self): return ""

    class Bus:
        def isConnected(self): return True
        def baseService(self): return ":1.42"
        def connect(self, *_args): return True
        def disconnect(self, *_args): pass
        def call(self, *_args): return Message()

    monkeypatch.setattr(QtCore, "QEventLoop", Loop)
    monkeypatch.setattr(QtCore, "QTimer", Timer)
    monkeypatch.setattr(QtDBus, "QDBusMessage", Message)
    monkeypatch.setattr(QtDBus.QDBusConnection, "sessionBus", lambda: Bus())
    monkeypatch.setattr(screenshot, "_gnome_saved_screenshot_signature",
                        lambda *_args: ("Screenshot.png", 100, 123))
    monkeypatch.setattr(screenshot, "_recover_gnome_saved_screenshot",
                        lambda *_args: expected)

    saved = screenshot.capture_screenshot(tmp_path / "Pictures")

    assert saved == expected



def test_site_opening_is_separate_from_application_opening():
    assert integrations.site_url_from_request("Aurora, abra o site example.com") == "https://example.com"
    assert integrations.site_url_from_request("abre o link https://example.org/ajuda") == "https://example.org/ajuda"
    assert integrations.site_url_from_request("abra o Firefox") is None
    assert aurora.parse_local_command("Aurora, abra o site example.com") == (
        "open_url", {"url": "https://example.com"}
    )
    assert aurora.parse_local_command("abra o aplicativo Firefox")[0] == "open_application"
    assert aurora.parse_local_command("abra qzxvplm-token") is None
    assert aurora.parse_local_command("abra o site youtube") is None


def test_site_opening_rejects_non_web_schemes_and_ambiguous_names():
    assert integrations.site_url_from_request("abra site javascript:alert(1)") is None
    assert integrations.site_url_from_request("abra site youtube") is None
    assert integrations.site_url_from_request("abra o site http://[::1") is None


def test_flatpak_application_id_is_only_taken_from_exported_desktop_entries(tmp_path):
    exported = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    native = tmp_path / "applications/com.obsproject.Studio.desktop"
    app = {"file": exported, "name": "OBS Studio"}
    assert apps_module._flatpak_app_id(app) == "com.obsproject.Studio"
    assert apps_module._flatpak_app_id({"file": native}) is None


def test_flatpak_application_launches_by_id_and_reports_window_state_honestly(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    app = {"file": desktop_file, "name": "OBS Studio", "exec": "flatpak run com.obsproject.Studio",
           "class": "obs"}
    calls = []
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(apps_module.subprocess, "Popen", lambda command, **kwargs: calls.append((command, kwargs)))
    assert apps_module.launch_application("OBS Studio") == (
        "Iniciei o processo Flatpak de OBS Studio; ainda não confirmei se a janela apareceu."
    )
    assert calls[0][0] == ["/usr/bin/flatpak", "run", "com.obsproject.Studio"]
    assert calls[0][1]["start_new_session"] is True
    assert "QT_QPA_PLATFORM" not in calls[0][1]["env"]


def test_obs_background_launch_starts_minimized_to_tray(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    app = {"file": desktop_file, "name": "OBS Studio", "exec": "flatpak run com.obsproject.Studio",
           "class": "obs"}
    calls = []
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(apps_module.subprocess, "Popen", lambda command, **kwargs: calls.append((command, kwargs)))

    result = apps_module.launch_application("OBS Studio", background=True)

    assert result.startswith("Iniciei o processo Flatpak")
    assert calls[0][0] == ["/usr/bin/flatpak", "run", "com.obsproject.Studio", "--minimize-to-tray"]
    assert "QT_QPA_PLATFORM" not in calls[0][1]["env"]


def test_roblox_app_request_resolves_to_installed_sober_flatpak(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/org.vinegarhq.Sober.desktop"
    app = {"file": desktop_file, "name": "Sober", "exec": "flatpak run org.vinegarhq.Sober",
           "class": "org.vinegarhq.Sober"}
    monkeypatch.setattr(apps_module, "desktop_app_entries", lambda: iter([app]))
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(apps_module, "FLATPAK_LAUNCH_CONFIRM_TIMEOUT", 0)
    monkeypatch.setattr(apps_module.subprocess, "run", lambda *args, **kwargs: __import__("subprocess").CompletedProcess(args[0], 0, stdout="[]", stderr=""))
    calls = []
    monkeypatch.setattr(apps_module.subprocess, "Popen", lambda command, **_kwargs: calls.append(command))

    assert aurora.parse_local_command("abre Roblox") == (
        "open_application", {"command": "roblox"}
    )
    assert apps_module.find_desktop_app("Roblox") == app
    assert apps_module.launch_application("Roblox") == (
        "Iniciei o processo Flatpak de Sober; ainda não confirmei se a janela apareceu."
    )
    assert calls == [["/usr/bin/flatpak", "run", "org.vinegarhq.Sober"]]


def test_flatpak_launch_confirms_active_sober_instance(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/org.vinegarhq.Sober.desktop"
    app = {"file": desktop_file, "name": "Sober", "exec": "flatpak run org.vinegarhq.Sober",
           "class": "org.vinegarhq.Sober"}
    class RunningProcess:
        def poll(self): return None
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(apps_module.subprocess, "Popen", lambda *_args, **_kwargs: RunningProcess())
    monkeypatch.setattr(apps_module.subprocess, "run", lambda *args, **kwargs: __import__("subprocess").CompletedProcess(
        args[0], 0, stdout='[{"application":"org.vinegarhq.Sober","instance":"42"}]', stderr=""))
    assert apps_module.launch_application("Roblox") == "Abri Sober; o processo Flatpak está ativo."


def test_polite_app_commands_are_routed_without_llm_fallback(monkeypatch):
    import aurora_core.system.commands as commands
    monkeypatch.setattr(commands, "find_desktop_app", lambda _name: {"name": "Sober"})
    assert aurora.parse_local_command("você pode abrir Roblox?") == (
        "open_application", {"command": "roblox"})
    assert aurora.parse_local_command("pode fechar o Sober?") == (
        "close_application", {"application": "sober"})


def test_flatpak_application_process_start_failure_is_not_reported_as_success(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    app = {"file": desktop_file, "name": "OBS Studio", "exec": "flatpak run com.obsproject.Studio",
           "class": "obs"}
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(apps_module.subprocess, "Popen", lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(OSError("Flatpak unavailable"))
    ))

    result = apps_module.launch_application("OBS Studio")

    assert "Não consegui iniciar OBS Studio pelo Flatpak." in result
    assert "Abri OBS Studio" not in result


def test_flatpak_immediate_nonzero_exit_is_reported_as_failure(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    app = {"file": desktop_file, "name": "OBS Studio", "exec": "flatpak run com.obsproject.Studio",
           "class": "obs"}
    class FailedProcess:
        def poll(self): return 127
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(apps_module.subprocess, "Popen", lambda *_args, **_kwargs: FailedProcess())

    result = apps_module.launch_application("OBS Studio")

    assert result == "O Flatpak encerrou com erro ao tentar iniciar OBS Studio (código 127)."


def test_flatpak_successful_short_process_does_not_claim_a_visible_window(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    app = {"file": desktop_file, "name": "OBS Studio", "exec": "flatpak run com.obsproject.Studio",
           "class": "obs"}
    class AcceptedProcess:
        def poll(self): return 0
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(apps_module, "FLATPAK_LAUNCH_CONFIRM_TIMEOUT", 0)
    monkeypatch.setattr(apps_module.subprocess, "Popen", lambda *_args, **_kwargs: AcceptedProcess())

    result = apps_module.launch_application("OBS Studio")

    assert result == "O Flatpak aceitou abrir OBS Studio, mas não confirmei se a janela apareceu."


def test_close_flatpak_application_uses_instance_id(monkeypatch):
    app = {"file": "/var/lib/flatpak/exports/share/applications/com.obsproject.Studio.desktop",
           "name": "OBS Studio", "exec": "/usr/bin/flatpak run com.obsproject.Studio",
           "class": "obs"}
    calls = []
    listings = [
        [{"application": "com.obsproject.Studio", "instance": "12345"},
         {"application": "org.other.App", "instance": "99999"}],
        [],
    ]
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which",
                        lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[-1] == "--json":
            return type("Result", (), {"stdout": json.dumps(listings.pop(0))})()
        return type("Result", (), {"stdout": ""})()

    monkeypatch.setattr(apps_module.subprocess, "run", fake_run)
    assert "Fechei OBS Studio pelo Flatpak" in apps_module.close_application("OBS Studio")
    assert calls == [["/usr/bin/flatpak", "ps", "--json"],
                     ["/usr/bin/flatpak", "kill", "12345"],
                     ["/usr/bin/flatpak", "ps", "--json"]]


def test_flatpak_close_is_not_confirmed_while_instance_remains_active(monkeypatch):
    app = {"file": "/var/lib/flatpak/exports/share/applications/com.obsproject.Studio.desktop"}
    monkeypatch.setattr(apps_module.shutil, "which", lambda _name: "/usr/bin/flatpak")
    monkeypatch.setattr(apps_module, "FLATPAK_CLOSE_CONFIRM_TIMEOUT", 0)

    def fake_run(command, **_kwargs):
        if command[-1] == "--json":
            return type("Result", (), {"stdout": json.dumps([
                {"application": "com.obsproject.Studio", "instance": "12345"}
            ])})()
        return type("Result", (), {"stdout": ""})()

    monkeypatch.setattr(apps_module.subprocess, "run", fake_run)

    assert apps_module._close_flatpak_app(app) is False


def test_close_application_does_not_claim_wmctrl_failure(monkeypatch):
    monkeypatch.setattr(apps_module.shutil, "which",
                        lambda name: "/usr/bin/wmctrl" if name == "wmctrl" else None)

    def fail_close(command, **kwargs):
        if command[1:] == ["-l", "-x"]:
            return type("Result", (), {"stdout": "0x0001 0 0 host obs.OBS  OBS Studio"})()
        raise apps_module.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(apps_module.subprocess, "run", fail_close)
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: None)
    monkeypatch.setattr(apps_module, "process_names_for_app", lambda _name: (None, set()))
    result = apps_module.close_application("OBS Studio")
    assert "Enviei o comando" not in result
    assert "Não encontrei" in result


def test_close_application_reports_sigterm_permission_failure(monkeypatch, tmp_path):
    process = tmp_path / "123456"
    process.mkdir()
    (process / "comm").write_text("obs")
    app = {"file": tmp_path / "native.desktop", "name": "OBS Studio"}
    monkeypatch.setattr(apps_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(apps_module, "process_names_for_app", lambda _name: (app, {"obs"}))
    monkeypatch.setattr(apps_module.Path, "glob", lambda _self, _pattern: iter([process]))
    monkeypatch.setattr(apps_module.os, "readlink", lambda _path: "/usr/bin/obs")
    monkeypatch.setattr(apps_module.os, "kill", lambda *_args: (_ for _ in ()).throw(PermissionError()))
    result = apps_module.close_application("OBS Studio")
    assert "não consegui encerrar" in result.casefold()
    assert "Enviei o sinal" not in result


def test_window_manager_rejects_unknown_action_before_running_tools(monkeypatch):
    import aurora_core.system.windows as windows_module

    calls = []
    monkeypatch.setattr(windows_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(windows_module.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    assert windows_module.manage_window("do-nothing", "Editor") == "Ação de janela desconhecida."
    assert calls == []


def test_wayland_window_limit_is_explained_without_false_install_advice(monkeypatch):
    import aurora_core.system.windows as windows_module
    monkeypatch.setattr(windows_module.shutil, "which", lambda _name: None)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")
    result = windows_module.manage_window("maximize", "Editor")
    assert "X11/XWayland" in result
    assert "janelas Wayland nativas" in result


def test_window_manager_applies_action_once_to_active_window(monkeypatch):
    import aurora_core.system.windows as windows_module

    calls = []
    monkeypatch.setattr(windows_module.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **_kwargs):
        calls.append(command)
        stdout = "0x0001 0 0 host editor.Editor  Editor" if command[1:] == ["-l", "-x"] else "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0001"
        return type("Result", (), {"stdout": stdout})()

    monkeypatch.setattr(windows_module.subprocess, "run", fake_run)
    assert "concluído" in windows_module.manage_window("maximize")
    maximize_calls = [command for command in calls if command[1:3] == ["-ir", "0x0001"]]
    assert maximize_calls == [["/usr/bin/wmctrl", "-ir", "0x0001", "-b", "add,maximized_vert,maximized_horz"]]


def test_local_fast_router_handles_media_capture_and_obs_requests():
    assert aurora.parse_local_command("faça uma captura de tela")[0] == "take_screenshot"
    assert aurora.parse_local_command("comece a gravar minha tela") == (
        "obs_record", {"action": "start"}
    )
    assert aurora.parse_local_command("pare de gravar a tela") == (
        "obs_record", {"action": "stop"}
    )
    for request in ("Aurora, pare a gravação", "interrompa a gravação do OBS",
                    "parar a gravação no OBS"):
        assert aurora.parse_local_command(request) == ("obs_record", {"action": "stop"})


def test_hardware_fast_route_reaches_the_system_info_executor(monkeypatch):
    monkeypatch.setattr(system_actions, "system_hardware_summary", lambda: "hardware confirmado")
    monkeypatch.setattr(service_module, "audit_action", lambda *_args, **_kwargs: None)
    assert aurora.parse_local_command("mostre o hardware do meu PC") == ("system_info", {})
    for prompt in (
        "Quais são os componentes do meu PC?",
        "Quais componentes tem nesse computador?",
        "Me fala as peças do meu computador",
        "Quanto de memória RAM tem neste PC?",
        "O que de hardware está instalado no meu laptop?",
    ):
        assert aurora.parse_local_command(prompt) == ("system_info", {}), prompt
    assert aurora.parse_local_command("Como trocar a placa de vídeo do meu PC?") is None
    assert aurora.parse_local_command("Pesquise componentes para comprar para meu PC") is None
    assert service_module.AuroraService.execute_action(object(), "system_info", {}) == "hardware confirmado"


def test_screenshot_saves_unique_timestamped_files_without_overwriting(tmp_path):
    moment = datetime(2026, 10, 22, 10, 11, 12, 123456)
    source = tmp_path / "portal-shot.png"
    source.write_bytes(b"png-data")
    first = screenshot.save_screenshot_uri(source.as_uri(), tmp_path / "Pictures", moment)
    second = screenshot.save_screenshot_uri(source.as_uri(), tmp_path / "Pictures", moment)
    assert first.name == "Aurora_2026-10-22_10-11-12-123456.png"
    assert second.name == "Aurora_2026-10-22_10-11-12-123456_1.png"
    assert first.read_bytes() == second.read_bytes() == b"png-data"
    import stat
    assert stat.S_IMODE(first.stat().st_mode) == 0o600
    assert stat.S_IMODE(first.parent.stat().st_mode) == 0o700


def test_obs_cancelled_before_start_does_not_connect_or_launch(monkeypatch):
    cancelled = threading.Event()
    cancelled.set()
    monkeypatch.setattr(obs.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not connect")))

    assert "cancelada antes" in obs.obs_record("start", cancel_event=cancelled)


def test_screenshot_uri_must_be_local_file(tmp_path):
    try:
        screenshot.save_screenshot_uri("https://example.com/screen.png", tmp_path)
    except ValueError as exc:
        assert "arquivo local" in str(exc)
    else:
        raise AssertionError("remote screenshot URI must be rejected")


def test_screenshot_collision_never_deletes_existing_file(monkeypatch, tmp_path):
    source = tmp_path / "portal-shot.png"
    source.write_bytes(b"new image")
    existing_dir = tmp_path / "Pictures" / "Aurora"
    existing_dir.mkdir(parents=True)
    existing = existing_dir / "Aurora_2026-10-22_10-11-12-123456.png"
    existing.write_bytes(b"keep me")
    monkeypatch.setattr(screenshot, "unique_screenshot_path", lambda *_args: existing)
    try:
        screenshot.save_screenshot_uri(source.as_uri(), tmp_path / "Pictures")
    except FileExistsError:
        pass
    else:
        raise AssertionError("a name collision must not overwrite an existing capture")
    assert existing.read_bytes() == b"keep me"


def test_action_log_permissions_are_private(monkeypatch, tmp_path):
    import stat
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    obs._append_action_log("test_action", "returned")
    root = tmp_path / "aurora"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "actions.jsonl").stat().st_mode) == 0o600


def test_obs_is_loopback_only_and_never_claims_unconfirmed_success(monkeypatch):
    monkeypatch.setattr(obs, "_append_action_log", lambda *_args, **_kwargs: None)
    assert "próprio computador" in obs.obs_record("start", host="192.0.2.4")
    unavailable = obs.obs_record("start", host="127.0.0.1", port=1).casefold()
    assert "obs não respondeu" in unavailable
    assert "não enviei o comando" in unavailable


def test_obs_flatpak_disabled_server_gets_specific_setup_message(monkeypatch):
    monkeypatch.setattr(obs, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {
        "server_enabled": False, "auth_required": True,
        "server_port": 4455, "server_password": "unused-secret",
    })
    monkeypatch.setattr(obs.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))
    response = obs.obs_record("start")
    assert "WebSocket do OBS Studio Flatpak está desativado" in response
    assert "unused-secret" not in response


def test_obs_start_launches_flatpak_after_approved_websocket_connection_fails(monkeypatch):
    log = []
    monkeypatch.setattr(obs, "_append_action_log",
                        lambda *args, **kwargs: log.append((args, kwargs)))
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {
        "server_enabled": True, "auth_required": True,
        "server_port": 4455, "server_password": "",
    })
    monkeypatch.setattr(obs, "OBS_STARTUP_TIMEOUT", 0.01)
    monkeypatch.setattr(obs.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(obs, "_obs_latest_log_is_safe_mode", lambda: False)
    launches = []
    monkeypatch.setattr(
        "aurora_core.system.apps.launch_application",
        lambda name, **kwargs: launches.append((name, kwargs)) or "Solicitei a abertura de OBS Studio; o sistema aceitou o pedido.",
    )
    monkeypatch.setattr(obs.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))

    result = obs.obs_record("start")

    assert launches == [("OBS Studio", {"background": True})]
    assert "não iniciei a gravação" in result.casefold()
    assert log[-1][0][:2] == ("obs_record", "unavailable")
    assert log[-1][0][2]["phase"] == "startup"
    assert log[-1][0][2]["error_type"] == "TimeoutError"


def test_obs_safe_mode_timeout_never_claims_or_starts_recording(monkeypatch):
    log = []
    monkeypatch.setattr(obs, "_append_action_log",
                        lambda *args, **kwargs: log.append((args, kwargs)))
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {
        "server_enabled": True, "server_port": 4455,
    })
    monkeypatch.setattr(obs, "OBS_STARTUP_TIMEOUT", 0.01)
    monkeypatch.setattr(obs.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(obs, "_obs_latest_log_is_safe_mode", lambda: True)
    monkeypatch.setattr("aurora_core.system.apps.launch_application",
                        lambda *_args, **_kwargs: "Solicitei a abertura de OBS Studio.")
    monkeypatch.setattr(obs.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))

    result = obs.obs_record("start")

    assert "modo de segurança" in result.casefold()
    assert "não confirmei nem iniciei" in result.casefold()
    assert log[-1][0][2]["phase"] == "safe_mode"


def test_obs_stop_never_launches_obs_when_websocket_is_down(monkeypatch):
    monkeypatch.setattr(obs, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {
        "server_enabled": True, "server_port": 4455,
    })
    monkeypatch.setattr("aurora_core.system.apps.launch_application",
                        lambda _name: (_ for _ in ()).throw(AssertionError("must not launch")))
    monkeypatch.setattr(obs.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))
    monkeypatch.setattr(obs, "_close_obs_after_recording_stops",
                        lambda: (_ for _ in ()).throw(AssertionError("must not close OBS")))

    result = obs.obs_record("stop")

    assert "não enviei o comando" in result.casefold()


def test_obs_closes_flatpak_only_after_stop_is_confirmed(monkeypatch):
    import aurora_core.system.apps as apps

    app = {"file": "/var/lib/flatpak/exports/share/applications/com.obsproject.Studio.desktop"}
    monkeypatch.setattr(apps, "find_desktop_app", lambda _name: app)
    closed = []
    monkeypatch.setattr(apps, "_close_flatpak_app", lambda value: closed.append(value) or True)

    assert obs._close_obs_after_recording_stops()
    assert closed == [app]


def test_obs_confirmed_stop_closes_obs_after_websocket_context(monkeypatch):
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {})
    monkeypatch.setattr(obs.secrets, "compare_digest", lambda *_args: True)
    request_ids = iter(("stop-request", "status-request"))
    monkeypatch.setattr(obs.secrets, "token_hex", lambda _size: next(request_ids))
    sent = []
    closed = []

    class FakeSocket:
        def __enter__(self): return self
        def __exit__(self, *_args): closed.append("socket-exit"); return False
        def settimeout(self, _timeout): pass
        def sendall(self, _data): pass
        def recv(self, _count):
            return (b"HTTP/1.1 101 Switching Protocols\r\n"
                    b"Sec-WebSocket-Accept: valid\r\n\r\n")

    monkeypatch.setattr(obs.socket, "create_connection", lambda *_args, **_kwargs: FakeSocket())
    monkeypatch.setattr(obs, "_ws_send", lambda _stream, payload, _deadline=None: sent.append(payload))

    def receive(_stream, _deadline=None):
        if not sent:
            return {"op": 0, "d": {"rpcVersion": 1}}
        if sent[-1].get("op") == 1:
            return {"op": 2, "d": {"negotiatedRpcVersion": 1}}
        request = sent[-1]["d"]
        if request["requestType"] == "StopRecord":
            return {"op": 7, "d": {"requestId": "stop-request",
                    "requestStatus": {"result": True}}}
        return {"op": 7, "d": {"requestId": "status-request",
                "requestStatus": {"result": True}, "responseData": {"outputActive": False}}}

    monkeypatch.setattr(obs, "_ws_receive", receive)
    def close_obs():
        assert closed == ["socket-exit"]
        closed.append("obs-close")
        return True
    monkeypatch.setattr(obs, "_close_obs_after_recording_stops", close_obs)

    result = obs.obs_record("stop", port=4455)

    assert result == "Gravação parada e OBS encerrado."
    assert closed == ["socket-exit", "obs-close"]


def test_obs_websocket_eof_during_handshake_returns_instead_of_spinning(monkeypatch):
    monkeypatch.setattr(obs, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {})

    class ClosedSocket:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def settimeout(self, _timeout): pass
        def sendall(self, _data): pass
        def recv(self, _count): return b""

    monkeypatch.setattr(obs.socket, "create_connection", lambda *_args, **_kwargs: ClosedSocket())
    outcome = obs.obs_record("start")
    assert "não enviei o comando" in outcome.casefold()


def test_obs_lost_reply_after_request_warns_to_check_state_before_retry(monkeypatch):
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {})
    actions = []
    monkeypatch.setattr(obs, "_append_action_log",
                        lambda _name, outcome, details=None: actions.append((outcome, details)))
    sent = []

    class QuietSocket:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def settimeout(self, _timeout): pass
        def sendall(self, data): sent.append(data)
        def recv(self, _count):
            return (b"HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: valid\r\n\r\n")

    monkeypatch.setattr(obs.socket, "create_connection", lambda *_args, **_kwargs: QuietSocket())
    monkeypatch.setattr(obs.secrets, "compare_digest", lambda *_args: True)
    received = iter(({"op": 0, "d": {"rpcVersion": 1}}, {"op": 2, "d": {"negotiatedRpcVersion": 1}}))

    def receive(*_args, **_kwargs):
        try: return next(received)
        except StopIteration: raise ConnectionError("reply lost")

    monkeypatch.setattr(obs, "_ws_receive", receive)
    outcome = obs.obs_record("start")

    assert "perdi a confirmação" in outcome.casefold()
    assert "antes de tentar de novo" in outcome.casefold()
    assert actions == [("unavailable", {"action": "start", "phase": "request",
                                        "error_type": "ConnectionError"})]
    assert len(sent) == 3  # HTTP upgrade, Identify, then StartRecord request.


def test_obs_partial_rpc_send_is_reported_as_unknown_not_never_sent(monkeypatch):
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {})
    actions = []
    monkeypatch.setattr(obs, "_append_action_log",
                        lambda _name, outcome, details=None: actions.append((outcome, details)))

    class BrokenSocket:
        def __init__(self): self.sends = 0
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def settimeout(self, _timeout): pass
        def sendall(self, _data):
            self.sends += 1
            if self.sends == 3: raise BrokenPipeError("connection lost during RPC frame")
        def recv(self, _count):
            return b"HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: valid\r\n\r\n"

    monkeypatch.setattr(obs.socket, "create_connection", lambda *_args, **_kwargs: BrokenSocket())
    monkeypatch.setattr(obs.secrets, "compare_digest", lambda *_args: True)
    received = iter(({"op": 0, "d": {"rpcVersion": 1}}, {"op": 2, "d": {"negotiatedRpcVersion": 1}}))
    monkeypatch.setattr(obs, "_ws_receive", lambda *_a, **_k: next(received))

    outcome = obs.obs_record("start")

    assert "perdi a confirmação" in outcome.casefold()
    assert "não enviei o comando" not in outcome.casefold()
    assert actions == [("unavailable", {"action": "start", "phase": "request",
                                        "error_type": "BrokenPipeError"})]


def test_obs_websocket_frame_read_stops_at_total_deadline():
    class UnreadSocket:
        def __init__(self): self.reads = 0
        def settimeout(self, _timeout): pass
        def recv(self, _count):
            self.reads += 1
            return b"\x81\x00"

    stream = UnreadSocket()
    try:
        obs._ws_receive(stream, obs.time.monotonic() - 1)
    except TimeoutError:
        pass
    else:
        raise AssertionError("a leitura devia respeitar o prazo total expirado")
    assert stream.reads == 0


def test_obs_flatpak_settings_with_non_object_json_are_ignored(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(obs, "_flatpak_obs_config_path", lambda: config)
    assert obs._flatpak_obs_settings() == {}


@pytest.mark.parametrize(("active_states", "should_confirm"), [
    ([True], True), ([False], False), ([False, True], True),
])
def test_obs_websocket_authenticates_and_verifies_record_state(
        monkeypatch, active_states, should_confirm):
    monkeypatch.setattr(obs, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(obs, "OBS_VERIFY_TIMEOUT", 0.35)
    monkeypatch.setattr(obs, "OBS_VERIFY_INTERVAL", 0.01)
    monkeypatch.setattr(obs, "_flatpak_obs_settings", lambda: {
        "server_enabled": True, "auth_required": True,
        "server_port": 4455, "server_password": "secret",
    })
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    errors = []
    requests = []
    stage = ["accept"]

    def send_frame(connection, payload):
        data = json.dumps(payload, separators=(",", ":")).encode()
        size = len(data)
        head = bytes([0x81, size]) if size < 126 else bytes([0x81, 126]) + size.to_bytes(2, "big")
        connection.sendall(head + data)

    def server():
        try:
            connection, _ = listener.accept()
            with connection:
                headers = bytearray()
                while b"\r\n\r\n" not in headers:
                    headers.extend(connection.recv(1))
                key = next(line.split(b":", 1)[1].strip().decode()
                           for line in headers.split(b"\r\n")
                           if line.lower().startswith(b"sec-websocket-key:"))
                accept = base64.b64encode(hashlib.sha1(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
                connection.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                                    "Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept +
                                    "\r\n\r\n").encode())
                stage[0] = "identify"
                salt, challenge, password = "salt", "challenge", "secret"
                send_frame(connection, {"op": 0, "d": {"rpcVersion": 1,
                    "authentication": {"salt": salt, "challenge": challenge}}})
                identify = obs._ws_receive(connection)
                secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
                expected = base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()
                assert identify["op"] == 1
                assert identify["d"]["authentication"] == expected
                send_frame(connection, {"op": 2, "d": {"negotiatedRpcVersion": 1}})
                stage[0] = "request"
                request = obs._ws_receive(connection)
                requests.append(request)
                send_frame(connection, {"op": 7, "d": {"requestType": "StartRecord",
                    "requestId": request["d"]["requestId"],
                    "requestStatus": {"result": True, "code": 100}}})
                state_index = 0
                while True:
                    try:
                        status = obs._ws_receive(connection)
                    except ConnectionError:
                        break
                    requests.append(status)
                    active = active_states[min(state_index, len(active_states) - 1)]
                    state_index += 1
                    send_frame(connection, {"op": 7, "d": {"requestType": "GetRecordStatus",
                        "requestId": status["d"]["requestId"],
                        "requestStatus": {"result": True, "code": 100},
                        "responseData": {"outputActive": active}}})
                    if active:
                        break
        except Exception as exc:
            errors.append((stage[0], repr(exc)))
        finally:
            listener.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    outcome = obs.obs_record("start", port=port)
    thread.join(timeout=3)
    assert not thread.is_alive()
    if should_confirm:
        assert "iniciada" in outcome, (outcome, errors)
        assert "em segundo plano" in outcome
        assert "pare a gravação" in outcome
    else:
        assert "não confirmei" in outcome.casefold()
    assert not errors
    assert requests[0]["d"]["requestType"] == "StartRecord"
    assert all(request["d"]["requestType"] == "GetRecordStatus"
               for request in requests[1:])
    if active_states == [False, True]:
        assert len(requests) == 3  # StartRecord, stale status, then active status.

