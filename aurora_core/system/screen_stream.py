"""Consent-gated, view-only desktop stream through the XDG portal and PipeWire."""
from __future__ import annotations

import secrets
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path


class DesktopScreenStream:
    """Captures low-rate JPEG frames only after the desktop portal grants a session."""

    def __init__(self, width: int = 960, fps: int = 4):
        self.width = max(320, min(int(width), 1600))
        self.fps = max(1, min(int(fps), 8))
        self._condition = threading.Condition()
        self._thread = None
        self._stop = threading.Event()
        self._frame = b""
        self._frame_number = 0
        self._error = ""
        self._state = "idle"
        self._viewer_last_seen = 0.0
        self._worker = None

    @property
    def state(self):
        with self._condition:
            return self._state

    def start(self):
        with self._condition:
            if self._state in {"starting", "streaming"}:
                return self._state
            self._frame = b""
            self._error = ""
            self._state = "starting"
            self._viewer_last_seen = time.monotonic()
            self._stop.clear()
            self._thread = threading.Thread(target=self._capture, name="aurora-screen-cast", daemon=True)
            self._thread.start()
            return self._state

    def stop(self):
        self._stop.set()
        with self._condition:
            self._frame = b""
            self._state = "stopping"
            self._condition.notify_all()

    def frame_after(self, frame_number: int = 0, timeout: float = 2.0):
        with self._condition:
            self._viewer_last_seen = time.monotonic()
            self._condition.wait_for(
                lambda: self._frame_number > frame_number or bool(self._error) or self._state in {"idle", "stopping"},
                timeout=max(.1, min(float(timeout), 3.0)),
            )
            if self._error:
                raise RuntimeError(self._error)
            if not self._frame or self._state != "streaming":
                return self._frame_number, b""
            return self._frame_number, self._frame

    def _set_state(self, state, error=""):
        with self._condition:
            self._state = state
            if error:
                self._error = error
            self._condition.notify_all()

    @staticmethod
    def _portal_response(bus, request_path, timeout=30):
        from gi.repository import GLib

        loop = GLib.MainLoop()
        result = {}
        def received(code, data):
            result["code"] = int(code)
            result["data"] = dict(data)
            if loop.is_running(): loop.quit()
        receiver = bus.add_signal_receiver(
            received, signal_name="Response", dbus_interface="org.freedesktop.portal.Request",
            path=request_path,
        )
        timer = GLib.timeout_add(int(timeout * 1000), lambda: (loop.quit(), False)[1])
        try:
            loop.run()
        finally:
            GLib.source_remove(timer)
            receiver.remove()
        if "code" not in result:
            raise TimeoutError("O portal não respondeu à solicitação de compartilhamento.")
        if result["code"] != 0:
            raise PermissionError("O compartilhamento da tela foi recusado ou cancelado no desktop.")
        return result["data"]

    def _capture(self):
        # Fedora's PyGObject/dbus bindings are built for the system interpreter
        # and usually are not importable from Aurora's isolated venv. Keep the
        # service isolated and run only the portal/PipeWire adapter there.
        try:
            import gi  # noqa: F401
            import dbus  # noqa: F401
        except ImportError:
            self._capture_system_worker()
            return

        pipeline = None
        bus = None
        dbus = None
        Gst = None
        session_path = None
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            import gi
            gi.require_version("Gst", "1.0")
            gi.require_version("GstApp", "1.0")
            from gi.repository import Gst
            DBusGMainLoop(set_as_default=True)
            Gst.init(None)
            bus = dbus.SessionBus()
            portal = dbus.Interface(
                bus.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"),
                "org.freedesktop.portal.ScreenCast",
            )
            token = "aurora_" + secrets.token_hex(8)
            request = portal.CreateSession({"handle_token": token, "session_handle_token": token + "_session"})
            data = self._portal_response(bus, request)
            session_path = str(data["session_handle"])
            request = portal.SelectSources(session_path, {
                "handle_token": token + "_sources", "types": dbus.UInt32(1),
                "multiple": False, "cursor_mode": dbus.UInt32(2),
            })
            self._portal_response(bus, request)
            request = portal.Start(session_path, "", {"handle_token": token + "_start"})
            data = self._portal_response(bus, request)
            streams = data.get("streams", [])
            if not streams:
                raise RuntimeError("O portal não retornou uma tela para transmitir.")
            node_id = int(streams[0][0])
            remote_fd = portal.OpenPipeWireRemote(session_path, {})
            fd = remote_fd.take() if hasattr(remote_fd, "take") else int(remote_fd)
            desc = (
                f"pipewiresrc fd={fd} path={node_id} do-timestamp=true ! videoconvert ! videoscale ! "
                f"video/x-raw,width={self.width},framerate={self.fps}/1 ! jpegenc quality=58 ! "
                "appsink name=aurora_sink max-buffers=1 drop=true sync=false"
            )
            pipeline = Gst.parse_launch(desc)
            sink = pipeline.get_by_name("aurora_sink")
            if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Não consegui iniciar o fluxo PipeWire.")
            self._set_state("streaming")
            while not self._stop.is_set() and time.monotonic() - self._viewer_last_seen < 30:
                sample = sink.emit("try-pull-sample", 1_000_000_000)
                if sample is None:
                    continue
                buffer = sample.get_buffer()
                success, mapping = buffer.map(Gst.MapFlags.READ)
                if not success:
                    continue
                try:
                    frame = bytes(mapping.data)
                finally:
                    buffer.unmap(mapping)
                if len(frame) > 2_000_000:
                    continue
                with self._condition:
                    self._frame = frame
                    self._frame_number += 1
                    self._condition.notify_all()
        except Exception as exc:
            self._set_state("error", str(exc) or type(exc).__name__)
        finally:
            if pipeline is not None:
                pipeline.set_state(Gst.State.NULL)
            if session_path and bus is not None:
                try:
                    session = dbus.Interface(bus.get_object("org.freedesktop.portal.Desktop", session_path),
                                              "org.freedesktop.portal.Session")
                    session.Close()
                except Exception:
                    pass
            if not self._error:
                self._set_state("idle")

    def _capture_system_worker(self):
        worker = Path(__file__).with_name("screen_stream_worker.py")
        interpreter = shutil.which("python3")
        if not interpreter or not worker.is_file():
            self._set_state("error", "A captura requer Python do sistema com PyGObject, dbus-python e GStreamer PipeWire.")
            return
        process = subprocess.Popen(
            [interpreter, str(worker), str(self.width), str(self.fps)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
        )
        self._worker = process
        stderr_lines = []
        def read_stderr():
            for line in iter(process.stderr.readline, b""):
                text = line.decode("utf-8", "replace").strip()
                if text:
                    stderr_lines.append(text[:500])
                    del stderr_lines[:-8]
        error_reader = threading.Thread(target=read_stderr, name="aurora-screen-stderr", daemon=True)
        error_reader.start()
        try:
            self._set_state("streaming")
            while not self._stop.is_set() and time.monotonic() - self._viewer_last_seen < 30:
                header = self._read_exact(process.stdout, 4)
                if not header:
                    break
                size = struct.unpack(">I", header)[0]
                if not 1 <= size <= 2_000_000:
                    raise RuntimeError("O worker de tela enviou um quadro inválido.")
                frame = self._read_exact(process.stdout, size)
                if not frame:
                    raise RuntimeError("A conexão com o worker de tela foi interrompida.")
                with self._condition:
                    self._frame = frame
                    self._frame_number += 1
                    self._condition.notify_all()
            if not self._stop.is_set():
                detail = " ".join(stderr_lines).strip()
                raise RuntimeError(detail or "A captura de tela terminou inesperadamente.")
        except Exception as exc:
            if not self._stop.is_set():
                self._set_state("error", str(exc) or type(exc).__name__)
        finally:
            if process.poll() is None:
                process.send_signal(2)  # SIGINT lets the worker close the portal session.
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            self._worker = None
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
            if not self._error:
                self._set_state("idle")

    @staticmethod
    def _read_exact(stream, size):
        chunks = bytearray()
        while len(chunks) < size:
            data = stream.read(size - len(chunks))
            if not data:
                return b""
            chunks.extend(data)
        return bytes(chunks)
