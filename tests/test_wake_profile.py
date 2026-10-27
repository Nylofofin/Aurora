# SPDX-License-Identifier: GPL-3.0-only
from array import array
import math
import pytest

from aurora_core.voice.profile import enroll, matches, similarity, validate_recording


def _tone(frequency, phase=0.0):
    return array("h", [int(9000 * math.sin(2 * math.pi * frequency * i / 16_000 + phase)) for i in range(25_600)]).tobytes()


def test_wake_profile_keeps_only_features_and_matches_enrolled_voice():
    samples = [_tone(220, phase) for phase in (0.0, 0.08, 0.16, 0.24)]
    profile = enroll("Luna", samples)
    assert profile["name"] == "Luna"
    assert profile["samples"] == 4
    assert "audio" not in profile
    assert similarity(profile, samples[0]) > 0.95
    assert matches(profile, samples[0])


def test_wake_profile_ignores_recording_silence_and_pace_alignment():
    samples = [_tone(220, phase) for phase in (0.0, 0.08, 0.16, 0.24)]
    profile = enroll("Luna", samples)
    speech = _tone(220, 0.08)
    padded = bytes(16_000 * 2 // 2) + speech + bytes(16_000 * 2 // 2)
    assert matches(profile, padded)


def test_legacy_profile_remains_usable_after_feature_upgrade():
    samples = [_tone(220, phase) for phase in (0.0, 0.08, 0.16)]
    current = enroll("Luna", samples)
    legacy = {**current, "version": 1}
    assert matches(legacy, samples[0])


def test_wake_profile_does_not_match_silence():
    samples = [_tone(220, phase) for phase in (0.0, 0.08, 0.16)]
    profile = enroll("Luna", samples)
    silence = array("h", [0] * 25_600).tobytes()
    assert not matches(profile, silence)


def test_wake_profile_rejects_low_energy_microphone_floor():
    samples = [_tone(220, phase) for phase in (0.0, 0.08, 0.16)]
    profile = enroll("Luna", samples)
    quiet = array("h", [200] * 25_600).tobytes()
    assert not matches(profile, quiet)


def test_wake_profile_requires_energy_above_room_floor():
    samples = [_tone(220, phase) for phase in (0.0, 0.08, 0.16)]
    profile = enroll("Luna", samples)
    room_floor = array("h", [500] * 25_600).tobytes()
    assert not matches(profile, room_floor)


def test_wake_training_rejects_silence_and_incomplete_audio():
    assert validate_recording(bytes(16_000 * 2))[0] is False
    assert validate_recording(b"\x01")[0] is False


def test_wake_training_accepts_a_clear_recording():
    valid, message = validate_recording(_tone(220, 0.0))
    assert valid is True
    assert "válida" in message


def test_wake_training_rejects_clipped_recording():
    clipped = array("h", [32767 if index % 2 else -32768 for index in range(25_600)]).tobytes()
    valid, message = validate_recording(clipped)
    assert valid is False
    assert "distorceu" in message


def test_enrollment_does_not_build_a_profile_from_silent_takes():
    with pytest.raises(ValueError, match="pelo menos três"):
        enroll("Luna", [bytes(16_000 * 2)] * 4)
