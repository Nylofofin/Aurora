# SPDX-License-Identifier: GPL-3.0-only
import threading

import pytest
import aurora
from aurora_core.service import AuroraService
from aurora_core.voice.wake import LocalVoice


def test_wake_word_requires_a_completed_exact_phrase():
    match = aurora.LocalVoice.is_final_wake_phrase
    assert not match("aurora", False)
    assert match("aurora", True)
    assert match("ei aurora", True)
    assert match("olá aurora", True)
    assert not match("aura", True)
    assert not match("aurora talvez", True)
    assert not match("oi, aurora", True)


def test_wake_word_is_removed_before_command_routing():
    from aurora_core.system.text import strip_wake_word

    assert strip_wake_word("Olá Aurora, abre o navegador") == "abre o navegador"
    assert strip_wake_word("Ei Aurora: abre o navegador") == "abre o navegador"


def test_custom_wake_name_is_used_for_exact_detection_and_stripping():
    from aurora_core.system.text import strip_wake_word

    assert LocalVoice.is_final_wake_phrase("ei luna", True, "Luna")
    assert LocalVoice.is_final_wake_phrase("olá nova aurora", True, "Nova Aurora")
    assert not LocalVoice.is_final_wake_phrase("luna talvez", True, "Luna")
    assert strip_wake_word("Ei Luna, abra o terminal", "Luna") == "abra o terminal"
    assert strip_wake_word("Olá Nova Aurora: abra o terminal", "Nova Aurora") == "abra o terminal"


def test_custom_wake_name_accepts_punctuation_but_requires_a_word_boundary():
    from aurora_core.system.text import strip_wake_word

    assert LocalVoice.is_final_wake_phrase("Ei, Luna!", True, "Luna")
    assert LocalVoice.is_final_wake_phrase("Nova-Aurora.", True, "Nova Aurora")
    assert LocalVoice.contains_wake_name("Ei, Luna: abra o terminal", "Luna")
    assert LocalVoice.contains_wake_name("Nova Aurora, abra o terminal", "Nova Aurora")
    assert not LocalVoice.contains_wake_name("Lunático, abra o terminal", "Luna")
    assert not LocalVoice.contains_wake_name("abra o terminal", "Luna")
    assert strip_wake_word("Ei, Luna: abra o terminal", "Luna") == "abra o terminal"


def test_wake_stripping_tolerates_one_transcription_error_and_optional_article():
    from aurora_core.system.text import strip_wake_word

    assert strip_wake_word("O Lune, qual é a previsão do tempo?", "Luna") == "qual é a previsão do tempo?"
    assert strip_wake_word("Ei Nova Auror, abra o terminal", "Nova Aurora") == "Ei Nova Auror, abra o terminal"


def test_wake_decoders_reset_together_at_an_utterance_boundary():
    class Recognizer:
        def __init__(self): self.resets = 0
        def Reset(self): self.resets += 1

    grammar = Recognizer()
    fallback = Recognizer()
    LocalVoice.reset_wake_recognizers(grammar, fallback, None)
    assert grammar.resets == 1
    assert fallback.resets == 1


def test_confident_vosk_transcript_skips_slow_whisper_decode(monkeypatch):
    import aurora_core.voice.stt as stt

    monkeypatch.setattr(stt, "transcribe_pcm", lambda *_args: pytest.fail("Whisper should not run"))
    voice = LocalVoice({"assistant_name": "Luna"})
    assert voice.local_transcribe(b"", "Ei, Luna, abra o terminal", 0.95) == "abra o terminal"


def test_moderate_vosk_confidence_keeps_whisper_accuracy_path(monkeypatch):
    import aurora_core.voice.stt as stt

    monkeypatch.setattr(stt, "transcribe_pcm", lambda *_args: "Ei Luna, abra o terminal")
    voice = LocalVoice({"assistant_name": "Luna"})
    assert voice.local_transcribe(b"pcm", "Ei Luna, abre o terminal", 0.89) == "abra o terminal"


def test_uncertain_vosk_transcript_uses_whisper_and_keeps_vosk_fallback(monkeypatch):
    import aurora_core.voice.stt as stt

    monkeypatch.setattr(stt, "transcribe_pcm", lambda *_args: "Ei Luna, abra o navegador")
    voice = LocalVoice({"assistant_name": "Luna"})
    assert voice.local_transcribe(b"pcm", "luna", 0.4) == "abra o navegador"


def test_whisper_audio_context_scales_to_short_commands():
    from aurora_core.voice.stt import SAMPLE_RATE, _audio_context

    assert _audio_context(round(3.6 * SAMPLE_RATE)) == 256
    assert _audio_context(8 * SAMPLE_RATE) == 464
    assert _audio_context(30 * SAMPLE_RATE) == 1500


