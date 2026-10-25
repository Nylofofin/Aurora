# SPDX-License-Identifier: GPL-3.0-only
from aurora_core.service import AuroraService


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
        def _mobile_audio_owned(self): return False

    service = Service()
    AuroraService.voice_state(service, "ready")
    assert service._voice_recovery_attempts == 0
    assert service._voice_error_announced is False
