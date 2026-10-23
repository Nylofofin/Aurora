"""OBS Studio WebSocket integration, isolated from the compatibility facade."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import shutil
import socket
import threading
import time
from pathlib import Path

from .action_log import _append_action_log

OBS_REQUEST_TIMEOUT = 3.0
OBS_VERIFY_TIMEOUT = 1.5
OBS_VERIFY_INTERVAL = 0.12


OBS_STARTUP_TIMEOUT = 15.0


def _close_obs_after_recording_stops() -> bool:
    """Exit OBS only after StopRecord has been confirmed inactive."""
    from aurora_core.system.apps import (
        _close_flatpak_app, _flatpak_app_id, close_application, find_desktop_app,
    )

    app = find_desktop_app("OBS Studio")
    if _flatpak_app_id(app) == "com.obsproject.Studio":
        # OBS is configured to minimize to tray. Closing its window can leave
        # the Flatpak process alive, so terminate the exact app only after
        # GetRecordStatus has confirmed outputActive=False.
        return _close_flatpak_app(app)
    return close_application("OBS Studio").startswith("Fechei ")


def _flatpak_obs_config_path() -> Path:
    return (Path.home() / ".var/app/com.obsproject.Studio/config/obs-studio/"
            "plugin_config/obs-websocket/config.json")


def _flatpak_obs_settings() -> dict:
    """Read only the local OBS WebSocket settings needed by this integration."""
    path = _flatpak_obs_config_path()
    try:
        if path.stat().st_size > 64_000:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        port = int(data.get("server_port", 4455))
        if not 1 <= port <= 65535:
            return {}
        return {"server_enabled": bool(data.get("server_enabled", False)),
                "auth_required": bool(data.get("auth_required", True)),
                "server_port": port,
                "server_password": str(data.get("server_password", ""))}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _obs_latest_log_is_safe_mode() -> bool:
    """Detect OBS safe-mode startup, where obs-websocket is deliberately disabled."""
    log_dir = Path.home() / ".var/app/com.obsproject.Studio/config/obs-studio/logs"
    try:
        newest = max(log_dir.glob("*.txt"), key=lambda path: path.stat().st_mtime)
        with newest.open("rb") as log:
            log.seek(max(0, newest.stat().st_size - 128_000))
            tail = log.read().decode("utf-8", errors="replace").casefold()
        return "safe mode enabled" in tail and "skipping module 'obs-websocket'" in tail
    except (OSError, ValueError):
        return False


def _set_request_timeout(stream: socket.socket, deadline: float | None) -> None:
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("O OBS excedeu o tempo total de resposta.")
        stream.settimeout(remaining)


def _read_exact(stream: socket.socket, count: int, deadline: float | None = None) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        _set_request_timeout(stream, deadline)
        part = stream.recv(count - len(chunks))
        if not part:
            raise ConnectionError("OBS encerrou a conexão WebSocket.")
        chunks.extend(part)
    return bytes(chunks)


def _ws_send(stream: socket.socket, payload: dict, deadline: float | None = None) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    mask = secrets.token_bytes(4)
    length = len(data)
    header = bytearray([0x81])
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))
    header.extend(mask)
    header.extend(byte ^ mask[index % 4] for index, byte in enumerate(data))
    _set_request_timeout(stream, deadline)
    stream.sendall(header)


def _ws_receive(stream: socket.socket, deadline: float | None = None) -> dict:
    while True:
        first, second = _read_exact(stream, 2, deadline)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(_read_exact(stream, 2, deadline), "big")
        elif length == 127:
            length = int.from_bytes(_read_exact(stream, 8, deadline), "big")
        if length > 2_000_000:
            raise ValueError("Mensagem WebSocket excede o limite local.")
        mask = _read_exact(stream, 4, deadline) if second & 0x80 else b""
        data = _read_exact(stream, length, deadline)
        if mask:
            data = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        if opcode == 0x8:
            raise ConnectionError("OBS fechou a sessão WebSocket.")
        if opcode == 0x9:
            pong = bytearray([0x8A, 0x80 | len(data)])
            mask_out = secrets.token_bytes(4)
            pong.extend(mask_out)
            pong.extend(byte ^ mask_out[index % 4] for index, byte in enumerate(data))
            _set_request_timeout(stream, deadline)
            stream.sendall(pong)
            continue
        if opcode != 0x1:
            continue
        return json.loads(data.decode("utf-8"))


def obs_record(action: str, password: str = "", host: str = "127.0.0.1", port: int = 4455,
               cancel_event: threading.Event | None = None) -> str:
    """Call only OBS on loopback; speak success only after its RPC confirms."""
    if host not in ("127.0.0.1", "::1", "localhost"):
        return "Por segurança, o OBS WebSocket precisa estar no próprio computador."
    action = str(action).casefold()
    request_type = {"start": "StartRecord", "stop": "StopRecord"}.get(action)
    if not request_type:
        return "Ação de gravação desconhecida."
    try:
        port = int(port)
    except (TypeError, ValueError):
        return "A porta do WebSocket do OBS é inválida."
    if not 1 <= port <= 65535:
        return "A porta do WebSocket do OBS é inválida."
    obs_settings = _flatpak_obs_settings()
    if port == 4455 and obs_settings.get("server_port"):
        port = obs_settings["server_port"]
    password = password or obs_settings.get("server_password", "")
    request_attempted = False
    phase = "connect"
    if cancel_event and cancel_event.is_set():
        return "A gravação foi cancelada antes de enviar qualquer comando ao OBS."
    try:
        try:
            stream = socket.create_connection((host, int(port)), timeout=OBS_REQUEST_TIMEOUT)
        except OSError:
            if cancel_event and cancel_event.is_set():
                return "A gravação foi cancelada antes de abrir o OBS."
            # Start OBS only after the user approved StartRecord. Never launch
            # it for a stop request or when its local WebSocket is disabled.
            configured_port = obs_settings.get("server_port")
            if not (action == "start" and obs_settings.get("server_enabled") is True
                    and configured_port == int(port)):
                raise
            from aurora_core.system.apps import launch_application
            launch_result = launch_application("OBS Studio", background=True)
            if not launch_result.startswith("Solicitei a abertura"):
                _append_action_log("obs_record", "unavailable", {"action": action,
                                    "phase": "launch", "error_type": "LaunchRejected"})
                return f"Não consegui iniciar o OBS: {launch_result}"
            startup_deadline = time.monotonic() + OBS_STARTUP_TIMEOUT
            stream = None
            while time.monotonic() < startup_deadline:
                if cancel_event and cancel_event.is_set():
                    return "A gravação foi cancelada antes de enviar qualquer comando ao OBS."
                try:
                    stream = socket.create_connection((host, int(port)), timeout=0.5)
                    break
                except OSError:
                    time.sleep(0.2)
            if stream is None:
                if _obs_latest_log_is_safe_mode():
                    _append_action_log("obs_record", "unavailable", {"action": action,
                                        "phase": "safe_mode", "error_type": "WebSocketDisabled"})
                    return ("O OBS abriu em modo de segurança, que desativa o WebSocket. "
                            "Não confirmei nem iniciei a gravação.")
                _append_action_log("obs_record", "unavailable", {"action": action,
                                    "phase": "startup", "error_type": "TimeoutError"})
                return ("Abri o OBS, mas o WebSocket não ficou disponível. Confira se o servidor "
                        f"está ativo na porta {port}; não iniciei a gravação.")
        # Startup has its own bounded wait. Start the short protocol deadline
        # only after a socket is connected, otherwise launching OBS can consume
        # the entire handshake budget before OBS is ready.
        deadline = time.monotonic() + OBS_REQUEST_TIMEOUT
        with stream:
            if cancel_event and cancel_event.is_set():
                return "A gravação foi cancelada antes de enviar qualquer comando ao OBS."
            phase = "handshake"
            _set_request_timeout(stream, deadline)
            key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
            stream.sendall(("GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\n"
                            "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                            f"Sec-WebSocket-Key: {key}\r\n\r\n").encode("ascii"))
            response = bytearray()
            while b"\r\n\r\n" not in response and len(response) < 16_384:
                _set_request_timeout(stream, deadline)
                part = stream.recv(1)
                if not part:
                    raise ConnectionError("O OBS encerrou a conexão durante o handshake WebSocket.")
                response.extend(part)
            headers = bytes(response).split(b"\r\n")
            if b" 101 " not in headers[0]:
                raise ConnectionError("O OBS não aceitou o WebSocket local.")
            accept = next((line.split(b":", 1)[1].strip().decode("ascii")
                           for line in headers if line.lower().startswith(b"sec-websocket-accept:")), "")
            expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            if not secrets.compare_digest(accept, expected):
                raise ConnectionError("A resposta do WebSocket local não passou na validação.")
            phase = "hello"
            hello = _ws_receive(stream, deadline)
            if hello.get("op") != 0:
                raise ConnectionError("O OBS respondeu com um protocolo inesperado.")
            data = hello.get("d", {})
            identify = {"rpcVersion": 1}
            auth = data.get("authentication")
            if auth:
                if not password:
                    raise RuntimeError("O OBS exige senha. Configure AURORA_OBS_PASSWORD no serviço, sem compartilhá-la no chat.")
                secret = base64.b64encode(hashlib.sha256((password + auth["salt"]).encode()).digest()).decode()
                identify["authentication"] = base64.b64encode(
                    hashlib.sha256((secret + auth["challenge"]).encode()).digest()).decode()
            phase = "authentication"
            _ws_send(stream, {"op": 1, "d": identify}, deadline)
            identified = _ws_receive(stream, deadline)
            if identified.get("op") != 2:
                raise ConnectionError("A autenticação WebSocket do OBS falhou.")
            if cancel_event and cancel_event.is_set():
                return "A gravação foi cancelada antes de enviar qualquer comando ao OBS."
            request_id = secrets.token_hex(8)
            phase = "request"
            # sendall may transmit part of a frame and then raise. From this
            # point onward Aurora must not claim the command was never sent.
            request_attempted = True
            _ws_send(stream, {"op": 6, "d": {"requestType": request_type,
                      "requestId": request_id, "requestData": {}}}, deadline)
            while True:
                result = _ws_receive(stream, deadline)
                if result.get("op") != 7:
                    continue
                data = result.get("d", {})
                if data.get("requestId") != request_id:
                    continue
                if not data.get("requestStatus", {}).get("result"):
                    comment = data.get("requestStatus", {}).get("comment", "").strip()
                    _append_action_log("obs_record", "rejected", {"action": action})
                    return (f"O OBS recusou o comando: {comment}. A gravação não foi alterada."
                            if comment else "O OBS recusou o comando. A gravação não foi alterada.")
                # A successful StartRecord/StopRecord RPC is not enough to
                # tell the user the output changed; verify OBS's resulting
                # state before speaking a success confirmation.
                expected_active = action == "start"
                verify_deadline = time.monotonic() + OBS_VERIFY_TIMEOUT
                status_data = {}
                actual_active = None
                while time.monotonic() < verify_deadline:
                    status_id = secrets.token_hex(8)
                    _ws_send(stream, {"op": 6, "d": {"requestType": "GetRecordStatus",
                              "requestId": status_id, "requestData": {}}}, verify_deadline)
                    while True:
                        status_reply = _ws_receive(stream, verify_deadline)
                        if status_reply.get("op") != 7:
                            continue
                        status_data = status_reply.get("d", {})
                        if status_data.get("requestId") == status_id:
                            break
                    if not status_data.get("requestStatus", {}).get("result"):
                        break
                    actual_active = status_data.get("responseData", {}).get("outputActive")
                    if actual_active is expected_active:
                        break
                    time.sleep(min(OBS_VERIFY_INTERVAL,
                                   max(0.0, verify_deadline - time.monotonic())))
                if (not status_data.get("requestStatus", {}).get("result")
                        or actual_active is not expected_active):
                    _append_action_log("obs_record", "unavailable", {"action": action,
                                        "phase": "verify", "error_type": "StateMismatch"})
                    return ("O OBS aceitou o comando, mas não confirmei que a gravação "+
                            ("está ativa." if expected_active else "foi parada."))
                _append_action_log("obs_record", "started" if action == "start" else "stopped")
                if action == "start":
                    return ("Gravação iniciada em segundo plano. Se quiser parar, é só dizer: "
                            "“Aurora, pare a gravação”.")
                break
        # Leave the WebSocket context before closing OBS. This runs only after
        # StopRecord succeeded and GetRecordStatus confirmed outputActive=False.
        try:
            if _close_obs_after_recording_stops():
                return "Gravação parada e OBS encerrado."
        except Exception as exc:
            _append_action_log("obs_record", "close_failed", {
                "action": action, "phase": "close", "error_type": type(exc).__name__,
            })
        return "Gravação parada no OBS, mas não consegui encerrar o aplicativo."
    except RuntimeError as exc:
        _append_action_log("obs_record", "unavailable", {"action": action, "phase": phase,
                            "error_type": type(exc).__name__})
        return str(exc)
    except Exception as exc:
        _append_action_log("obs_record", "unavailable", {"action": action, "phase": phase,
                            "error_type": type(exc).__name__})
        if (host in ("127.0.0.1", "::1", "localhost") and
                obs_settings.get("server_enabled") is False and
                int(port) == obs_settings.get("server_port")):
            return ("O WebSocket do OBS Studio Flatpak está desativado. No OBS, abra "
                    "Ferramentas → Configurações do servidor WebSocket e ative o servidor.")
        if request_attempted:
            return ("Enviei o comando ao OBS, mas perdi a confirmação. Confira se a gravação "
                    "começou ou parou antes de tentar de novo.")
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return (f"O OBS demorou demais na etapa de {phase}. Confira se o WebSocket está "
                    "ativo e tente novamente; não enviei o comando de gravação.")
        return (f"O OBS não respondeu em {host}:{port}. Abra o OBS e confira se o servidor "
                "WebSocket está ativo; não enviei o comando de gravação.")