def test_custom_wake_name_grammar_checks_model_vocabulary():
    from aurora_core.voice.wake import wake_grammar_phrases, wake_name_supported, wake_name_words

    class Model:
        def vosk_model_find_word(self, word):
            return word in {"luna", "nova", "aurora"}

    assert wake_name_words("Nova Aurora") == ("nova", "aurora")
    assert wake_name_supported("Nova Aurora", Model())
    assert not wake_name_supported("Nebrya", Model())
    assert not wake_name_supported("Name 123", Model())
    assert not wake_name_words("Luna, Nova")
    assert wake_grammar_phrases("Luna") == ["luna", "ei luna", "olá luna"]
    assert wake_grammar_phrases("Nova Aurora") == ["nova aurora", "ei nova aurora", "olá nova aurora"]


def test_custom_wake_name_treats_vosk_minus_one_as_missing():
    from aurora_core.voice.wake import wake_name_supported

    class Model:
        def vosk_model_find_word(self, _word):
            return -1

    assert not wake_name_supported("Zorblax", Model())


def test_microphone_energy_is_normalized_for_voice_reactive_orb():
    from array import array

    quiet = array("h", [0] * 32).tobytes()
    medium = array("h", [4000] * 32).tobytes()
    loud = array("h", [16000] * 32).tobytes()
    assert LocalVoice.normalized_audio_level(quiet) == 0.0
    assert 0.4 < LocalVoice.normalized_audio_level(medium) < 0.6
    assert LocalVoice.normalized_audio_level(loud) == 1.0


def test_wake_session_is_a_single_request_gate():
    voice = aurora.LocalVoice({})
    assert not voice.request_active.is_set()

    voice.begin_request()
    assert voice.request_active.is_set()

    voice.end_request()
    assert not voice.request_active.is_set()
    assert not voice.one_shot.is_set()


def test_phone_wake_audio_is_accepted_only_during_mobile_control_and_is_bounded():
    voice = LocalVoice({})
    assert not voice.feed_mobile_audio(b"\0\0")
    voice.mobile_owned.set()
    assert not voice.feed_mobile_audio(b"\0")
    assert not voice.feed_mobile_audio(b"\0" * 32_002)


def test_phone_wake_audio_is_evaluated_by_vosk_on_its_owner_thread():
    import json
    from PySide6.QtCore import QThread

    class FakeWakeRecognizer:
        def AcceptWaveform(self, _block): return True
        def Result(self): return json.dumps({"text": "aurora"})
        def Reset(self): pass

    voice = LocalVoice({})
    voice.mobile_owned.set()

    class WakeWorker(QThread):
        def run(self):
            voice._drain_mobile_audio(FakeWakeRecognizer())

    worker = WakeWorker()
    worker.start()
    try:
        assert voice.feed_mobile_audio(b"\0\0") is True
    finally:
        voice.mobile_owned.clear()
        assert worker.wait(1000)
    assert not worker.isRunning()


def test_wake_detection_stays_suppressed_until_request_finishes_but_allows_click():
    voice = LocalVoice({})
    assert not voice.defer_wake_detection()

    voice.begin_request()
    assert voice.defer_wake_detection()

    voice.request_once()
    assert not voice.defer_wake_detection()

    voice.end_request()
    assert not voice.defer_wake_detection()


def test_control_cancel_requires_an_exact_final_local_phrase():
    match = LocalVoice.is_final_cancel_phrase
    for phrase in ("para", "pare", "parar", "cancele", "cancela", "cancelar",
                   "interrompa", "interrompe", "chega", "calma para",
                   "não calma para", "pera aí", "deixa pra lá",
                   "para com isso", "corta"):
        assert match(phrase, True)
    for ambiguous in ("não", "calma", "espera", "pera", "deixa"):
        assert not match(ambiguous, True)
    assert not match("para", False)
    assert not match("para a janela", True)


def test_new_wake_request_resets_interrupt_listener():
    voice = LocalVoice({})
    voice.interrupt_active.set()
    voice.begin_request()
    assert not voice.interrupt_active.is_set()
    voice.interrupt_active.set()
    voice.end_request()
    assert not voice.interrupt_active.is_set()


def test_control_cancel_detection_can_be_enabled_and_disabled():
    voice = LocalVoice({})
    voice.enable_control_cancel()
    assert voice.cancel_control_active.is_set()
    voice.disable_control_cancel()
    assert not voice.cancel_control_active.is_set()


def test_voice_exposes_barge_in_signal_for_speech_interruption():
    voice = LocalVoice({})
    assert hasattr(voice, "barge_in")
    assert voice.barge_in is not None


def test_recognized_command_does_not_auto_rearm_continuous_listening():
    from pathlib import Path
    from aurora_core.voice.wake import MIC_BLOCK_FRAMES

    source = (Path(__file__).resolve().parents[1] / "aurora_core" / "voice" / "wake.py").read_text()
    service_source = (Path(__file__).resolve().parents[1] / "aurora_core" / "service.py").read_text()
    assert "if self.one_shot.is_set():" in source
    assert "self.one_shot.is_set() or self.request_active.is_set()" not in source
    assert MIC_BLOCK_FRAMES == 1600
    assert "pcm=b''.join(buffer[-200:]); active=False" in source
    assert "getattr(self,'continuous_mode',False)" in service_source


