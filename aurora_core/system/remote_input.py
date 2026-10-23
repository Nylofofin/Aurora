"""Validation for consent-gated XDG RemoteDesktop pointer events."""
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import math

_ACTIONS = {"move", "click", "double_click", "down", "up", "scroll"}
_BUTTONS = {1, 2, 3}


def validate_remote_event(action, x, y, button=1, delta=0.0):
    """Return a normalized pointer event or raise ValueError for invalid input."""
    action = str(action).lower()
    if action not in _ACTIONS:
        raise ValueError("unsupported remote input action")
    x, y, delta = float(x), float(y), float(delta)
    button = int(button)
    if not all(math.isfinite(value) for value in (x, y, delta)):
        raise ValueError("non-finite remote input coordinate")
    if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
        raise ValueError("remote input coordinates must be normalized")
    if button not in _BUTTONS:
        raise ValueError("unsupported pointer button")
    if action == "scroll" and abs(delta) > 10:
        raise ValueError("scroll delta is too large")
    return {"action": action, "x": x, "y": y, "button": button, "delta": delta}
