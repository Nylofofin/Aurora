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


def test_screenshot_uri_must_be_local_file(tmp_path):
    try:
        integrations.save_screenshot_uri("https://example.com/screen.png", tmp_path)
    except ValueError as exc:
        assert "arquivo local" in str(exc)
    else:
        raise AssertionError("remote screenshot URI must be rejected")


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
    assert "não consegui confirmar" in integrations.obs_record("start", host="127.0.0.1", port=1).casefold()


def test_obs_websocket_authenticates_and_confirms_record_request(monkeypatch):
    monkeypatch.setattr(integrations, "_append_action_log", lambda *_args, **_kwargs: None)
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
    outcome = integrations.obs_record("start", password="secret", port=port)
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert "iniciada" in outcome, (outcome, errors)
    assert not errors
    assert requests[0]["d"]["requestType"] == "StartRecord"

