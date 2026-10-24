# SPDX-License-Identifier: GPL-3.0-only
"""Wait for the XWayland display used by Aurora's XCB Qt backend."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import sys
import time
from collections.abc import Callable
from functools import lru_cache


@lru_cache(maxsize=1)
def _x11_library():
    library_name = ctypes.util.find_library("X11")
    if not library_name:
        return None
    try:
        x11 = ctypes.CDLL(library_name)
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.restype = ctypes.c_int
        return x11
    except (OSError, AttributeError):
        return None


def x11_display_available(display: str) -> bool:
    """Return whether the X server accepts an authenticated X11 connection."""
    try:
        x11 = _x11_library()
        if x11 is None:
            return False
        connection = x11.XOpenDisplay(display.encode())
        if not connection:
            return False
        x11.XCloseDisplay(connection)
        return True
    except (OSError, AttributeError, UnicodeError):
        return False


def wait_for_x11_display(
    display: str,
    *,
    timeout: float = 30.0,
    interval: float = 0.25,
    probe: Callable[[str], bool] = x11_display_available,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Wait a bounded time for XWayland to accept XCB connections."""
    if not display:
        raise ValueError("DISPLAY is not set; Aurora's XCB interface cannot start.")
    if timeout < 0 or interval <= 0:
        raise ValueError("timeout must be non-negative and interval must be positive")

    deadline = monotonic() + timeout
    while True:
        if probe(display):
            return True
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"X11 display {display!r} did not become available within {timeout:g} seconds."
            )
        sleep(min(interval, remaining))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("display", nargs="?", default=os.environ.get("DISPLAY", ""))
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        wait_for_x11_display(args.display, timeout=args.timeout)
    except (TimeoutError, ValueError) as exc:
        print(f"[aurora-startup] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
