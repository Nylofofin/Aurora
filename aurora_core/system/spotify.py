"""Spotify OAuth and playback integration."""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .action_log import _append_action_log

SPOTIFY_REDIRECT_URI = "http://127.0.0.1:43827/callback"
SPOTIFY_SCOPES = "user-modify-playback-state user-read-playback-state"

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
        _append_action_log("spotify_play", "started")
        return spoken
    except RuntimeError as exc:
        _append_action_log("spotify_play", "unavailable")
        return str(exc)
    except Exception:
        _append_action_log("spotify_play", "failed")
        return "Não consegui falar com o Spotify agora; nada foi iniciado."
