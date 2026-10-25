#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Render the original CC0 entry/exit sound signatures used by the onboarding."""
from __future__ import annotations

import math
import random
import wave
from pathlib import Path


RATE = 44_100
OUT = Path(__file__).resolve().parents[1] / "assets" / "audio"


def tone(buf, start, duration, low, high, gain, *, pan=0.0, harmonic=0.0,
         attack=0.025, release=0.20):
    begin = int(start * RATE)
    count = min(int(duration * RATE), len(buf) - begin)
    if count <= 0:
        return
    left_gain = math.sqrt((1.0 - pan) * 0.5)
    right_gain = math.sqrt((1.0 + pan) * 0.5)
    for n in range(count):
        t = n / RATE
        x = n / max(1, count - 1)
        freq = low * ((high / low) ** x)
        phase = 2 * math.pi * duration * (
            low * x + (high - low) * x * x / 2
        )
        envelope = min(1.0, t / max(attack, 0.001))
        envelope *= min(1.0, (duration - t) / max(release, 0.001))
        envelope *= math.exp(-1.25 * x)
        sample = math.sin(phase) + harmonic * math.sin(phase * 2.003 + .3)
        value = gain * envelope * sample
        buf[begin + n][0] += value * left_gain
        buf[begin + n][1] += value * right_gain


def noise_bloom(buf, start, duration, gain, *, seed, pan=0.0):
    rng = random.Random(seed)
    begin = int(start * RATE)
    count = min(int(duration * RATE), len(buf) - begin)
    left_gain = math.sqrt((1.0 - pan) * 0.5)
    right_gain = math.sqrt((1.0 + pan) * 0.5)
    previous = 0.0
    for n in range(max(0, count)):
        t = n / RATE
        x = n / max(1, count - 1)
        white = rng.uniform(-1.0, 1.0)
        previous = previous * .88 + white * .12
        envelope = min(1.0, t / .08) * min(1.0, (duration - t) / .28)
        value = previous * gain * envelope * (1.0 - .45 * x)
        buf[begin + n][0] += value * left_gain
        buf[begin + n][1] += value * right_gain


def make(theme, direction):
    duration = {
        ("boreal", "entrada"): .92, ("boreal", "saida"): .78,
        ("pulse", "entrada"): .74, ("pulse", "saida"): .68,
        ("void", "entrada"): 1.02, ("void", "saida"): .90,
    }[(theme, direction)]
    buf = [[0.0, 0.0] for _ in range(int(RATE * duration))]

    if theme == "boreal":
        if direction == "entrada":
            tone(buf, 0.00, .80, 390, 1180, .25, pan=-.18, harmonic=.24, attack=.09, release=.42)
            tone(buf, .13, .67, 920, 1560, .10, pan=.30, harmonic=.12, attack=.02, release=.43)
            tone(buf, .39, .36, 1780, 2380, .075, pan=.14, attack=.005, release=.30)
            noise_bloom(buf, 0, .60, .035, seed=17, pan=-.15)
        else:
            tone(buf, 0.00, .76, 1160, 370, .22, pan=.16, harmonic=.20, attack=.015, release=.50)
            tone(buf, .06, .60, 1880, 920, .085, pan=-.25, attack=.005, release=.42)
            tone(buf, .21, .49, 680, 290, .09, pan=.10, harmonic=.12, attack=.04, release=.40)
            noise_bloom(buf, .10, .58, .025, seed=21, pan=.22)
    elif theme == "pulse":
        if direction == "entrada":
            for start, freq, gain in ((.02, 94, .25), (.20, 132, .19), (.39, 176, .12)):
                tone(buf, start, .22, freq, freq * 1.18, gain, pan=-.08, harmonic=.52, attack=.004, release=.16)
            tone(buf, .05, .61, 250, 820, .12, pan=.18, harmonic=.10, attack=.03, release=.35)
            tone(buf, .37, .32, 930, 1480, .055, pan=-.24, attack=.003, release=.24)
        else:
            tone(buf, .00, .31, 166, 105, .27, pan=.08, harmonic=.50, attack=.005, release=.24)
            tone(buf, .19, .46, 610, 230, .10, pan=-.17, harmonic=.12, attack=.02, release=.35)
            tone(buf, .38, .27, 380, 180, .065, pan=.20, attack=.015, release=.22)
    else:
        if direction == "entrada":
            tone(buf, 0, .95, 74, 210, .27, pan=-.10, harmonic=.26, attack=.22, release=.46)
            tone(buf, .17, .80, 147, 294, .12, pan=.12, harmonic=.18, attack=.18, release=.42)
            tone(buf, .55, .43, 1180, 780, .075, pan=.34, harmonic=.10, attack=.008, release=.35)
            noise_bloom(buf, .08, .78, .045, seed=37, pan=-.28)
        else:
            tone(buf, .00, .88, 205, 58, .26, pan=.12, harmonic=.30, attack=.08, release=.60)
            tone(buf, .11, .73, 420, 116, .10, pan=-.14, harmonic=.18, attack=.04, release=.56)
            tone(buf, .45, .42, 970, 540, .065, pan=-.32, attack=.006, release=.37)
            noise_bloom(buf, .12, .70, .030, seed=41, pan=.24)

    peak = max((abs(channel) for frame in buf for channel in frame), default=1.0)
    scale = min(.82 / max(peak, 1e-6), 1.8)
    target = OUT / f"{direction}-{theme}.wav"
    with wave.open(str(target), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        frames = bytearray()
        for left, right in buf:
            for sample in (left * scale, right * scale):
                frames.extend(int(max(-1, min(1, sample)) * 32767).to_bytes(2, "little", signed=True))
        out.writeframes(frames)


if __name__ == "__main__":
    for theme in ("boreal", "pulse", "void"):
        for direction in ("entrada", "saida"):
            make(theme, direction)
            print(f"{direction}-{theme}.wav")