def test_speaker_interrupt_discards_queued_speech():
    speaker = aurora.Speaker({})
    speaker.q.put("fala que ainda não começou")

    speaker.interrupt()

    assert speaker.q.empty()


def test_voice_preview_queues_selected_voice_without_changing_saved_voice():
    speaker = aurora.Speaker({"tts_voice": "pt_BR-faber-medium"})
    speaker.say_with_voice("Olá!", "supertonic:F1", engine="supertonic")
    text, _queued_at, voice, engine, is_preview = speaker.q.get_nowait()
    assert text == "Olá!"
    assert voice == "supertonic:F1"
    assert engine == "supertonic"
    assert is_preview
    assert speaker.cfg["tts_voice"] == "pt_BR-faber-medium"


def test_speaker_interrupt_stops_local_piper_between_audio_chunks(monkeypatch):
    import aurora_core.voice.tts as tts_module
    from types import SimpleNamespace
    import io

    generation_blocked = threading.Event()
    release_generation = threading.Event()
    class Player:
        def __init__(self, *_args, **_kwargs): self.stdin = io.BytesIO(); self.returncode = None; self.killed = False
        def kill(self): self.killed = True; self.returncode = -9
        def wait(self, timeout=None): return self.returncode or 0
        def poll(self): return self.returncode
    player = Player()
    monkeypatch.setattr(tts_module.subprocess, "Popen", lambda *_a, **_k: player)
    class Voice:
        config = SimpleNamespace(sample_rate=22050)
        def synthesize(self, _text):
            yield SimpleNamespace(audio_int16_bytes=b"first")
            generation_blocked.set()
            release_generation.wait(2)
            yield SimpleNamespace(audio_int16_bytes=b"second")
    speaker = aurora.Speaker({"tts_engine": "piper"})
    monkeypatch.setattr(speaker, "_load_piper_voice", lambda _voice=None: Voice())
    errors = []
    def stream():
        try: speaker._stream_piper("resposta", speaker.cancel_generation)
        except RuntimeError as exc: errors.append(str(exc))
    worker = threading.Thread(target=stream)
    worker.start()
    assert generation_blocked.wait(1)
    speaker.interrupt()
    release_generation.set()
    worker.join(2)
    assert not worker.is_alive()
    assert player.killed
    assert speaker.current_player is None
    assert errors == ["speech interrupted"]


def test_speaker_keeps_player_handle_clear_when_local_playback_setup_fails(monkeypatch):
    import aurora_core.voice.tts as tts_module
    from types import SimpleNamespace
    import io

    class Voice:
        config = SimpleNamespace(sample_rate=22050)
        def synthesize(self, _text):
            yield SimpleNamespace(audio_int16_bytes=b"data")
    speaker = aurora.Speaker({"tts_engine": "piper"})
    monkeypatch.setattr(speaker, "_load_piper_voice", lambda _voice=None: Voice())
    monkeypatch.setattr(tts_module.subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("player failed")))
    with pytest.raises(RuntimeError, match="player failed"):
        speaker._stream_piper("resposta", speaker.cancel_generation)
    assert speaker.current_player is None


def test_right_click_is_wired_to_stop_the_current_request():
    from pathlib import Path

    root = Path(aurora.__file__).parent
    source = (root / "orb.qml").read_text()
    service = (root / "aurora_core" / "service.py").read_text()
    assert "if (mouse.button === Qt.RightButton)" in source
    assert "self.orb.hide_requested.connect(self.stop_conversation)" in service


def test_orb_is_only_a_clean_animated_sphere():
    from pathlib import Path

    root = Path(aurora.__file__).parent
    source = (root / "orb.qml").read_text()
    orb = (root / "aurora_core" / "ui" / "orb.py").read_text()
    assert "PathAngleArc { centerX: 48; centerY: 34; radiusX: 39; radiusY: 28" in source
    assert "property real sheenTravel" in source and "entranceActive" not in source and "exitActive" not in source
    assert "PathCubic" not in source and "morphPhase" not in source
    assert "RadialGradient" in source and "LinearGradient" in source
    assert "inputLevel" in source and "voiceEnergy" in source
    assert "SmoothedAnimation" in source and "activeEnergy" in source
    assert source.count("Shape {") >= 3
    assert "duration: root.mode === \"searching\" ? 1550" in source
    assert "statusText" not in source and "statusBadge" not in source
    assert "voiceGlyph" not in source and "thoughtCore" not in source and "orbit" not in source
    assert "Text {" not in source and "Repeater {" not in source
    assert "self.scale_anim.setStartValue(.68)" in orb
    assert "QEasingCurve.Type.OutBack" in orb and "QEasingCurve.Type.InBack" in orb
