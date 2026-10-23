"""Desktop screenshot portal integration."""
from __future__ import annotations

import os
import secrets
import shutil
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

def unique_screenshot_path(pictures_dir: str | Path, now: datetime | None = None) -> Path:
    folder = Path(pictures_dir).expanduser() / "Aurora"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    moment = now or datetime.now().astimezone()
    stamp = moment.strftime("%Y-%m-%d_%H-%M-%S-%f")
    candidate = folder / f"Aurora_{stamp}.png"
    suffix = 1
    while candidate.exists():
        candidate = folder / f"Aurora_{stamp}_{suffix}.png"
        suffix += 1
    return candidate


def save_screenshot_uri(uri: str, pictures_dir: str | Path, now: datetime | None = None,
                        cancel_event: threading.Event | None = None) -> Path:
    """Copy the local file URI returned by the desktop screenshot portal."""
    parsed = urllib.parse.urlsplit(str(uri))
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        raise ValueError("O portal não retornou um arquivo local.")
    source = Path(urllib.parse.unquote(parsed.path))
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("A captura foi cancelada; nenhum arquivo foi salvo.")
    if not source.is_file():
        raise FileNotFoundError("O arquivo temporário da captura não existe.")
    with source.open("rb") as incoming:
        target = None
        fd = None
        for _attempt in range(1000):
            candidate = unique_screenshot_path(pictures_dir, now)
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                target = candidate
                break
            except FileExistsError:
                continue
        if fd is None or target is None:
            raise FileExistsError("Não consegui reservar um nome exclusivo para a captura.")
        try:
            with os.fdopen(fd, "wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("A captura foi cancelada; nenhum arquivo foi salvo.")
        except Exception:
            target.unlink(missing_ok=True)
            raise
    os.chmod(target, 0o600)
    return target


def _portal_request_object_path(bus_name: str, token: str) -> str:
    sender = bus_name.replace(":", "_").replace(".", "_")
    return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"


def _portal_response_code_type() -> str:
    return "uint"


def _portal_response_slot() -> str:
    from PySide6.QtCore import SLOT
    return SLOT(f"receive({_portal_response_code_type()},QVariantMap)")


class ScreenshotPortalError(RuntimeError):
    """Screenshot error tagged with a safe diagnostic stage."""

    def __init__(self, phase: str, message: str):
        super().__init__(message)
        self.phase = phase


def _recover_gnome_saved_screenshot(pictures_dir: str | Path, request_started_at: float) -> Path | None:
    """Recover the sole new GNOME Screenshot file when its portal reply is lost."""
    root = Path(pictures_dir).expanduser()
    try:
        candidates = [
            path for path in root.iterdir()
            if path.is_file() and path.name.casefold().startswith("screenshot")
            and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}
            and path.stat().st_size > 0
            and path.stat().st_mtime >= request_started_at - 1.0
        ]
    except OSError:
        return None
    # Never guess if another screenshot appeared during the same interval.
    if len(candidates) != 1:
        return None
    try:
        return save_screenshot_uri(candidates[0].resolve().as_uri(), root)
    except (OSError, ValueError):
        return None


def _gnome_saved_screenshot_signature(pictures_dir: str | Path, request_started_at: float):
    """Return metadata for the only new GNOME screenshot, if unambiguous."""
    root = Path(pictures_dir).expanduser()
    try:
        candidates = [
            path for path in root.iterdir()
            if path.is_file() and path.name.casefold().startswith("screenshot")
            and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}
            and path.stat().st_size > 0
            and path.stat().st_mtime >= request_started_at - 1.0
        ]
        if len(candidates) != 1:
            return None
        path = candidates[0]
        stat = path.stat()
        return (str(path), stat.st_size, stat.st_mtime_ns)
    except OSError:
        return None


def screenshot_parent_identifier(window_id: int | str | None, platform: str = "xcb") -> str:
    """Format an X11 window ID for XDG portals, or return no parent."""
    if str(platform).casefold() != "xcb":
        return ""
    try:
        value = int(window_id)
    except (TypeError, ValueError):
        return ""
    return f"x11:{value:x}" if value > 0 else ""


