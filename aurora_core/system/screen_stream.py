"""Consent-gated desktop stream and touch input through XDG portals/PipeWire."""
from __future__ import annotations

import shutil
import json
import struct
import subprocess
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
        self._worker_lock = threading.Lock()

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

    def send_input(self, event):
        """Send one validated pointer event to the active portal session."""
        with self._worker_lock:
            process = self._worker
            if self.state != "streaming" or process is None or process.poll() is not None or process.stdin is None:
                return False
            try:
                process.stdin.write((json.dumps(event, separators=(",", ":")) + "\n").encode("utf-8"))
                process.stdin.flush()
                return True
            except (BrokenPipeError, OSError, ValueError):
                return False

    def _capture(self):
        # The system-python adapter owns both the screen stream and the
        # consent-gated RemoteDesktop session, so the screen and touch input
        # use the same portal-approved stream on Wayland and X11.
        self._capture_system_worker()

    def _capture_system_worker(self):
        worker = Path(__file__).with_name("screen_stream_worker.py")
        interpreter = shutil.which("python3")
        if not interpreter or not worker.is_file():
            self._set_state("error", "A captura requer Python do sistema com PyGObject, dbus-python e GStreamer PipeWire.")
            return
        process = subprocess.Popen(
            [interpreter, str(worker), str(self.width), str(self.fps)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
        )
        with self._worker_lock:
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
                    self._state = "streaming"
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
            with self._worker_lock:
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
