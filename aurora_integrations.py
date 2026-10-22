"""Fast, local-first desktop integrations used by Aurora's deterministic router."""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

SPOTIFY_REDIRECT_URI = "http://127.0.0.1:43827/callback"
SPOTIFY_SCOPES = "user-modify-playback-state user-read-playback-state"
OBS_REQUEST_TIMEOUT = 1.5


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


def site_url_from_request(prompt: str) -> str | None:
    """Return a safe HTTP(S) URL only when speech clearly asks for a site."""
    text = " ".join(str(prompt or "").strip().split())
    text = re.sub(r"^\s*(?:(?:ei|olá)\s+)?aurora[\s,.:;!?-]*", "", text, flags=re.I)
    lowered = text.casefold()
    starters = ("abra o site ", "abra site ", "abre o site ", "abre site ",
                "abrir o site ", "abrir site ", "acesse o site ", "acesse site ",
                "abra o link ", "abre o link ", "abrir o link ",
                "abra o endereço ", "abre o endereço ", "abrir o endereço ")
    target = None
    for starter in starters:
        if lowered.startswith(starter):
            target = text[len(starter):].strip(" .,!?:;")
            break
    if target is None:
        # A spoken, fully qualified domain is unambiguous even without "site".
        command_prefixes = ("abra ", "abre ", "abrir ", "acesse ")
        for prefix in command_prefixes:
            if lowered.startswith(prefix):
                candidate = text[len(prefix):].strip(" .,!?:;")
                if "." in candidate and " " not in candidate:
                    target = candidate
                break
    if not target:
        return None
    if target.startswith(("http://", "https://")):
        candidate = target
    else:
        if "/" not in target and "." not in target:
            return None
        candidate = "https://" + target
    try:
        parsed = urllib.parse.urlsplit(candidate)
        parsed.port
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return None
    if any(c.isspace() for c in candidate):
        return None
    return candidate


def unique_screenshot_path(pictures_dir: str | Path, now: datetime | None = None) -> Path:
    folder = Path(pictures_dir).expanduser() / "Aurora"
    folder.mkdir(parents=True, exist_ok=True)
    moment = now or datetime.now().astimezone()
    stamp = moment.strftime("%Y-%m-%d_%H-%M-%S-%f")
    candidate = folder / f"Aurora_{stamp}.png"
    suffix = 1
    while candidate.exists():
        candidate = folder / f"Aurora_{stamp}_{suffix}.png"
        suffix += 1
    return candidate


def save_screenshot_uri(uri: str, pictures_dir: str | Path, now: datetime | None = None) -> Path:
    """Copy the local file URI returned by the desktop screenshot portal."""
    parsed = urllib.parse.urlsplit(str(uri))
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        raise ValueError("O portal não retornou um arquivo local.")
    source = Path(urllib.parse.unquote(parsed.path))
    if not source.is_file():
        raise FileNotFoundError("O arquivo temporário da captura não existe.")
    target = unique_screenshot_path(pictures_dir, now)
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    return target


def _portal_request_object_path(bus_name: str, token: str) -> str:
    sender = bus_name.replace(":", "_").replace(".", "_")
    return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"


