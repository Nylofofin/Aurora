from datetime import datetime
import base64
import hashlib
import json
import socket
import threading

import aurora
import aurora_integrations as integrations
import aurora_core.service as service_module
import aurora_core.system.actions as system_actions
import aurora_core.system.apps as apps_module


def test_screenshot_portal_request_path_preserves_sender_prefix():
    assert integrations._portal_request_object_path(":1.42", "aurora_token") == (
        "/org/freedesktop/portal/desktop/request/_1_42/aurora_token"
    )


def test_screenshot_portal_uses_qt_encoded_slot_signature():
    from PySide6.QtCore import QObject, Slot

    class Response(QObject):
        @Slot(integrations._portal_response_code_type(), "QVariantMap")
        def receive(self, _code, _data):
            pass

    assert integrations._portal_response_slot().startswith("1receive(")
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
        integrations.capture_screenshot(tmp_path, cancel_event=cancelled)
    except RuntimeError as exc:
        assert "cancelada" in str(exc)
    else:
        raise AssertionError("cancelled screenshots must not be saved")
    assert calls[-1][1:] == ("org.freedesktop.portal.Request", "Close")
    assert not (tmp_path / "Aurora").exists()


def test_site_opening_is_separate_from_application_opening():
    assert integrations.site_url_from_request("Aurora, abra o site example.com") == "https://example.com"
    assert integrations.site_url_from_request("abre o link https://example.org/ajuda") == "https://example.org/ajuda"
    assert integrations.site_url_from_request("abra o Firefox") is None
    assert aurora.parse_local_command("Aurora, abra o site example.com") == (
        "open_url", {"url": "https://example.com"}
    )
    assert aurora.parse_local_command("abra o aplicativo Firefox")[0] == "open_application"
    assert aurora.parse_local_command("abra qzxvplm-token") == (
        "clarify_open_target", {"target": "qzxvplm-token"}
    )
    assert aurora.parse_local_command("abra o site youtube") == (
        "clarify_open_target", {"target": "site youtube"}
    )


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


