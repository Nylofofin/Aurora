# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import hmac
import ipaddress
import json
import base64
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlsplit


MAX_BODY = 16 * 1024
MAX_VOICE_BODY = 2_000_000
PAIR_WINDOW_SECONDS = 300
MAX_PAIR_ATTEMPTS = 5
CONTROL_LEASE_SECONDS = 60


def discover_private_address() -> str:
    """Choose the host's routed LAN address without sending application data."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        address = sock.getsockname()[0]
        parsed = ipaddress.ip_address(address)
        if parsed.is_private and not parsed.is_loopback and not parsed.is_link_local:
            return address
    finally:
        sock.close()
    raise RuntimeError("Nenhum endereço IPv4 privado para a rede local foi encontrado")


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def ensure_tls_identity(directory: Path, address: str) -> tuple[Path, Path, str]:
    """Create a local-only TLS certificate and return its SHA-256 pin."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    cert, key = directory / "server-cert.pem", directory / "server-key.pem"
    if not cert.exists() or not key.exists():
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(key), "-out", str(cert), "-days", "825",
             "-subj", "/CN=Aurora Companion",
             "-addext", f"subjectAltName=IP:{address},IP:127.0.0.1,DNS:localhost"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20,
        )
        os.chmod(key, 0o600)
        os.chmod(cert, 0o600)
    decoded = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
    fingerprint = hashlib.sha256(decoded).hexdigest()
    return cert, key, fingerprint


class PairingAuth:
    """Single-use pairing code and persistent hashed bearer-token records."""

    def __init__(self, directory: Path, *, clock=time.monotonic):
        self.directory = directory
        self.clock = clock
        self._lock = threading.Lock()
        self._pair_attempts: dict[str, list[float]] = {}
        self.token_path = directory / "device-tokens.json"
        try:
            stored = json.loads(self.token_path.read_text(encoding="utf-8"))
            self._tokens = {str(item["hash"]): str(item["address"]) for item in stored if isinstance(item, dict)}
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            self._tokens = {}
        self.code_path = directory / "pairing-code.txt"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        if not self.code_path.exists():
            self.rotate_code()

    def rotate_code(self) -> str:
        code = f"{secrets.randbelow(100_000_000):08d}"
        _write_private(self.code_path, code + "\n")
        return code

    def pair(self, address: str, supplied_code: str) -> str | None:
        now = self.clock()
        with self._lock:
            attempts = [t for t in self._pair_attempts.get(address, []) if now - t < PAIR_WINDOW_SECONDS]
            if len(attempts) >= MAX_PAIR_ATTEMPTS:
                self._pair_attempts[address] = attempts
                return None
            attempts.append(now)
            self._pair_attempts[address] = attempts
            try:
                expected = self.code_path.read_text(encoding="ascii").strip()
            except OSError:
                return None
            if not hmac.compare_digest(expected, str(supplied_code)):
                return None
            try:
                self.code_path.unlink()
            except FileNotFoundError:
                return None
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode("ascii")).hexdigest()
            self._tokens[digest] = address
            _write_private(self.token_path, json.dumps([{"hash": key, "address": value} for key, value in self._tokens.items()]))
            self.rotate_code()
            return token

    def authorized(self, token: str) -> bool:
        digest = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
        with self._lock:
            try:
                stored = json.loads(self.token_path.read_text(encoding="utf-8"))
                current = {str(item["hash"]): str(item["address"]) for item in stored if isinstance(item, dict)}
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                current = {}
            self._tokens = current
            return any(hmac.compare_digest(digest, known) for known in current)


