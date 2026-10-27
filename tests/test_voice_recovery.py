# SPDX-License-Identifier: GPL-3.0-only
import pytest

from aurora_core.service import AuroraService
from aurora_core.voice import wake
from aurora_core.voice.wake import parse_vosk_result


@pytest.fixture(autouse=True)
def reset_vosk_log_throttle():
    """Keep rate-limited diagnostics isolated between tests."""
    wake._LAST_MALFORMED_RESULT_LOG.clear()


def test_voice_error_logs_cause_speaks_once_and_schedules_bounded_retry(monkeypatch, capsys):
    scheduled = []
    spoken = []

    class Orb:
        def reveal(self, mode): self.mode = mode

    class Voice:
        running = True

    class Service:
        _restart_voice_after_error = AuroraService._restart_voice_after_error
        orb = Orb()
        voice = Voice()
        response_finished = False
        response_summary = ""
        _voice_recovery_attempts = 0
        _voice_error_announced = False
        def speak_in_selected_language(self, text): spoken.append(text)

    monkeypatch.setattr("aurora_core.service.QTimer.singleShot",
                        lambda delay, callback: scheduled.append((delay, callback)))
    service = Service()
    AuroraService.voice_error(service, "PortAudioError: Device unavailable")
    AuroraService.voice_error(service, "PortAudioError: Device unavailable")

    assert service.response_summary == "Não consegui iniciar o reconhecimento de voz."
    assert service.orb.mode == "error"
    assert len(spoken) == 1
    assert [delay for delay, _callback in scheduled] == [1000, 2500]
    assert "PortAudioError: Device unavailable" in capsys.readouterr().err


def test_voice_recovery_counter_resets_after_capture_device_is_ready():
    class Service:
        _voice_recovery_attempts = 3
        _voice_error_announced = True

    service = Service()
    AuroraService.voice_state(service, "ready")
    assert service._voice_recovery_attempts == 0
    assert service._voice_error_announced is False


def test_vosk_malformed_metadata_recovers_transcript_without_logging_it(capsys):
    payload = '{"text": "abrir calculadora",\n result: []}'
    result = parse_vosk_result(payload, "comando")
    assert result == {"text": "abrir calculadora", "result": []}
    output = capsys.readouterr().err
    assert "texto recuperado" in output
    assert "abrir calculadora" not in output


def test_vosk_malformed_metadata_recovers_only_valid_word_confidences(capsys):
    payload = '{"text": "abrir calculadora", "result": [{"word": "abrir", "conf": 0.94}, {"word": "calculadora", "conf": 0.97}], bad}'
    result = parse_vosk_result(payload, "comando")
    assert result == {"text": "abrir calculadora", "result": [{"conf": 0.94}, {"conf": 0.97}]}
    assert "abrir calculadora" not in capsys.readouterr().err


def test_vosk_invalid_result_without_text_is_nonfatal(capsys):
    assert parse_vosk_result('{not-json}', "wake") == {"text": "", "result": []}
    assert "sem texto recuperável" in capsys.readouterr().err


def test_first_malformed_vosk_diagnostic_is_not_suppressed_during_cold_start(monkeypatch, capsys):
    wake._LAST_MALFORMED_RESULT_LOG.clear()
    monkeypatch.setattr(wake.time, "monotonic", lambda: 10.0)

    parse_vosk_result("{not-json}", "cold-start")

    assert "sem texto recuperável" in capsys.readouterr().err