def test_flatpak_application_launches_through_exported_desktop_entry(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    app = {"file": desktop_file, "name": "OBS Studio", "exec": "flatpak run com.obsproject.Studio",
           "class": "obs"}
    calls = []
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/gio" if name == "gio" else None)
    monkeypatch.setattr(apps_module.subprocess, "run", lambda command, **_kwargs: (
        calls.append(command) or type("Result", (), {"returncode": 0, "stderr": ""})()
    ))
    assert apps_module.launch_application("OBS Studio") == "Solicitei a abertura de OBS Studio; o sistema aceitou o pedido."
    assert calls == [["/usr/bin/gio", "launch", str(desktop_file)]]


def test_roblox_app_request_resolves_to_installed_sober_flatpak(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/org.vinegarhq.Sober.desktop"
    app = {"file": desktop_file, "name": "Sober", "exec": "flatpak run org.vinegarhq.Sober",
           "class": "org.vinegarhq.Sober"}
    monkeypatch.setattr(apps_module, "desktop_app_entries", lambda: iter([app]))
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/gio" if name == "gio" else None)
    calls = []
    monkeypatch.setattr(apps_module.subprocess, "run", lambda command, **_kwargs: (
        calls.append(command) or type("Result", (), {"returncode": 0, "stderr": ""})()
    ))

    assert aurora.parse_local_command("abre Roblox") == (
        "open_application", {"command": "roblox"}
    )
    assert apps_module.find_desktop_app("Roblox") == app
    assert apps_module.launch_application("Roblox") == "Solicitei a abertura de Sober; o sistema aceitou o pedido."
    assert calls == [["/usr/bin/gio", "launch", str(desktop_file)]]


def test_polite_app_commands_are_routed_without_llm_fallback(monkeypatch):
    import aurora_core.system.commands as commands
    monkeypatch.setattr(commands, "find_desktop_app", lambda _name: {"name": "Sober"})
    assert aurora.parse_local_command("você pode abrir Roblox?") == (
        "open_application", {"command": "roblox"})
    assert aurora.parse_local_command("pode fechar o Sober?") == (
        "close_application", {"application": "sober"})


def test_flatpak_application_launch_failure_is_not_reported_as_success(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    app = {"file": desktop_file, "name": "OBS Studio", "exec": "flatpak run com.obsproject.Studio",
           "class": "obs"}
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/gio" if name == "gio" else None)
    monkeypatch.setattr(apps_module.subprocess, "run", lambda *_args, **_kwargs: (
        type("Result", (), {"returncode": 1, "stderr": "Application launch failed"})()
    ))

    result = apps_module.launch_application("OBS Studio")

    assert "Não consegui abrir OBS Studio" in result
    assert "Abri OBS Studio" not in result


def test_flatpak_application_launch_timeout_does_not_claim_success(monkeypatch, tmp_path):
    desktop_file = tmp_path / "flatpak/exports/share/applications/com.obsproject.Studio.desktop"
    app = {"file": desktop_file, "name": "OBS Studio", "exec": "flatpak run com.obsproject.Studio",
           "class": "obs"}
    monkeypatch.setattr(apps_module, "find_desktop_app", lambda _name: app)
    monkeypatch.setattr(apps_module.shutil, "which", lambda name: "/usr/bin/gio" if name == "gio" else None)
    monkeypatch.setattr(apps_module.subprocess, "run", lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(apps_module.subprocess.TimeoutExpired("gio launch", 4))
    ))

    result = apps_module.launch_application("OBS Studio")

    assert "não confirmei se o aplicativo abriu" in result
    assert "Abri OBS Studio" not in result


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
    assert aurora.parse_local_command("toca a música Dreams") == (
        "spotify_play", {"query": "dreams"}
    )
    assert aurora.parse_local_command("conectar Spotify")[0] == "spotify_authorize"
    assert aurora.parse_local_command("faça uma captura de tela")[0] == "take_screenshot"
    assert aurora.parse_local_command("comece a gravar minha tela") == (
        "obs_record", {"action": "start"}
    )
    assert aurora.parse_local_command("pare de gravar a tela") == (
        "obs_record", {"action": "stop"}
    )


def test_hardware_fast_route_reaches_the_system_info_executor(monkeypatch):
    monkeypatch.setattr(system_actions, "system_hardware_summary", lambda: "hardware confirmado")
    monkeypatch.setattr(service_module, "audit_action", lambda *_args, **_kwargs: None)
    assert aurora.parse_local_command("mostre o hardware do meu PC") == ("system_info", {})
    assert service_module.AuroraService.execute_action(object(), "system_info", {}) == "hardware confirmado"


def test_screenshot_saves_unique_timestamped_files_without_overwriting(tmp_path):
    moment = datetime(2026, 10, 22, 10, 11, 12, 123456)
    source = tmp_path / "portal-shot.png"
    source.write_bytes(b"png-data")
    first = integrations.save_screenshot_uri(source.as_uri(), tmp_path / "Pictures", moment)
    second = integrations.save_screenshot_uri(source.as_uri(), tmp_path / "Pictures", moment)
    assert first.name == "Aurora_2026-10-22_10-11-12-123456.png"
    assert second.name == "Aurora_2026-10-22_10-11-12-123456_1.png"
    assert first.read_bytes() == second.read_bytes() == b"png-data"
    import stat
    assert stat.S_IMODE(first.stat().st_mode) == 0o600
    assert stat.S_IMODE(first.parent.stat().st_mode) == 0o700


def test_obs_cancelled_before_start_does_not_connect_or_launch(monkeypatch):
    cancelled = threading.Event()
    cancelled.set()
    monkeypatch.setattr(integrations.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not connect")))

    assert "cancelada antes" in integrations.obs_record("start", cancel_event=cancelled)


def test_screenshot_uri_must_be_local_file(tmp_path):
    try:
        integrations.save_screenshot_uri("https://example.com/screen.png", tmp_path)
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
    monkeypatch.setattr(integrations, "unique_screenshot_path", lambda *_args: existing)
    try:
        integrations.save_screenshot_uri(source.as_uri(), tmp_path / "Pictures")
    except FileExistsError:
        pass
    else:
        raise AssertionError("a name collision must not overwrite an existing capture")
    assert existing.read_bytes() == b"keep me"


def test_action_log_permissions_are_private(monkeypatch, tmp_path):
    import stat
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    integrations._append_action_log("test_action", "returned")
    root = tmp_path / "aurora"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "actions.jsonl").stat().st_mode) == 0o600


def test_spotify_pkce_challenge_is_url_safe():
    challenge = integrations.spotify_code_challenge("A" * 64)
    assert len(challenge) == 43
    assert "+" not in challenge and "/" not in challenge and "=" not in challenge


def test_spotify_reports_missing_local_configuration_without_network(monkeypatch):
    monkeypatch.setattr(integrations, "_append_action_log", lambda *_args, **_kwargs: None)
    assert "spotify_client_id" in integrations.start_spotify_authorization("", lambda _url: True)
    assert "não conectado" in integrations.play_spotify_track("Faixa", "").casefold()


def test_obs_is_loopback_only_and_never_claims_unconfirmed_success(monkeypatch):
    monkeypatch.setattr(integrations, "_append_action_log", lambda *_args, **_kwargs: None)
    assert "próprio computador" in integrations.obs_record("start", host="192.0.2.4")
    unavailable = integrations.obs_record("start", host="127.0.0.1", port=1).casefold()
    assert "obs não respondeu" in unavailable
    assert "não enviei o comando" in unavailable


def test_obs_flatpak_disabled_server_gets_specific_setup_message(monkeypatch):
    monkeypatch.setattr(integrations, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integrations, "_flatpak_obs_settings", lambda: {
        "server_enabled": False, "auth_required": True,
        "server_port": 4455, "server_password": "unused-secret",
    })
    monkeypatch.setattr(integrations.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))
    response = integrations.obs_record("start")
    assert "WebSocket do OBS Studio Flatpak está desativado" in response
    assert "unused-secret" not in response


