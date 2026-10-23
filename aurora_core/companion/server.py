from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess
import threading
import time
from urllib.parse import urlsplit


MAX_BODY = 16 * 1024
PAIR_WINDOW_SECONDS = 300
MAX_PAIR_ATTEMPTS = 5


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

    def __init__(self, directory: Path, address: str, port: int, on_message, *, api_timeout=120):
        self.directory = directory
        self.address = address
        self.port = int(port)
        self.on_message = on_message
        self.api_timeout = api_timeout
        self.auth = PairingAuth(directory)
        self.cert_path, self.key_path, self.fingerprint = ensure_tls_identity(directory, address)
        _write_private(directory / "server-fingerprint.txt", self.fingerprint + "\n")
        self.history_path = directory / "conversations.json"
        self._history_lock = threading.RLock()
        self._conversation_locks: dict[str, threading.Lock] = {}
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
                    self._json(200, {"service": "Aurora", "protocol": 1, "fingerprint": outer.fingerprint})
                    return
                if not self._authorized():
                    self._json(401, {"error": "unauthorized"})
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
                    self._json(200, {"conversation_id": conversation_id, "answer": answer.strip()})
                finally:
                    lock.release()

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

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread:
            self.thread.join(timeout=3)
