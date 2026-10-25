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


def chime(buf, start, duration, frequency, gain, *, pan=0.0, decay=5.0):
    """A small inharmonic glass strike with a soft fundamental and upper partials."""
    begin = int(start * RATE)
    count = min(int(duration * RATE), len(buf) - begin)
    left_gain = math.sqrt((1.0 - pan) * 0.5)
    right_gain = math.sqrt((1.0 + pan) * 0.5)
    partials = ((1.0, 1.0), (2.71, .28), (4.16, .12))
    for n in range(max(0, count)):
        t = n / RATE
        attack = min(1.0, t / .004)
        sample = sum(weight * math.sin(2 * math.pi * frequency * ratio * t)
                     * math.exp(-decay * t * (1 + .12 * index))
                     for index, (ratio, weight) in enumerate(partials))
        value = gain * attack * sample
        buf[begin + n][0] += value * left_gain
        buf[begin + n][1] += value * right_gain


def drop(buf, start, duration, frequency, gain, *, pan=0.0):
    """Rounded water-like blip: a fast upward bend followed by a falling tail."""
    begin = int(start * RATE)
    count = min(int(duration * RATE), len(buf) - begin)
    left_gain = math.sqrt((1.0 - pan) * 0.5)
    right_gain = math.sqrt((1.0 + pan) * 0.5)
    for n in range(max(0, count)):
        t = n / RATE
        x = t / max(duration, .001)
        freq = frequency * (1.0 + .62 * math.exp(-x * 17.0))
        phase = 2 * math.pi * (frequency * t + frequency * .62 * (1 - math.exp(-x * 17)) * duration / 17)
        envelope = (1 - math.exp(-x * 55)) * math.exp(-x * 4.5)
        sample = math.sin(phase) + .2 * math.sin(phase * 2.03 + .2)
        value = gain * envelope * sample
        buf[begin + n][0] += value * left_gain
        buf[begin + n][1] += value * right_gain


def make(theme, direction):
    duration = {
        ("boreal", "entrada"): .92, ("boreal", "saida"): .78,
        ("pulse", "entrada"): .74, ("pulse", "saida"): .68,
        ("void", "entrada"): 1.02, ("void", "saida"): .90,
        ("prisma", "entrada"): .92, ("prisma", "saida"): .86,
        ("marea", "entrada"): 1.00, ("marea", "saida"): .90,
        ("lumen", "entrada"): .86, ("lumen", "saida"): .82,
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
    elif theme == "void":
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
    elif theme == "prisma":
        # A glassy three-note signature, spatially stepping from left to right.
        if direction == "entrada":
            for start, freq, pan in ((.06, 659.25, -.30), (.25, 830.61, .05), (.45, 987.77, .30)):
                chime(buf, start, .48, freq, .14, pan=pan, decay=5.2)
            tone(buf, .05, .70, 330, 660, .045, harmonic=.18, attack=.03, release=.45)
        else:
            for start, freq, pan in ((.04, 987.77, .28), (.25, 830.61, 0), (.44, 659.25, -.28)):
                chime(buf, start, .46, freq, .12, pan=pan, decay=5.7)
            tone(buf, .04, .68, 660, 330, .04, harmonic=.16, attack=.02, release=.46)
    elif theme == "marea":
        # Rounded liquid blips over a soft, low tide-like swell.
        if direction == "entrada":
            tone(buf, .04, .86, 165, 247, .12, pan=-.12, harmonic=.20, attack=.16, release=.48)
            for start, freq, pan in ((.12, 520, -.24), (.34, 690, .12), (.57, 880, .30)):
                drop(buf, start, .34, freq, .13, pan=pan)
            noise_bloom(buf, .05, .68, .018, seed=53, pan=.16)
        else:
            tone(buf, .02, .78, 247, 146, .11, pan=.12, harmonic=.16, attack=.12, release=.50)
            for start, freq, pan in ((.06, 880, .26), (.28, 660, -.05), (.50, 494, -.28)):
                drop(buf, start, .30, freq, .11, pan=pan)
            noise_bloom(buf, .08, .62, .014, seed=59, pan=-.15)
    else:  # lumen
        # A warm, rounded two-tone beacon with a slow, even amplitude swell.
        if direction == "entrada":
            for start, freq, gain, pan in ((.00, 392.0, .15, -.18), (.16, 523.25, .12, .12), (.34, 783.99, .10, .26)):
                tone(buf, start, .50, freq, freq * 1.015, gain, pan=pan, harmonic=.32, attack=.08, release=.32)
            tone(buf, .08, .68, 196, 392, .075, pan=0, harmonic=.08, attack=.12, release=.38)
        else:
            for start, freq, gain, pan in ((.00, 783.99, .10, .24), (.18, 523.25, .12, 0), (.36, 392.0, .14, -.22)):
                tone(buf, start, .46, freq, freq * .985, gain, pan=pan, harmonic=.28, attack=.06, release=.32)
            tone(buf, .06, .66, 392, 196, .07, pan=0, harmonic=.08, attack=.10, release=.40)

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
    for theme in ("boreal", "pulse", "void", "prisma", "marea", "lumen"):
        for direction in ("entrada", "saida"):
            make(theme, direction)
            print(f"{direction}-{theme}.wav")
