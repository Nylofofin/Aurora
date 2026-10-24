# SPDX-License-Identifier: GPL-3.0-only

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "wait_for_x11.py"
SPEC = importlib.util.spec_from_file_location("wait_for_x11", SCRIPT)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_display_wait_returns_when_xwayland_accepts_connection():
    probes = iter((False, False, True))
    sleeps = []

    assert MODULE.wait_for_x11_display(
        ":0",
        timeout=5,
        interval=0.25,
        probe=lambda display: next(probes),
        monotonic=iter((0, 0, 0, 0, 0)).__next__,
        sleep=sleeps.append,
    )
    assert sleeps == [0.25, 0.25]


def test_display_wait_times_out_instead_of_spinning_forever():
    clock = iter((10.0, 10.0, 10.5, 11.0)).__next__
    sleeps = []

    with pytest.raises(TimeoutError, match="did not become available"):
        MODULE.wait_for_x11_display(
            ":0",
            timeout=1,
            interval=0.5,
            probe=lambda display: False,
            monotonic=clock,
            sleep=sleeps.append,
        )

    assert sleeps == [0.5, 0.5]


def test_missing_display_fails_immediately():
    with pytest.raises(ValueError, match="DISPLAY is not set"):
        MODULE.wait_for_x11_display("")


def test_x11_probe_closes_successful_connection(monkeypatch):
    closed = []

    class FakeX11:
        def __init__(self):
            self.XOpenDisplay = lambda display: 123
            self.XCloseDisplay = lambda connection: closed.append(connection) or 0

    MODULE._x11_library.cache_clear()
    monkeypatch.setattr(MODULE.ctypes.util, "find_library", lambda name: "libX11.so")
    monkeypatch.setattr(MODULE.ctypes, "CDLL", lambda name: FakeX11())

    assert MODULE.x11_display_available(":0")
    assert closed == [123]
    MODULE._x11_library.cache_clear()