def capture_screenshot(pictures_dir: str | Path, timeout: int = 45) -> Path:
    """Request a full-screen capture through the XDG portal and save it safely."""
    try:
        from PySide6.QtCore import QEventLoop, QObject, QTimer, Slot
        from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage
    except ImportError as exc:
        raise RuntimeError("O suporte DBus do Qt não está instalado.") from exc
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise RuntimeError("Não conectei ao portal de captura da sessão gráfica.")
    token = "aurora_" + secrets.token_hex(8)
    # xdg-desktop-portal derives the Request object path from the caller's
    # unique bus name by replacing both ':' and '.' with '_'. Keeping the
    # leading underscore is required (for example :1.42 -> _1_42).
    request_path = _portal_request_object_path(bus.baseService(), token)
    result = {}
    loop = QEventLoop()

    class Response(QObject):
        @Slot(int, "QVariantMap")
        def receive(self, code, data):
            result["code"] = int(code)
            result["data"] = dict(data)
            loop.quit()

    receiver = Response()
    slot = "receive(uint,QVariantMap)"
    if not bus.connect("org.freedesktop.portal.Desktop", request_path,
                       "org.freedesktop.portal.Request", "Response", receiver, slot):
        raise RuntimeError("Não consegui acompanhar a resposta do portal de captura.")
    message = QDBusMessage.createMethodCall(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot", "Screenshot")
    message.setArguments(["", {"handle_token": token, "interactive": False, "modal": True}])
    reply = bus.call(message, QDBus.CallMode.BlockWithGui, 5000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        bus.disconnect("org.freedesktop.portal.Desktop", request_path,
                       "org.freedesktop.portal.Request", "Response", receiver, slot)
        raise RuntimeError(reply.errorMessage() or "O portal recusou a captura.")
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(max(1, int(timeout)) * 1000)
    if "code" not in result:
        loop.exec()
    timer.stop()
    bus.disconnect("org.freedesktop.portal.Desktop", request_path,
                   "org.freedesktop.portal.Request", "Response", receiver, slot)
    if "code" not in result:
        raise TimeoutError("A captura expirou ou o portal aguarda uma ação do sistema.")
    if result["code"] != 0:
        raise RuntimeError("A captura foi cancelada pelo portal ou pelo usuário.")
    uri = result["data"].get("uri")
    if not uri:
        raise RuntimeError("O portal concluiu sem informar o arquivo da captura.")
    return save_screenshot_uri(str(uri), pictures_dir)


def _append_action_log(action: str, outcome: str, details: dict | None = None) -> None:
    """Keep an auditable, local JSONL record; callers must omit credentials."""
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "aurora"
    root.mkdir(parents=True, exist_ok=True)
    row = {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
           "action": action, "outcome": outcome, "details": details or {}}
    path = root / "actions.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _token_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "aurora" / "spotify-token.json"


def _store_token(token: dict) -> None:
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(token, stream)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def _spotify_request(url: str, token: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                    headers={"Authorization": f"Bearer {token}",
                                             "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            raw = response.read(1_000_000)
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read(5000)
        try:
            detail = json.loads(raw)
        except Exception:
            detail = {"message": raw.decode("utf-8", "replace")}
        return exc.code, detail


def spotify_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


_spotify_auth_lock = threading.Lock()
_spotify_auth_started = False


def start_spotify_authorization(client_id: str, open_url) -> str:
    """Start the local PKCE callback once; no client secret is stored."""
    global _spotify_auth_started
    client_id = str(client_id or "").strip()
    if not client_id:
        return "Configure spotify_client_id em aurora-settings.json para conectar o Spotify."
    with _spotify_auth_lock:
        if _spotify_auth_started:
            return "A autorização do Spotify já está aguardando no navegador."
        try:
            server = http.server.HTTPServer(("127.0.0.1", 43827), _SpotifyCallback)
        except OSError:
            return "A porta local 43827 está ocupada; não iniciei a autorização do Spotify."
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(24)
        server.client_id = client_id
        server.verifier = verifier
        server.state = state
        server.completed = False
        _spotify_auth_started = True
    query = urllib.parse.urlencode({"client_id": client_id, "response_type": "code",
                                    "redirect_uri": SPOTIFY_REDIRECT_URI,
                                    "scope": SPOTIFY_SCOPES, "state": state,
                                    "code_challenge_method": "S256",
                                    "code_challenge": spotify_code_challenge(verifier)})
    url = "https://accounts.spotify.com/authorize?" + query
    def wait_for_oauth_callback():
        deadline = time.monotonic() + 300
        while not server.completed and time.monotonic() < deadline:
            server.timeout = min(2.0, max(0.1, deadline - time.monotonic()))
            try:
                server.handle_request()
            except OSError:
                break
        server.server_close()
        with _spotify_auth_lock:
            _spotify_auth_started = False
    threading.Thread(target=wait_for_oauth_callback, daemon=True,
                     name="aurora-spotify-oauth").start()
    if not open_url(url):
        server.completed = True
        server.server_close()
        with _spotify_auth_lock:
            _spotify_auth_started = False
        return "Não consegui abrir a autorização do Spotify no navegador."
    _append_action_log("spotify_authorization", "browser_opened")
    return "Abri a autorização do Spotify. Aprove a conexão no navegador; depois me peça a música."


class _SpotifyCallback(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        supplied = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        error = query.get("error", [""])[0]
        if not secrets.compare_digest(supplied, self.server.state):
            self.send_error(400, "Invalid OAuth state")
            return
        self.server.completed = True
        if error or not code:
            body = b"Spotify authorization was cancelled. You can close this tab."
            self.send_response(400)
        else:
            form = urllib.parse.urlencode({"client_id": self.server.client_id,
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
                "code_verifier": self.server.verifier}).encode()
            request = urllib.request.Request("https://accounts.spotify.com/api/token", data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    token = json.loads(response.read(100_000))
                token["client_id"] = self.server.client_id
                token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
                _store_token(token)
                _append_action_log("spotify_authorization", "connected")
                body = b"Spotify connected to Aurora. You can close this tab."
                self.send_response(200)
            except Exception:
                body = b"Spotify authorization could not be completed. Check the Aurora service logs."
                self.send_response(502)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def _spotify_access_token(client_id: str) -> str:
    path = _token_path()
    if not path.is_file():
        raise RuntimeError("Spotify não conectado. Diga ‘conectar Spotify’ depois de configurar o Client ID.")
    try:
        token = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("A autorização local do Spotify está inválida; conecte novamente.") from exc
    if token.get("client_id") != client_id or not token.get("refresh_token"):
        raise RuntimeError("A autorização é de outro app Spotify; conecte novamente.")
    if time.time() >= float(token.get("expires_at", 0)) - 60:
        form = urllib.parse.urlencode({"client_id": client_id, "grant_type": "refresh_token",
                                       "refresh_token": token["refresh_token"]}).encode()
        request = urllib.request.Request("https://accounts.spotify.com/api/token", data=form,
             headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=2.0) as response:
                refreshed = json.loads(response.read(100_000))
        except Exception as exc:
            raise RuntimeError("Não consegui renovar a autorização do Spotify.") from exc
        token.update(refreshed)
        token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
        _store_token(token)
    return str(token["access_token"])


def play_spotify_track(query: str, client_id: str) -> str:
    query = " ".join(str(query or "").split()).strip()
    if not query:
        return "Diga o nome da música ou do artista."
    try:
        token = _spotify_access_token(client_id)
        search_url = "https://api.spotify.com/v1/search?" + urllib.parse.urlencode(
            {"q": query, "type": "track", "limit": 5})
        status, body = _spotify_request(search_url, token)
        if status != 200:
            raise RuntimeError("A busca do catálogo Spotify falhou; tente novamente em instantes.")
        tracks = body.get("tracks", {}).get("items", [])
        if not tracks:
            raise RuntimeError("Não encontrei essa música no catálogo do Spotify.")
        track = tracks[0]
        uri = track.get("uri")
        title = str(track.get("name", "")).strip()
        artists = ", ".join(str(item.get("name", "")).strip()
                             for item in track.get("artists", []) if item.get("name"))
        if not uri or not title:
            raise RuntimeError("O Spotify retornou uma faixa sem identificação válida.")
        status, _ = _spotify_request("https://api.spotify.com/v1/me/player/play", token,
                                     method="PUT", payload={"uris": [uri]})
        if status not in (200, 202, 204):
            raise RuntimeError("Abra o Spotify em um dispositivo ativo e confirme uma conta Premium.")
        spoken = f"Tocando {title}" + (f", de {artists}." if artists else ".")
        _append_action_log("spotify_play", "started", {"track": title, "artists": artists})
        return spoken
    except RuntimeError as exc:
        _append_action_log("spotify_play", "unavailable")
        return str(exc)
    except Exception:
        _append_action_log("spotify_play", "failed")
        return "Não consegui falar com o Spotify agora; nada foi iniciado."


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


def obs_record(action: str, password: str = "", host: str = "127.0.0.1", port: int = 4455) -> str:
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
    request_sent = False
    try:
        deadline = time.monotonic() + OBS_REQUEST_TIMEOUT
        stream = socket.create_connection((host, int(port)), timeout=OBS_REQUEST_TIMEOUT)
        with stream:
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
            _ws_send(stream, {"op": 1, "d": identify}, deadline)
            identified = _ws_receive(stream, deadline)
            if identified.get("op") != 2:
                raise ConnectionError("A autenticação WebSocket do OBS falhou.")
            request_id = secrets.token_hex(8)
            _ws_send(stream, {"op": 6, "d": {"requestType": request_type,
                      "requestId": request_id, "requestData": {}}}, deadline)
            request_sent = True
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
                _append_action_log("obs_record", "started" if action == "start" else "stopped")
                return "Gravação iniciada no OBS." if action == "start" else "Gravação parada no OBS."
    except RuntimeError as exc:
        _append_action_log("obs_record", "unavailable", {"action": action, "phase": "request" if request_sent else "connect"})
        return str(exc)
    except Exception:
        _append_action_log("obs_record", "unavailable", {"action": action, "phase": "confirmation" if request_sent else "connect"})
        if (host in ("127.0.0.1", "::1", "localhost") and
                obs_settings.get("server_enabled") is False and
                int(port) == obs_settings.get("server_port")):
            return ("O WebSocket do OBS Studio Flatpak está desativado. No OBS, abra "
                    "Ferramentas → Configurações do servidor WebSocket e ative o servidor.")
        if request_sent:
            return ("Enviei o comando ao OBS, mas perdi a confirmação. Confira se a gravação "
                    "começou ou parou antes de tentar de novo.")
        return (f"O OBS não respondeu em {host}:{port}. Abra o OBS e confira se o servidor "
                "WebSocket está ativo; não enviei o comando de gravação.")
