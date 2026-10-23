"""Native X11 / libXtst mouse and keyboard input injection for remote desktop control.

Enables low-latency touch-to-mouse translation from companion mobile devices.
Supports normalized coordinates (0.0 to 1.0) mapped to screen resolution.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
from typing import Optional, Tuple

_lock = threading.Lock()

def ensure_gnome_remote_desktop_permissions():
    """Ensure GNOME allows remote desktop control, screen sharing and accessibility input."""
    import subprocess, shutil
    if not shutil.which("gsettings"):
        return
    commands = [
        ["gsettings", "set", "org.gnome.desktop.interface", "toolkit-accessibility", "true"],
        ["gsettings", "set", "org.gnome.desktop.remote-desktop.rdp", "view-only", "false"],
        ["gsettings", "set", "org.gnome.desktop.remote-desktop.rdp", "enable", "true"],
        ["gsettings", "set", "org.gnome.desktop.remote-desktop.vnc", "view-only", "false"],
        ["gsettings", "set", "org.gnome.desktop.remote-desktop.vnc", "enable", "true"],
    ]
    for cmd in commands:
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            pass

class _X11Input:
    def __init__(self):
        self.available = False
        ensure_gnome_remote_desktop_permissions()
        try:
            self.x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
            self.xtst = ctypes.cdll.LoadLibrary("libXtst.so.6")

            self.x11.XOpenDisplay.restype = ctypes.c_void_p
            self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self.x11.XDefaultScreen.restype = ctypes.c_int
            self.x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
            self.x11.XDisplayWidth.restype = ctypes.c_int
            self.x11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.x11.XDisplayHeight.restype = ctypes.c_int
            self.x11.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.x11.XFlush.argtypes = [ctypes.c_void_p]
            self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

            self.xtst.XTestFakeMotionEvent.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong
            ]
            self.xtst.XTestFakeButtonEvent.argtypes = [
                ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong
            ]

            display = self.x11.XOpenDisplay(None)
            if display:
                screen = self.x11.XDefaultScreen(display)
                self.width = int(self.x11.XDisplayWidth(display, screen))
                self.height = int(self.x11.XDisplayHeight(display, screen))
                self.x11.XCloseDisplay(display)
                self.available = True
            else:
                self.width = 1920
                self.height = 1080
        except Exception as exc:
            print(f"[remote_input] X11/Xtst initialization failed: {exc}", file=sys.stderr)
            self.width = 1920
            self.height = 1080

    def screen_size(self) -> Tuple[int, int]:
        return self.width, self.height

    def handle_input(self, action: str, norm_x: float, norm_y: float, button: int = 1, delta: float = 0.0) -> bool:
        if not self.available:
            return False

        with _lock:
            display = self.x11.XOpenDisplay(None)
            if not display:
                return False
            try:
                screen = self.x11.XDefaultScreen(display)
                # Clamp coordinates
                norm_x = max(0.0, min(1.0, norm_x))
                norm_y = max(0.0, min(1.0, norm_y))
                pixel_x = int(norm_x * self.width)
                pixel_y = int(norm_y * self.height)

                act = action.lower()
                if act in ("move", "hover"):
                    self.xtst.XTestFakeMotionEvent(display, screen, pixel_x, pixel_y, 0)
                elif act == "click":
                    self.xtst.XTestFakeMotionEvent(display, screen, pixel_x, pixel_y, 0)
                    self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(button), 1, 0) # Press
                    self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(button), 0, 15) # Release
                elif act == "double_click":
                    self.xtst.XTestFakeMotionEvent(display, screen, pixel_x, pixel_y, 0)
                    self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(button), 1, 0)
                    self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(button), 0, 15)
                    self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(button), 1, 30)
                    self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(button), 0, 45)
                elif act in ("down", "press"):
                    self.xtst.XTestFakeMotionEvent(display, screen, pixel_x, pixel_y, 0)
                    self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(button), 1, 0)
                elif act in ("up", "release"):
                    self.xtst.XTestFakeMotionEvent(display, screen, pixel_x, pixel_y, 0)
                    self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(button), 0, 0)
                elif act == "scroll":
                    btn = 4 if delta > 0 else 5 # Button 4 = Up, Button 5 = Down
                    clicks = max(1, min(10, int(abs(delta))))
                    for _ in range(clicks):
                        self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(btn), 1, 0)
                        self.xtst.XTestFakeButtonEvent(display, ctypes.c_uint(btn), 0, 5)

                self.x11.XFlush(display)
                return True
            finally:
                self.x11.XCloseDisplay(display)

_instance: Optional[_X11Input] = None

def get_input_injector() -> _X11Input:
    global _instance
    if _instance is None:
        _instance = _X11Input()
    return _instance

def inject_remote_event(action: str, x: float = 0.0, y: float = 0.0, button: int = 1, delta: float = 0.0) -> bool:
    return get_input_injector().handle_input(action, x, y, button, delta)
