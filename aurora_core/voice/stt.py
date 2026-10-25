# SPDX-License-Identifier: GPL-3.0-only
"""Private, offline command transcription using whisper.cpp."""
from __future__ import annotations

import os
import threading
import ctypes
import math
from pathlib import Path

from ..config import STT_MODEL_PATH

SAMPLE_RATE = 16_000
_MODEL_LOCK = threading.Lock()
_TRANSCRIBE_LOCK = threading.Lock()
_MODEL = None


def _thread_count() -> int:
    """Use the available cores for the short, latency-sensitive decode burst."""
    return max(1, min(4, os.cpu_count() or 1))


def _trim_silence(samples):
    """Trim quiet edges while retaining enough margin for soft consonants."""
    import numpy as np

    frame_size = SAMPLE_RATE // 50  # 20 ms
    frame_count = samples.size // frame_size
    if frame_count < 25:
        return samples
    framed = samples[:frame_count * frame_size].astype(np.float32).reshape(-1, frame_size)
    levels = np.sqrt(np.mean(framed * framed, axis=1))
    noise_floor = float(np.percentile(levels, 20))
    threshold = max(140.0, min(320.0, noise_floor * 1.7))
    active = np.flatnonzero(levels >= threshold)
    if active.size == 0:
        return samples

    # Whisper's encoder runs a 30-second context by default. Keeping the actual
    # utterance edges makes the duration-based context below much smaller.
    margin = int(SAMPLE_RATE * 0.4)
    start = max(0, int(active[0]) * frame_size - margin)
    end = min(samples.size, (int(active[-1]) + 1) * frame_size + margin)
    if end - start < SAMPLE_RATE // 5:
        return samples
    return samples[start:end]


def _audio_context(sample_count: int) -> int:
    """Scale Whisper's encoder context to speech duration with a short-command floor."""
    # whisper.cpp uses 1500 context tokens for 30 seconds (50 tokens/s).
    # Keep 1.28 seconds of headroom, and a 5.12 second floor for short speech.
    # The old 512-token floor forced 10.24 seconds of encoder context even for
    # 2-4 second commands, wasting CPU without improving our local samples.
    duration = sample_count / SAMPLE_RATE
    return min(1500, max(256, math.ceil(duration * 50) + 64))


def _get_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            if not STT_MODEL_PATH.is_file() or STT_MODEL_PATH.stat().st_size < 20_000_000:
                raise RuntimeError(
                    "O modelo local de transcrição não está pronto. "
                    "Execute setup-voice.sh para instalá-lo."
                )
            try:
                # Source builds install whisper.cpp's shared libraries beside
                # the package extension. Load them first so the user service
                # does not need a process-wide LD_LIBRARY_PATH override.
                import pywhispercpp
                library_dir = Path(pywhispercpp.__file__).resolve().parent.parent
                for library in (
                    "libggml-base.so.0",
                    "libggml-cpu.so.0",
                    "libggml.so.0",
                    "libwhisper.so.1",
                ):
                    path = library_dir / library
                    if not path.is_file():
                        raise RuntimeError(f"Biblioteca local do Whisper ausente: {library}")
                    ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
                from pywhispercpp.model import Model
            except ImportError as exc:
                raise RuntimeError(
                    "O runtime Whisper.cpp não está instalado. Execute run.sh --setup-only."
                ) from exc
            _MODEL = Model(
                str(STT_MODEL_PATH),
                n_threads=_thread_count(),
                language="pt",
                no_context=True,
                no_timestamps=True,
                context_params={"use_gpu": False, "flash_attn": False},
                print_progress=False,
                print_realtime=False,
                suppress_nst=True,
                redirect_whispercpp_logs_to=None,
            )
    return _MODEL


def transcribe_pcm(pcm: bytes, sample_rate: int = SAMPLE_RATE, assistant_name: str = "Aurora") -> str:
    """Decode signed 16-bit mono PCM locally; audio never leaves this process."""
    if sample_rate != SAMPLE_RATE:
        raise ValueError("O áudio de reconhecimento precisa estar em 16 kHz")
    if not isinstance(pcm, (bytes, bytearray, memoryview)) or len(pcm) % 2:
        raise ValueError("O áudio de reconhecimento precisa ser PCM de 16 bits")

    import numpy as np

    samples = np.frombuffer(pcm, dtype="<i2")
    if samples.size < SAMPLE_RATE // 5:
        return ""
    # Trim quiet edges before the silence check: a short but quiet phrase in a
    # long microphone window should not have its energy diluted by room silence.
    samples = _trim_silence(samples)
    # Whisper can hallucinate a plausible sentence from digital silence. Reject
    # near-silent windows before inference; this also avoids wasting CPU while
    # the Vosk wake recognizer is listening to room tone.
    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
    if rms < 120.0:
        return ""
    # whisper.cpp's Python API takes mono float samples in [-1, 1]. Keep the
    # conversion in one copy to avoid retaining microphone buffers.
    audio = samples.astype(np.float32) / 32768.0
    safe_name = " ".join(str(assistant_name or "Aurora").split())[:48]
    initial_prompt = (
        "Português brasileiro falado informalmente. Perguntas e comandos curtos. "
        f"O nome da assistente é {safe_name}."
    )
    with _TRANSCRIBE_LOCK:
        segments = _get_model().transcribe(
            audio,
            language="pt",
            n_threads=_thread_count(),
            no_context=True,
            no_timestamps=True,
            audio_ctx=_audio_context(samples.size),
            max_tokens=128,
            single_segment=True,
            print_progress=False,
            print_realtime=False,
            suppress_nst=True,
            temperature=0.0,
            initial_prompt=initial_prompt,
        )
    return " ".join(str(segment.text).strip() for segment in segments if segment.text.strip()).strip()
