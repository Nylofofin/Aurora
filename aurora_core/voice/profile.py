# SPDX-License-Identifier: GPL-3.0-only
"""Small local wake-profile enrollment and matching helpers.

The profile is deliberately audio-free after enrollment: only normalized
acoustic features are persisted in the user's private settings. It is a
fallback for custom names that are absent from the Vosk vocabulary; Vosk and
its exact-phrase gate remain the primary detector.
"""
from __future__ import annotations

from array import array
import math


SAMPLE_RATE = 16_000
FRAME_SAMPLES = 400  # 25 ms
FRAME_COUNT = 48
PROFILE_VERSION = 2
MIN_MATCH_RMS = 0.02
MIN_ENROLL_RMS = 0.008
MIN_VOICED_FRAMES = 4
MAX_CLIPPED_RATIO = 0.02
_SPECTRAL_FREQUENCIES = (180, 420, 760, 1200, 1900, 2800)
# These coefficients are shared across every frame. Calculating trig functions
# inside the always-on microphone loop made custom wake checks unnecessarily
# expensive and could make its small PCM queue fall behind.
_SPECTRAL_COEFFICIENTS = tuple(
    (
        tuple(math.cos(2.0 * math.pi * frequency * index / SAMPLE_RATE)
              for index in range(FRAME_SAMPLES)),
        tuple(math.sin(2.0 * math.pi * frequency * index / SAMPLE_RATE)
              for index in range(FRAME_SAMPLES)),
    )
    for frequency in _SPECTRAL_FREQUENCIES
)


def _samples(pcm: bytes) -> list[float]:
    values = array("h")
    values.frombytes(bytes(pcm))
    if __import__("sys").byteorder != "little":
        values.byteswap()
    return [sample / 32768.0 for sample in values]


