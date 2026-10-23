from aurora_core.voice.telemetry import log_voice_timing


def test_voice_timing_logs_only_sanitized_stage_metadata(capsys):
    log_voice_timing("stt", 13, "google")
    log_voice_timing("stt private transcript", 9000, "ok")
    log_voice_timing("tts_complete", 28, "fallback")
    output = capsys.readouterr().err

    assert output == ("[voice-timing] stage=stt elapsed_ms=13 outcome=google\n"
                      "[voice-timing] stage=tts_complete elapsed_ms=28 outcome=fallback\n")
    assert "transcript text" not in output
