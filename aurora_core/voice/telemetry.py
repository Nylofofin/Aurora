"""Privacy-safe voice-stage timing for local service logs."""
from __future__ import annotations

import sys
import time

_STAGES = {"stt", "llm_first_response", "llm_turn", "tts_first_audio", "tts_queue", "tts_complete"}
_OUTCOMES = {"ok", "google", "local_fallback", "interrupted"}


def log_voice_timing(stage: str, elapsed_ms: int, outcome: str = "ok") -> None:
    """Log bounded stage labels and durations; never include audio or transcript text."""
    safe_stage = str(stage) if stage in _STAGES else ""
    safe_outcome = str(outcome) if outcome in _OUTCOMES else ""
    if not safe_stage or not safe_outcome:
        return
    print(f"[voice-timing] stage={safe_stage} elapsed_ms={max(0, int(elapsed_ms))} outcome={safe_outcome}",
          file=sys.stderr, flush=True)


def elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