def validate_recording(pcm: bytes) -> tuple[bool, str]:
    """Reject unusable enrollment takes before they poison a local profile."""
    raw = bytes(pcm or b"")
    if len(raw) % 2:
        return False, "A gravação ficou incompleta. Tente novamente."
    values = _samples(raw)
    if len(values) < FRAME_SAMPLES * 8:
        return False, "A gravação ficou curta demais. Tente novamente."
    frame_rms = []
    for start in range(0, len(values) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        frame = values[start:start + FRAME_SAMPLES]
        frame_rms.append(math.sqrt(sum(sample * sample for sample in frame) / len(frame)))
    peak = max(frame_rms, default=0.0)
    threshold = max(MIN_ENROLL_RMS, peak * 0.12)
    voiced_indices = [index for index, level in enumerate(frame_rms) if level >= threshold]
    if peak < MIN_ENROLL_RMS:
        return False, "Não ouvi o nome com clareza. Fale um pouco mais perto do microfone e tente novamente."
    clipped = sum(abs(sample) >= 0.995 for sample in values) / len(values)
    if clipped > MAX_CLIPPED_RATIO:
        return False, "O áudio distorceu. Afaste um pouco o microfone e tente novamente."
    if len(voiced_indices) < MIN_VOICED_FRAMES:
        return False, "Não consegui distinguir a fala do silêncio. Grave o nome novamente."
    if len(voiced_indices) / (SAMPLE_RATE / FRAME_SAMPLES) < 0.16:
        return False, "A fala ficou curta demais para comparar. Repita o nome uma vez."
    return True, "Amostra de voz válida."


def _voiced_frames(values: list[float]) -> list[list[float]]:
    frames = [values[start:start + FRAME_SAMPLES]
              for start in range(0, len(values) - FRAME_SAMPLES + 1, FRAME_SAMPLES)]
    levels = [math.sqrt(sum(sample * sample for sample in frame) / len(frame)) for frame in frames]
    peak = max(levels, default=0.0)
    if peak < MIN_ENROLL_RMS:
        return []
    threshold = max(MIN_ENROLL_RMS, peak * 0.12)
    active = [index for index, level in enumerate(levels) if level >= threshold]
    if not active:
        return []
    # Keep a small amount of consonant onset/decay while dropping the long
    # recording silence. This makes enrollment independent of when the user
    # starts speaking inside the capture window.
    first, last = max(0, active[0] - 2), min(len(frames), active[-1] + 3)
    return frames[first:last]


def feature_vector(pcm: bytes) -> list[float]:
    """Return a time-normalized acoustic template of the spoken wake phrase."""
    values = _samples(pcm)
    if not values:
        return []
    frames = _voiced_frames(values)
    if len(frames) < MIN_VOICED_FRAMES:
        return []
    # Recordings vary in speaking pace. Resample voiced 25 ms frames into a
    # fixed-length sequence so comparisons preserve phoneme order without a
    # heavy ML runtime or storing microphone audio.
    source_count = len(frames)
    normalized_frames = []
    for target_index in range(FRAME_COUNT):
        source_position = target_index * (source_count - 1) / max(1, FRAME_COUNT - 1)
        lower = int(source_position)
        upper = min(source_count - 1, lower + 1)
        fraction = source_position - lower
        normalized_frames.append([
            frames[lower][sample] * (1.0 - fraction) + frames[upper][sample] * fraction
            for sample in range(FRAME_SAMPLES)
        ])
    vector: list[float] = []
    for frame_index in range(FRAME_COUNT):
        frame = normalized_frames[frame_index]
        rms = math.sqrt(sum(sample * sample for sample in frame) / len(frame))
        crossings = sum(1 for left, right in zip(frame, frame[1:]) if (left < 0) != (right < 0)) / len(frame)
        vector.extend((min(1.0, rms * 8.0), min(1.0, crossings * 3.0)))
        # A few stable spectral samples distinguish phonemes without pulling
        # in a heavyweight ML dependency in the always-on microphone thread.
        for cosine, sine in _SPECTRAL_COEFFICIENTS:
            real = sum(sample * coefficient for sample, coefficient in zip(frame, cosine)) / len(frame)
            imag = sum(sample * coefficient for sample, coefficient in zip(frame, sine)) / len(frame)
            magnitude = math.sqrt(real * real + imag * imag)
            vector.append(min(1.0, magnitude / max(rms, 0.01) * 5.0))
    return vector


def _legacy_feature_vector(pcm: bytes) -> list[float]:
    """Version-1 signature reader so existing enrolled users keep working."""
    values = _samples(pcm)
    if not values:
        return []
    required = FRAME_SAMPLES * FRAME_COUNT
    values = (values + [0.0] * max(0, required - len(values)))[:required]
    vector: list[float] = []
    for frame_index in range(FRAME_COUNT):
        frame = values[frame_index * FRAME_SAMPLES:(frame_index + 1) * FRAME_SAMPLES]
        rms = math.sqrt(sum(sample * sample for sample in frame) / len(frame))
        crossings = sum(1 for left, right in zip(frame, frame[1:]) if (left < 0) != (right < 0)) / len(frame)
        vector.extend((min(1.0, rms * 8.0), min(1.0, crossings * 3.0)))
        for cosine, sine in _SPECTRAL_COEFFICIENTS:
            real = sum(sample * coefficient for sample, coefficient in zip(frame, cosine)) / len(frame)
            imag = sum(sample * coefficient for sample, coefficient in zip(frame, sine)) / len(frame)
            vector.append(min(1.0, math.sqrt(real * real + imag * imag) * 18.0))
    return vector


def enroll(name: str, recordings: list[bytes]) -> dict:
    vectors = [feature_vector(recording) for recording in recordings
               if validate_recording(recording)[0]]
    vectors = [vector for vector in vectors if vector]
    if len(vectors) < 3:
        raise ValueError("São necessárias pelo menos três amostras de voz.")
    width = min(map(len, vectors))
    centroid = [sum(vector[index] for vector in vectors) / len(vectors) for index in range(width)]
    return {
        "version": PROFILE_VERSION,
        "name": " ".join(str(name or "").split())[:80],
        "samples": len(vectors),
        "centroid": [round(value, 6) for value in centroid],
    }


def similarity(profile: dict, pcm: bytes) -> float:
    if not isinstance(profile, dict):
        return 0.0
    version = profile.get("version", 1)
    centroid = profile.get("centroid") if isinstance(profile, dict) else None
    vector = feature_vector(pcm) if version == PROFILE_VERSION else (
        _legacy_feature_vector(pcm) if version == 1 else [])
    if not isinstance(centroid, list) or not vector or len(centroid) != len(vector):
        return 0.0
    distance = sum(abs(float(left) - float(right)) for left, right in zip(centroid, vector)) / len(vector)
    return max(0.0, 1.0 - distance * 2.4)


def matches(profile: dict, pcm: bytes, threshold: float = 0.78) -> bool:
    # A low-energy window can otherwise resemble a quiet custom profile
    # after normalization. Never wake from silence or room-floor noise.
    values = _samples(pcm)
    if not values:
        return False
    rms = math.sqrt(sum(sample * sample for sample in values) / len(values))
    if rms < MIN_MATCH_RMS:
        return False
    return similarity(profile, pcm) >= threshold
