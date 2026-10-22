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


def test_wake_session_is_a_single_request_gate():
    voice = aurora.LocalVoice({})
    assert not voice.request_active.is_set()

    voice.begin_request()
    assert voice.request_active.is_set()

    voice.end_request()
    assert not voice.request_active.is_set()
    assert not voice.one_shot.is_set()


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
    for phrase in ("para", "pare", "parar", "cancele", "cancela", "cancelar"):
        assert match(phrase, True)
    assert not match("para", False)
    assert not match("para a janela", True)


def test_control_cancel_detection_can_be_enabled_and_disabled():
    voice = LocalVoice({})
    voice.enable_control_cancel()
    assert voice.cancel_control_active.is_set()
    voice.disable_control_cancel()
    assert not voice.cancel_control_active.is_set()


def test_recognized_command_does_not_auto_rearm_continuous_listening():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "aurora_core" / "voice" / "wake.py").read_text()
    assert "if self.one_shot.is_set():" in source
    assert "self.one_shot.is_set() or self.request_active.is_set()" not in source
    assert "pcm=b''.join(buffer[-40:]); active=False" in source


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
