# SPDX-License-Identifier: GPL-3.0-only
from array import array
import math

from aurora_core.voice.profile import enroll, matches, similarity


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


def test_wake_profile_does_not_match_silence():
    samples = [_tone(220, phase) for phase in (0.0, 0.08, 0.16)]
    profile = enroll("Luna", samples)
    silence = array("h", [0] * 25_600).tobytes()
    assert not matches(profile, silence)