def test_obs_start_launches_flatpak_after_approved_websocket_connection_fails(monkeypatch):
    monkeypatch.setattr(integrations, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integrations, "_flatpak_obs_settings", lambda: {
        "server_enabled": True, "auth_required": True,
        "server_port": 4455, "server_password": "",
    })
    monkeypatch.setattr(integrations, "OBS_STARTUP_TIMEOUT", 0.01)
    monkeypatch.setattr(integrations.time, "sleep", lambda _seconds: None)
    launches = []
    monkeypatch.setattr(
        "aurora_core.system.apps.launch_application",
        lambda name: launches.append(name) or "Solicitei a abertura de OBS Studio; o sistema aceitou o pedido.",
    )
    monkeypatch.setattr(integrations.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))

    result = integrations.obs_record("start")

    assert launches == ["OBS Studio"]
    assert "não iniciei a gravação" in result.casefold()


def test_obs_stop_never_launches_obs_when_websocket_is_down(monkeypatch):
    monkeypatch.setattr(integrations, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integrations, "_flatpak_obs_settings", lambda: {
        "server_enabled": True, "server_port": 4455,
    })
    monkeypatch.setattr("aurora_core.system.apps.launch_application",
                        lambda _name: (_ for _ in ()).throw(AssertionError("must not launch")))
    monkeypatch.setattr(integrations.socket, "create_connection",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))

    result = integrations.obs_record("stop")

    assert "não enviei o comando" in result.casefold()


def test_obs_websocket_eof_during_handshake_returns_instead_of_spinning(monkeypatch):
    monkeypatch.setattr(integrations, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integrations, "_flatpak_obs_settings", lambda: {})

    class ClosedSocket:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def settimeout(self, _timeout): pass
        def sendall(self, _data): pass
        def recv(self, _count): return b""

    monkeypatch.setattr(integrations.socket, "create_connection", lambda *_args, **_kwargs: ClosedSocket())
    outcome = integrations.obs_record("start")
    assert "não enviei o comando" in outcome.casefold()


def test_obs_lost_reply_after_request_warns_to_check_state_before_retry(monkeypatch):
    monkeypatch.setattr(integrations, "_flatpak_obs_settings", lambda: {})
    actions = []
    monkeypatch.setattr(integrations, "_append_action_log",
                        lambda _name, outcome, details=None: actions.append((outcome, details)))
    sent = []

    class QuietSocket:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def settimeout(self, _timeout): pass
        def sendall(self, data): sent.append(data)
        def recv(self, _count):
            return (b"HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: valid\r\n\r\n")

    monkeypatch.setattr(integrations.socket, "create_connection", lambda *_args, **_kwargs: QuietSocket())
    monkeypatch.setattr(integrations.secrets, "compare_digest", lambda *_args: True)
    received = iter(({"op": 0, "d": {"rpcVersion": 1}}, {"op": 2, "d": {"negotiatedRpcVersion": 1}}))

    def receive(*_args, **_kwargs):
        try: return next(received)
        except StopIteration: raise ConnectionError("reply lost")

    monkeypatch.setattr(integrations, "_ws_receive", receive)
    outcome = integrations.obs_record("start")

    assert "perdi a confirmação" in outcome.casefold()
    assert "antes de tentar de novo" in outcome.casefold()
    assert actions == [("unavailable", {"action": "start", "phase": "confirmation"})]
    assert len(sent) == 3  # HTTP upgrade, Identify, then StartRecord request.


def test_obs_websocket_frame_read_stops_at_total_deadline():
    class UnreadSocket:
        def __init__(self): self.reads = 0
        def settimeout(self, _timeout): pass
        def recv(self, _count):
            self.reads += 1
            return b"\x81\x00"

    stream = UnreadSocket()
    try:
        integrations._ws_receive(stream, integrations.time.monotonic() - 1)
    except TimeoutError:
        pass
    else:
        raise AssertionError("a leitura devia respeitar o prazo total expirado")
    assert stream.reads == 0


def test_obs_flatpak_settings_with_non_object_json_are_ignored(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(integrations, "_flatpak_obs_config_path", lambda: config)
    assert integrations._flatpak_obs_settings() == {}


def test_obs_websocket_authenticates_and_confirms_record_request(monkeypatch):
    monkeypatch.setattr(integrations, "_append_action_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integrations, "_flatpak_obs_settings", lambda: {
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
                identify = integrations._ws_receive(connection)
                secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
                expected = base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()
                assert identify["op"] == 1
                assert identify["d"]["authentication"] == expected
                send_frame(connection, {"op": 2, "d": {"negotiatedRpcVersion": 1}})
                stage[0] = "request"
                request = integrations._ws_receive(connection)
                requests.append(request)
                send_frame(connection, {"op": 7, "d": {"requestType": "StartRecord",
                    "requestId": request["d"]["requestId"],
                    "requestStatus": {"result": True, "code": 100}}})
        except Exception as exc:
            errors.append((stage[0], repr(exc)))
        finally:
            listener.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    outcome = integrations.obs_record("start", port=port)
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert "iniciada" in outcome, (outcome, errors)
    assert not errors
    assert requests[0]["d"]["requestType"] == "StartRecord"

