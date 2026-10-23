# SPDX-License-Identifier: GPL-3.0-only
import asyncio
import sys
import threading
import types

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


def test_recognized_command_does_not_auto_rearm_continuous_listening():
    from pathlib import Path
    from aurora_core.voice.wake import MIC_BLOCK_FRAMES

    source = (Path(__file__).resolve().parents[1] / "aurora_core" / "voice" / "wake.py").read_text()
    service_source = (Path(__file__).resolve().parents[1] / "aurora_core" / "service.py").read_text()
    assert "if self.one_shot.is_set():" in source
    assert "self.one_shot.is_set() or self.request_active.is_set()" not in source
    assert MIC_BLOCK_FRAMES == 1600
    assert "pcm=b''.join(buffer[-80:]); active=False" in source
    assert "getattr(self,'continuous_mode',False)" in service_source


def test_speaker_interrupt_discards_queued_speech():
    speaker = aurora.Speaker({})
    speaker.q.put("fala que ainda não começou")

    speaker.interrupt()

    assert speaker.q.empty()


def test_speaker_interrupt_cancels_stalled_edge_stream(monkeypatch):
    import aurora_core.voice.tts as tts_module

    started = threading.Event()
    class Player:
        def __init__(self): self.stdin = object(); self.returncode = None; self.killed = False
        def kill(self): self.killed = True; self.returncode = -9
        async def wait(self): return self.returncode
    player = Player()
    async def create_player(*_args, **_kwargs): return player
    monkeypatch.setattr(tts_module.asyncio, "create_subprocess_exec", create_player)

    class Communicate:
        def __init__(self, *_args, **_kwargs): pass
        def stream(self):
            async def stalled_stream():
                started.set()
                await asyncio.Future()
                yield {"type": "audio", "data": b"unreachable"}
            return stalled_stream()
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))

    speaker = aurora.Speaker({})
    async def exercise():
        task = asyncio.create_task(speaker._stream_edge("resposta", speaker.cancel_generation))
        assert await asyncio.to_thread(started.wait, 1)
        speaker.interrupt()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)

    asyncio.run(exercise())
    assert player.killed
    assert speaker.stream_task is None


def test_speaker_clears_stream_handle_when_player_creation_is_cancelled(monkeypatch):
    import aurora_core.voice.tts as tts_module

    started = threading.Event()
    async def stalled_player(*_args, **_kwargs):
        started.set()
        await asyncio.Future()
    monkeypatch.setattr(tts_module.asyncio, "create_subprocess_exec", stalled_player)
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=object))
    speaker = aurora.Speaker({})

    async def exercise():
        task = asyncio.create_task(speaker._stream_edge("resposta", speaker.cancel_generation))
        assert await asyncio.to_thread(started.wait, 1)
        speaker.interrupt()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)

    asyncio.run(exercise())
    assert speaker.stream_task is None
    assert speaker.stream_loop is None


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
    assert "PathAngleArc { centerX: 57; centerY: 57; radiusX: 56; radiusY: 56" in source
    assert "property real sheenTravel" in source and "entranceActive" not in source and "exitActive" not in source
    assert "PathCubic" not in source and "morphPhase" not in source
    assert "RadialGradient" in source and "LinearGradient" in source
    assert "inputLevel" in source and "voiceEnergy" in source
    assert "SmoothedAnimation" in source and "activeEnergy" in source
    assert source.count("Shape {") == 3
    assert "duration: root.mode === \"searching\" ? 1550" in source
    assert "statusText" not in source and "statusBadge" not in source
    assert "voiceGlyph" not in source and "thoughtCore" not in source and "orbit" not in source
    assert "Text {" not in source and "Repeater {" not in source
    assert "self.scale_anim.setStartValue(.68)" in orb
    assert "QEasingCurve.Type.OutBack" in orb and "QEasingCurve.Type.InBack" in orb
