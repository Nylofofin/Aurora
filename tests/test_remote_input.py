import pytest

from aurora_core.system.remote_input import validate_remote_event


def test_remote_pointer_event_accepts_normalized_touch_coordinates():
    assert validate_remote_event("click", 0.25, 0.75, button=1) == {
        "action": "click", "x": 0.25, "y": 0.75, "button": 1, "delta": 0.0,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action": "shell", "x": 0.2, "y": 0.2},
        {"action": "click", "x": -0.1, "y": 0.2},
        {"action": "click", "x": 0.1, "y": float("nan")},
        {"action": "click", "x": 0.1, "y": 0.2, "button": 9},
        {"action": "scroll", "x": 0.1, "y": 0.2, "delta": 99},
    ],
)
def test_remote_pointer_event_rejects_invalid_input(kwargs):
    with pytest.raises(ValueError):
        validate_remote_event(**kwargs)