class CompanionServer:
    """Small HTTPS API; request processing stays injected into AuroraService."""

    def __init__(self, directory: Path, address: str, port: int, on_message, *, on_voice=None, on_control=None, on_speech=None, on_wake_audio=None, screen_stream=None, sound_directory=None, api_timeout=120):
        self.directory = directory
        self.address = address
        self.port = int(port)
        self.on_message = on_message
        self.on_voice = on_voice
        self.on_speech = on_speech
        self.on_wake_audio = on_wake_audio
        self.screen_stream = screen_stream
        self.sound_directory = Path(sound_directory) if sound_directory else None
        self._on_control = on_control
        self.api_timeout = api_timeout
        self.auth = PairingAuth(directory)
        self.cert_path, self.key_path, self.fingerprint = ensure_tls_identity(directory, address)
        _write_private(directory / "server-fingerprint.txt", self.fingerprint + "\n")
        self.history_path = directory / "conversations.json"
        self._history_lock = threading.RLock()
        self._conversation_locks: dict[str, threading.Lock] = {}
        self._control_lock = threading.RLock()
        self._control_owner = None
        self._control_expires = 0.0
        self._remote_state = "idle"
        self._resume_pending = False
        self._advertiser = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AuroraCompanion/1"
            sys_version = ""

            def log_message(self, _format, *_args):
                return

            def _json(self, status, payload):
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _speech_audio(self, text):
                if not outer.on_speech:
                    return ""
                try:
                    audio = outer.on_speech(text)
                    if not isinstance(audio, bytes) or not audio or len(audio) > 3_000_000:
                        return ""
                    return base64.b64encode(audio).decode("ascii")
                except Exception as exc:
                    print(f"[companion] Edge TTS indisponível ({type(exc).__name__})", flush=True)
                    return ""

            def _audio(self, data, content_type):
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def _screen_frame(self, frame_number, data):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Frame-Number", str(frame_number))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError as exc:
                    raise ValueError("body size") from exc
                if length <= 0 or length > MAX_BODY:
                    raise ValueError("body size")
                return json.loads(self.rfile.read(length))

            def _authorized(self):
                scheme, _, token = self.headers.get("Authorization", "").partition(" ")
                return scheme.lower() == "bearer" and outer.auth.authorized(token)

            def do_GET(self):
                path = urlsplit(self.path).path
                if path == "/v1/status":
                    self._json(200, {"service": "Aurora", "protocol": 1, "fingerprint": outer.fingerprint, "mobile_control": outer.control_active(), "state": outer.remote_state()})
                    return
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                if path == "/v1/screen/frame":
                    _, _, token = self.headers.get("Authorization", "").partition(" ")
                    if not outer.owns_control(token):
                        self._json(409, {"error": "mobile control not acquired"})
                        return
                    if not outer.screen_stream:
                        self._json(503, {"error": "screen stream unavailable"})
                        return
                    try:
                        query = parse_qs(urlsplit(self.path).query)
                        after = int(query.get("after", ["0"])[0])
                        frame_number, frame = outer.screen_stream.frame_after(after, timeout=2.0)
                    except (ValueError, RuntimeError) as exc:
                        self._json(503, {"error": str(exc)})
                        return
                    if not frame:
                        self._json(202, {"state": outer.screen_stream.state, "frame": frame_number})
                        return
                    if len(frame) > 2_000_000:
                        self._json(413, {"error": "screen frame too large"})
                        return
                    self._screen_frame(frame_number, frame)
                    return
                if path in {"/v1/sounds/entrada.wav", "/v1/sounds/saida.wav"}:
                    _, _, token = self.headers.get("Authorization", "").partition(" ")
                    if not outer.owns_control(token):
                        self._json(409, {"error": "mobile control not acquired"})
                        return
                    filename = path.rsplit("/", 1)[-1]
                    sound_path = outer.sound_directory / filename if outer.sound_directory else None
                    try:
                        if sound_path is None or not sound_path.is_file():
                            raise FileNotFoundError
                        data = sound_path.read_bytes()
                    except OSError:
                        self._json(404, {"error": "sound not found"})
                        return
                    if len(data) > 500_000:
                        self._json(413, {"error": "sound too large"})
                        return
                    self._audio(data, "audio/wav")
                    return
                if path == "/v1/conversations":
                    summaries = [
                        {key: item.get(key) for key in ("id", "title", "created_at", "updated_at")}
                        | {"message_count": len(item.get("display_messages", item.get("messages", [])))}
                        for item in outer._load_history() if isinstance(item, dict)
                    ]
                    self._json(200, {"conversations": summaries})
                    return
                if path.startswith("/v1/conversations/"):
                    conversation_id = path.rsplit("/", 1)[-1]
                    item = outer._get_conversation(conversation_id)
                    self._json(200 if item is not None else 404, item or {"error": "not found"})
                    return
                self._json(404, {"error": "not found"})

            def do_POST(self):
                path = urlsplit(self.path).path
                if path == "/v1/control":
                    self._post_control()
                    return
                if path == "/v1/voice":
                    self._post_voice()
                    return
                if path == "/v1/wake":
                    self._post_wake_audio()
                    return
                if path == "/v1/speech":
                    self._post_speech()
                    return
                if path in {"/v1/screen/start", "/v1/screen/stop"}:
                    self._post_screen_stream(path)
                    return
                if path == "/v1/desktop/input":
                    self._post_desktop_input()
                    return
                if path == "/v1/user/profile":
                    self._post_user_profile()
                    return
                try:
                    payload = self._body()
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                    self._json(400, {"error": "invalid request"})
                    return
                if path == "/v1/pair":
                    if not isinstance(payload, dict):
                        self._json(400, {"error": "invalid request"})
                        return
                    token = outer.auth.pair(self.client_address[0], payload.get("code", ""))
                    if token is None:
                        self._json(403, {"error": "pairing rejected"})
                    else:
                        self._json(200, {"token": token})
                    return
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                _, _, token = self.headers.get("Authorization", "").partition(" ")
                if not outer.owns_control(token):
                    self._json(409, {"error": "mobile control not acquired"})
                    return
                if path != "/v1/chat" or not isinstance(payload, dict):
                    self._json(404, {"error": "not found"})
                    return
                message = payload.get("message")
                conversation_id = payload.get("conversation_id")
                if not isinstance(message, str) or not message.strip() or len(message) > 4000:
                    self._json(400, {"error": "invalid message"})
                    return
                if (not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 64
                        or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in conversation_id)):
                    self._json(400, {"error": "invalid conversation"})
                    return
                lock = outer._conversation_lock(conversation_id)
                if not lock.acquire(timeout=outer.api_timeout):
                    self._json(409, {"error": "conversation busy"})
                    return
                try:
                    history = outer._get_conversation(conversation_id)
                    messages = list(history.get("messages", [])) if history else []
                    try:
                        completion = outer.on_message(message.strip(), messages)
                    except TimeoutError:
                        self._json(504, {"error": "request timeout"})
                        return
                    except Exception:
                        self._json(500, {"error": "request failed"})
                        return
                    if isinstance(completion, dict):
                        answer = completion.get("answer", "")
                        context_history = completion.get("context_history")
                    else:
                        answer = completion
                        context_history = None
                    if not isinstance(answer, str) or not answer.strip():
                        self._json(502, {"error": "empty response"})
                        return
                    outer._append_exchange(conversation_id, message.strip(), answer.strip(), context_history)
                    if payload.get("speech_delivery") == "separate":
                        self._json(200, {"conversation_id": conversation_id, "answer": answer.strip()})
                    else:
                        if outer.on_speech:
                            outer.set_remote_state("speaking")
                        speech_audio = self._speech_audio(answer.strip())
                        self._json(200, {"conversation_id": conversation_id, "answer": answer.strip(), "speech_audio_base64": speech_audio})
                        if outer.on_speech and outer.control_active():
                            outer.set_remote_state("ready")
                finally:
                    lock.release()

            def _post_control(self):
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                try:
                    payload = self._body()
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                    self._json(400, {"error": "invalid request"})
                    return
                scheme, _, token = self.headers.get("Authorization", "").partition(" ")
                operation = payload.get("operation") if isinstance(payload, dict) else None
                if operation == "acquire":
                    acquired, changed = outer.acquire_control(token)
                    if acquired and changed and not outer.notify_control(True):
                        outer.release_control(token)
                        outer.notify_control(False)
                        acquired = False
                    self._json(200 if acquired else 409, {"mobile_control": acquired})
                elif operation == "heartbeat":
                    active = outer.heartbeat_control(token)
                    self._json(200 if active else 409, {"mobile_control": active, "state": outer.remote_state()})
                elif operation == "release":
                    released, changed = outer.release_control(token)
                    if changed and not outer.notify_control(False):
                        self._json(503, {"error": "desktop resume pending", "mobile_control": False})
                        return
                    self._json(200 if released else 409, {"mobile_control": False})
                else:
                    self._json(400, {"error": "invalid operation"})

            def _post_voice(self):
                authorized = self._authorized()
                if not authorized:
                    self._json(401, {"error": "unauthorized"})
                    return
                if not outer.on_voice:
                    self._json(404, {"error": "not found"})
                    return
                _, _, token = self.headers.get("Authorization", "").partition(" ")
                if not outer.owns_control(token):
                    self._json(409, {"error": "mobile control not acquired"})
                    return
                conversation_id = self.headers.get("X-Conversation-ID", "")
                if (not conversation_id or len(conversation_id) > 64
                        or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in conversation_id)):
                    self._json(400, {"error": "invalid conversation"})
                    return
                if not self.headers.get("Content-Type", "").lower().startswith("audio/wav"):
                    self._json(415, {"error": "audio/wav required"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length < 44 or length > MAX_VOICE_BODY:
                    self._json(413, {"error": "audio size rejected"})
                    return
                audio = self.rfile.read(length)
                if len(audio) != length:
                    self._json(400, {"error": "incomplete audio"})
                    return
                lock = outer._conversation_lock(conversation_id)
                if not lock.acquire(timeout=outer.api_timeout):
                    self._json(409, {"error": "conversation busy"})
                    return
                try:
                    history = outer._get_conversation(conversation_id)
                    messages = list(history.get("messages", [])) if history else []
                    try:
                        completion = outer.on_voice(audio, messages)
                    except TimeoutError:
                        self._json(504, {"error": "request timeout"})
                        return
                    except Exception:
                        self._json(500, {"error": "voice request failed"})
                        return
                    if not isinstance(completion, dict):
                        self._json(502, {"error": "invalid voice response"})
                        return
                    transcript = completion.get("transcript")
                    answer = completion.get("answer")
                    if not isinstance(transcript, str) or not transcript.strip() or not isinstance(answer, str) or not answer.strip():
                        self._json(502, {"error": "empty voice response"})
                        return
                    outer._append_exchange(conversation_id, transcript.strip(), answer.strip(), completion.get("context_history"))
                    separate_speech = self.headers.get("X-Speech-Delivery", "").lower() == "separate"
                    if separate_speech:
                        self._json(200, {"conversation_id": conversation_id, "transcript": transcript.strip(), "answer": answer.strip()})
                    else:
                        if outer.on_speech:
                            outer.set_remote_state("speaking")
                        speech_audio = self._speech_audio(answer.strip())
                        self._json(200, {"conversation_id": conversation_id, "transcript": transcript.strip(), "answer": answer.strip(), "speech_audio_base64": speech_audio})
                        if outer.on_speech and outer.control_active():
                            outer.set_remote_state("ready")
                finally:
                    lock.release()

            def _post_speech(self):
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                _, _, token = self.headers.get("Authorization", "").partition(" ")
                if not outer.owns_control(token):
                    self._json(409, {"error": "mobile control not acquired"})
                    return
                try:
                    payload = self._body()
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                    self._json(400, {"error": "invalid request"})
                    return
                text = payload.get("text") if isinstance(payload, dict) else None
                if not isinstance(text, str) or not text.strip() or len(text) > 1800:
                    self._json(400, {"error": "invalid speech text"})
                    return
                if not outer.on_speech:
                    self._json(503, {"error": "Edge TTS unavailable"})
                    return
                outer.set_remote_state("speaking")
                try:
                    try:
                        audio = outer.on_speech(text.strip())
                    except Exception as exc:
                        print(f"[companion] Edge TTS falhou ({type(exc).__name__})", flush=True)
                        self._json(503, {"error": "Edge TTS failed"})
                        return
                    if not isinstance(audio, bytes) or not audio or len(audio) > 3_000_000:
                        print("[companion] Edge TTS retornou áudio vazio ou acima do limite", flush=True)
                        self._json(503, {"error": "Edge TTS returned no audio"})
                        return
                    print(f"[companion] Edge TTS entregando MP3: {len(audio)} bytes", flush=True)
                    self._audio(audio, "audio/mpeg")
                finally:
                    if outer.control_active():
                        outer.set_remote_state("ready")

            def _post_wake_audio(self):
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                _, _, token = self.headers.get("Authorization", "").partition(" ")
                if not outer.owns_control(token):
                    self._json(409, {"error": "mobile control not acquired"})
                    return
                if not outer.on_wake_audio:
                    self._json(503, {"error": "local wake detector unavailable"})
                    return
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "audio/pcm":
                    self._json(415, {"error": "audio/pcm required"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > 32000 or length % 2:
                    self._json(400, {"error": "invalid PCM frame"})
                    return
                frame = self.rfile.read(length)
                if len(frame) != length:
                    self._json(400, {"error": "incomplete PCM frame"})
                    return
                try:
                    detected = bool(outer.on_wake_audio(token, frame))
                except Exception:
                    self._json(503, {"error": "local wake detector failed"})
                    return
                self._json(200, {"wake_detected": detected})

            def _post_screen_stream(self, path):
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                _, _, token = self.headers.get("Authorization", "").partition(" ")
                if not outer.owns_control(token):
                    self._json(409, {"error": "mobile control not acquired"})
                    return
                if not outer.screen_stream:
                    self._json(503, {"error": "screen stream unavailable"})
                    return
                if path.endswith("/start"):
                    state = outer.screen_stream.start()
                    self._json(202, {"state": state, "consent_required": True})
                else:
                    outer.screen_stream.stop()
                    self._json(200, {"state": "stopping"})

            def _post_desktop_input(self):
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                _, _, token = self.headers.get("Authorization", "").partition(" ")
                if not outer.owns_control(token):
                    self._json(409, {"error": "mobile control not acquired"})
                    return
                try:
                    payload = self._body()
                    if not isinstance(payload, dict):
                        self._json(400, {"error": "invalid json"})
                        return
                    from ..system.remote_input import validate_remote_event
                    event = validate_remote_event(
                        payload.get("action", "move"), payload.get("x", 0.0),
                        payload.get("y", 0.0), payload.get("button", 1),
                        payload.get("delta", 0.0),
                    )
                    if not outer.screen_stream:
                        self._json(409, {"error": "remote desktop stream is not available"})
                        return
                    ok = outer.screen_stream.send_input(event)
                    self._json(200 if ok else 409, {"success": ok, "error": None if ok else "screen sharing and GNOME pointer consent are required"})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

            def _post_user_profile(self):
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
                    return
                try:
                    payload = self._body()
                    if not isinstance(payload, dict):
                        self._json(400, {"error": "invalid json"})
                        return
                    username = str(payload.get("username", "")).strip()
                    age = str(payload.get("age", "")).strip()
                    from ..memory import user_memory_update
                    if username:
                        user_memory_update(f"O nome do usuário é {username}")
                    if age:
                        user_memory_update(f"A idade do usuário é {age} anos")
                    profile_file = outer.directory / "user_profile.json"
                    _write_private(profile_file, json.dumps(payload, ensure_ascii=False, indent=2))
                    self._json(200, {"success": True, "saved_profile": payload})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

        self.httpd = ThreadingHTTPServer((address, self.port), Handler)
        self.httpd.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(self.cert_path), str(self.key_path))
        self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
        self.thread: threading.Thread | None = None

    def _conversation_lock(self, conversation_id):
        with self._history_lock:
            return self._conversation_locks.setdefault(conversation_id, threading.Lock())

    def _token_digest(self, token):
        return hashlib.sha256(str(token).encode("utf-8")).hexdigest()

    def control_active(self):
        with self._control_lock:
            return bool(self._control_owner and time.monotonic() < self._control_expires)

    def owns_control(self, token):
        digest = self._token_digest(token)
        with self._control_lock:
            return bool(self._control_owner and time.monotonic() < self._control_expires and hmac.compare_digest(self._control_owner, digest))

    def set_remote_state(self, state):
        allowed = {"idle", "ready", "transcribing", "thinking", "searching", "speaking", "error"}
        if state not in allowed: return
        with self._control_lock:
            self._remote_state = state

    def remote_state(self):
        with self._control_lock:
            return self._remote_state

    def acquire_control(self, token):
        digest = self._token_digest(token)
        if not self.auth.authorized(token):
            return False, False
        with self._control_lock:
            now = time.monotonic()
            if self._control_owner and now >= self._control_expires:
                self._control_owner = None
            if self._control_owner and not hmac.compare_digest(self._control_owner, digest):
                return False, False
            changed = self._control_owner is None
            self._control_owner = digest
            self._control_expires = now + CONTROL_LEASE_SECONDS
            return True, changed

    def heartbeat_control(self, token):
        digest = self._token_digest(token)
        with self._control_lock:
            now = time.monotonic()
            if not self._control_owner or now >= self._control_expires or not hmac.compare_digest(self._control_owner, digest):
                if self._control_owner and now >= self._control_expires:
                    self._control_owner = None
                return False
            self._control_expires = now + CONTROL_LEASE_SECONDS
            return True

    def release_control(self, token):
        digest = self._token_digest(token)
        with self._control_lock:
            if not self._control_owner or not hmac.compare_digest(self._control_owner, digest):
                return False, False
            self._control_owner = None
            self._control_expires = 0.0
            return True, True

    def notify_control(self, active):
        result = True
        if self._on_control:
            try:
                result = bool(self._on_control(active))
            except Exception:
                result = False
        with self._control_lock:
            if active:
                self._resume_pending = False
            elif result:
                self._resume_pending = False
            else:
                self._resume_pending = True
        return result

    def _load_history(self):
        try:
            data = json.loads(self.history_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _get_conversation(self, conversation_id):
        if not conversation_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in conversation_id):
            return None
        with self._history_lock:
            return next((item for item in self._load_history() if item.get("id") == conversation_id), None)

    def _append_exchange(self, conversation_id, user_text, assistant_text, context_history=None):
        with self._history_lock:
            conversations = self._load_history()
            now = int(time.time())
            item = next((entry for entry in conversations if entry.get("id") == conversation_id), None)
            if item is None:
                item = {"id": conversation_id, "title": user_text[:72], "created_at": now, "messages": [], "display_messages": []}
                conversations.insert(0, item)
            item["updated_at"] = now
            exchange = [
                {"role": "user", "content": user_text[:4000], "created_at": now},
                {"role": "assistant", "content": assistant_text[:12000], "created_at": now},
            ]
            item.setdefault("display_messages", []).extend(exchange)
            item["display_messages"] = item["display_messages"][-100:]
            if isinstance(context_history, list):
                safe_context = [
                    {"role": entry["role"], "content": str(entry["content"])[:16000]}
                    for entry in context_history[-200:]
                    if isinstance(entry, dict) and entry.get("role") in {"user", "assistant"} and isinstance(entry.get("content"), str)
                ]
                item["messages"] = safe_context
            else:
                item["messages"].extend(exchange)
                item["messages"] = item["messages"][-200:]
            conversations = conversations[:100]
            _write_private(self.history_path, json.dumps(conversations, ensure_ascii=False, separators=(",", ":")))

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="aurora-companion-https", daemon=True)
        self.thread.start()
        publisher = shutil.which("avahi-publish-service")
        if publisher and self.port > 0:
            try:
                self._advertiser = subprocess.Popen(
                    [publisher, "Aurora Companion", "_aurora-companion._tcp", str(self.port)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except OSError:
                self._advertiser = None
        self._control_monitor = threading.Thread(target=self._monitor_control, name="aurora-companion-control", daemon=True)
        self._control_monitor.start()

    def _monitor_control(self):
        while self.thread and self.thread.is_alive():
            expired = False
            with self._control_lock:
                if self._control_owner and time.monotonic() >= self._control_expires:
                    self._control_owner = None
                    self._control_expires = 0.0
                    expired = True
                retry_resume = self._resume_pending
            if expired or retry_resume:
                self.notify_control(False)
            time.sleep(2)

    def close(self):
        released = False
        with self._control_lock:
            released = self._control_owner is not None
            self._control_owner = None
            self._control_expires = 0.0
        if released:
            self.notify_control(False)
        advertiser = self._advertiser
        self._advertiser = None
        if advertiser and advertiser.poll() is None:
            advertiser.terminate()
            try:
                advertiser.wait(timeout=2)
            except subprocess.TimeoutExpired:
                advertiser.kill()
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread:
            self.thread.join(timeout=3)