def capture_screenshot(pictures_dir: str | Path, timeout: int = 45,
                       cancel_event: threading.Event | None = None,
                       parent_window: str = "") -> Path:
    """Request a full-screen capture through the XDG portal and save it safely."""
    try:
        from PySide6.QtCore import QEventLoop, QObject, QTimer, Slot
        from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage
    except ImportError as exc:
        raise ScreenshotPortalError("qt_dbus", "O suporte DBus do Qt não está instalado.") from exc
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise ScreenshotPortalError("session_bus", "Não conectei ao portal de captura da sessão gráfica.")
    token = "aurora_" + secrets.token_hex(8)
    # xdg-desktop-portal derives the Request object path from the caller's
    # unique bus name by replacing both ':' and '.' with '_'. Keeping the
    # leading underscore is required (for example :1.42 -> _1_42).
    request_path = _portal_request_object_path(bus.baseService(), token)
    result = {}
    loop = QEventLoop()

    class Response(QObject):
        @Slot(_portal_response_code_type(), "QVariantMap")
        def receive(self, code, data):
            result["code"] = int(code)
            result["data"] = dict(data)
            loop.quit()

    receiver = Response()
    # QDBusConnection.connect expects Qt's encoded SLOT() signature. A plain
    # method signature is silently mangled and leaves the response unhandled.
    slot = _portal_response_slot()
    if not bus.connect("org.freedesktop.portal.Desktop", request_path,
                       "org.freedesktop.portal.Request", "Response", receiver, slot):
        raise ScreenshotPortalError("subscribe", "Não consegui acompanhar a resposta do portal de captura.")
    message = QDBusMessage.createMethodCall(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot", "Screenshot")
    message.setArguments([str(parent_window or ""), {"handle_token": token, "interactive": False, "modal": True}])
    request_started_at = time.time()
    try:
        reply = bus.call(message, QDBus.CallMode.BlockWithGui, 5000)
    except Exception as exc:
        bus.disconnect("org.freedesktop.portal.Desktop", request_path,
                       "org.freedesktop.portal.Request", "Response", receiver, slot)
        raise ScreenshotPortalError("portal_request", "A chamada ao portal de captura falhou.") from exc
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        bus.disconnect("org.freedesktop.portal.Desktop", request_path,
                       "org.freedesktop.portal.Request", "Response", receiver, slot)
        raise ScreenshotPortalError("portal_request", reply.errorMessage() or "O portal recusou a captura.")
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    # GNOME may save its screenshot successfully but never deliver the portal
    # Response signal. Watch for the resulting file while the request is
    # pending, rather than waiting for the full 45-second timeout to recover it.
    recovery_timer = QTimer()
    recovery_timer.setInterval(100)
    recovery_state = {"signature": None, "stable": 0}
    def recover_when_file_is_ready():
        signature = _gnome_saved_screenshot_signature(pictures_dir, request_started_at)
        if signature is None:
            recovery_state.update(signature=None, stable=0)
            return
        if signature == recovery_state["signature"]:
            recovery_state["stable"] += 1
        else:
            recovery_state.update(signature=signature, stable=1)
        if recovery_state["stable"] < 2:
            return
        recovered = _recover_gnome_saved_screenshot(pictures_dir, request_started_at)
        if recovered:
            result["recovered"] = recovered
            loop.quit()
    recovery_timer.timeout.connect(recover_when_file_is_ready)
    cancelled = {"value": False}
    cancel_timer = QTimer()
    def cancel_if_requested():
        if cancel_event and cancel_event.is_set():
            cancelled["value"] = True
            close = QDBusMessage.createMethodCall(
                "org.freedesktop.portal.Desktop", request_path,
                "org.freedesktop.portal.Request", "Close")
            try:
                bus.call(close, QDBus.CallMode.Block, 500)
            except Exception:
                pass
            loop.quit()
    cancel_timer.timeout.connect(cancel_if_requested)
    cancel_timer.start(50)
    recovery_timer.start()
    timer.start(max(1, int(timeout)) * 1000)
    cancel_if_requested()
    if "code" not in result and not (cancel_event and cancel_event.is_set()):
        loop.exec()
    timer.stop()
    cancel_timer.stop()
    recovery_timer.stop()
    bus.disconnect("org.freedesktop.portal.Desktop", request_path,
                   "org.freedesktop.portal.Request", "Response", receiver, slot)
    if result.get("recovered"):
        return result["recovered"]
    if "code" not in result:
        recovered = _recover_gnome_saved_screenshot(pictures_dir, request_started_at)
        if recovered:
            return recovered
        if cancelled["value"] or (cancel_event and cancel_event.is_set()):
            raise ScreenshotPortalError("cancelled", "A captura foi cancelada; nenhum arquivo foi salvo.")
        raise ScreenshotPortalError("response_wait", "A captura expirou ou o portal aguarda uma ação do sistema.")
    if result["code"] != 0:
        raise ScreenshotPortalError("portal_response", "A captura foi cancelada pelo portal ou pelo usuário.")
    uri = result["data"].get("uri")
    if not uri:
        raise ScreenshotPortalError("portal_response", "O portal concluiu sem informar o arquivo da captura.")
    # A successful portal response is the capture's commit point. Finish the
    # local copy even if the user interrupts immediately afterwards; otherwise
    # a completed capture could be discarded and misreported as cancelled.
    try:
        return save_screenshot_uri(str(uri), pictures_dir)
    except Exception as exc:
        raise ScreenshotPortalError("save", str(exc)) from exc
