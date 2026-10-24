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
PROFILE_VERSION = 1


def _samples(pcm: bytes) -> list[float]:
    values = array("h")
    values.frombytes(bytes(pcm))
    if __import__("sys").byteorder != "little":
        values.byteswap()
    return [sample / 32768.0 for sample in values]


def feature_vector(pcm: bytes) -> list[float]:
    """Return a compact, scale-normalized voice signature for ``pcm``."""
    values = _samples(pcm)
    if not values:
        return []
    required = FRAME_SAMPLES * FRAME_COUNT
    if len(values) < required:
        values += [0.0] * (required - len(values))
    values = values[:required]
    vector: list[float] = []
    for frame_index in range(FRAME_COUNT):
        frame = values[frame_index * FRAME_SAMPLES:(frame_index + 1) * FRAME_SAMPLES]
        rms = math.sqrt(sum(sample * sample for sample in frame) / len(frame))
        crossings = sum(1 for left, right in zip(frame, frame[1:]) if (left < 0) != (right < 0)) / len(frame)
        vector.extend((min(1.0, rms * 8.0), min(1.0, crossings * 3.0)))
        # A few stable spectral samples distinguish phonemes without pulling
        # in a heavyweight ML dependency in the always-on microphone thread.
        for frequency in (180, 420, 760, 1200, 1900, 2800):
            step = 2.0 * math.pi * frequency / SAMPLE_RATE
            real = sum(sample * math.cos(step * index) for index, sample in enumerate(frame)) / len(frame)
            imag = sum(sample * math.sin(step * index) for index, sample in enumerate(frame)) / len(frame)
            vector.append(min(1.0, math.sqrt(real * real + imag * imag) * 18.0))
    return vector


def enroll(name: str, recordings: list[bytes]) -> dict:
    vectors = [feature_vector(recording) for recording in recordings]
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
    centroid = profile.get("centroid") if isinstance(profile, dict) else None
    vector = feature_vector(pcm)
    if not isinstance(centroid, list) or not vector or len(centroid) != len(vector):
        return 0.0
    distance = sum(abs(float(left) - float(right)) for left, right in zip(centroid, vector)) / len(vector)
    return max(0.0, 1.0 - distance * 2.4)


def matches(profile: dict, pcm: bytes, threshold: float = 0.78) -> bool:
    return similarity(profile, pcm) >= threshold
