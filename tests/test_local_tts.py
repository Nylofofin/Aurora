from types import SimpleNamespace
import io

import pytest

from aurora_core.config import DEFAULTS
from aurora_core.voice import tts


def test_default_voice_engine_is_local_piper():
    assert DEFAULTS["tts_engine"] == "piper"
    assert DEFAULTS["tts_voice"] == "pt_BR-faber-medium"


def test_local_faber_voice_preview_is_marked_as_preview():
    speaker = tts.Speaker({"tts_engine": "piper"})
    speaker.say_with_voice("Olá!", "pt_BR-faber-medium")
    _text, _queued_at, voice, engine, is_preview, _pitch, _speed = speaker.q.get_nowait()
    assert voice == "pt_BR-faber-medium"
    assert engine == "piper"
    assert is_preview


def test_local_voice_preview_is_queued_without_changing_saved_engine():
    speaker = tts.Speaker({"tts_engine": "piper"})
    speaker.say_with_voice("Olá!", None)

    text, _queued_at, voice, engine, is_preview, _pitch, _speed = speaker.q.get_nowait()
    assert text == "Olá!"
    assert voice is None
    assert engine == "piper"
    assert is_preview
    assert speaker.cfg["tts_engine"] == "piper"


def test_speaker_does_not_silently_truncate_long_answers():
    speaker = tts.Speaker({"tts_engine": "piper"})
    answer = "Esta frase completa precisa chegar ao sintetizador. " * 60
    speaker.say(answer)

    queued_text, _queued_at, _voice, _engine = speaker.q.get_nowait()
    assert queued_text == answer.strip()


def test_speaker_routes_saved_local_engine_to_piper(monkeypatch):
    speaker = tts.Speaker({"tts_engine": "piper"})
    speaker.engine = "/usr/bin/ffplay"
    calls = []

    class OneItemQueue:
        def __init__(self): self.read = False
        def get(self, timeout):
            if not self.read:
                self.read = True
                return ("resposta", 0.0, None, None)
            speaker.running = False
            raise __import__("queue").Empty
        def empty(self): return True

    speaker.q = OneItemQueue()
    monkeypatch.setattr(speaker, "_stream_piper", lambda text, generation, voice_id=None, **_kwargs: calls.append((text, generation, voice_id)))
    speaker.run()
    assert calls == [("resposta", 0, None)]


def test_speaker_coalesces_backlogged_stream_chunks_without_losing_text(monkeypatch):
    import queue

    speaker = tts.Speaker({"tts_engine": "piper", "tts_voice": "faber"})
    speaker.engine = "/usr/bin/ffplay"
    speaker.say("Primeira frase.")
    speaker.say("Segunda frase.")
    speaker.say("Terceira frase.")
    calls = []

    class QueueUntilDrained:
        def __init__(self, items): self.items = list(items)
        def get(self, timeout):
            if self.items: return self.items.pop(0)
            speaker.running = False
            raise queue.Empty
        def get_nowait(self):
            if self.items: return self.items.pop(0)
            raise queue.Empty
        def empty(self): return not self.items

    speaker.q = QueueUntilDrained(list(speaker.q.queue))
    monkeypatch.setattr(speaker, "_stream_piper", lambda text, *_args, **_kwargs: calls.append(text))
    speaker.run()

    assert calls == ["Primeira frase. Segunda frase. Terceira frase."]


def test_local_voice_runtime_detection_is_independent_of_voice_weights(monkeypatch):
    monkeypatch.setattr(tts.importlib.util, "find_spec", lambda _name: object())
    assert tts.local_piper_available()


def test_local_piper_streams_pcm_chunks_to_ffplay(monkeypatch):
    written = bytearray()

    class Input(io.BytesIO):
        def write(self, data):
            written.extend(data)
            return super().write(data)

    class Player:
        def __init__(self, args, **_kwargs):
            self.args = args
            self.stdin = Input()
            self.returncode = None
        def wait(self, timeout=None):
            self.returncode = 0
            return 0
        def poll(self): return self.returncode
        def kill(self): self.returncode = -9

    player = None
    def fake_popen(args, **kwargs):
        nonlocal player
        player = Player(args, **kwargs)
        return player

    chunks = [SimpleNamespace(audio_int16_bytes=b"\x01\x02"),
              SimpleNamespace(audio_int16_bytes=b"\x03\x04")]
    voice = SimpleNamespace(config=SimpleNamespace(sample_rate=22050),
                            synthesize=lambda _text: iter(chunks))
    speaker = tts.Speaker({"tts_engine": "piper"})
    monkeypatch.setattr(speaker, "_load_piper_voice", lambda _voice_id=None: voice)
    monkeypatch.setattr(tts.subprocess, "Popen", fake_popen)
    levels = []
    speaker.speech_level.connect(levels.append)

    speaker._stream_piper("Olá, mundo.", speaker.cancel_generation)

    assert bytes(written).startswith(b"\x01\x02\x03\x04")
    assert player.args[player.args.index("-ar") + 1] == "22050"
    assert player.args[player.args.index("-ch_layout") + 1] == "mono"
    assert levels[-1] == 0.0
    assert speaker.current_player is None


def test_local_piper_failure_kills_player_and_clears_handle(monkeypatch):
    class Player:
        def __init__(self, *_args, **_kwargs):
            self.stdin = io.BytesIO()
            self.returncode = None
            self.killed = False
        def wait(self, timeout=None): self.returncode = -9; return -9
        def poll(self): return self.returncode
        def kill(self): self.killed = True; self.returncode = -9

    player = Player()
    class Voice:
        config = SimpleNamespace(sample_rate=22050)
        def synthesize(self, _text): raise RuntimeError("model error")

    speaker = tts.Speaker({"tts_engine": "piper"})
    monkeypatch.setattr(speaker, "_load_piper_voice", lambda _voice_id=None: Voice())
    monkeypatch.setattr(tts.subprocess, "Popen", lambda *_args, **_kwargs: player)
    with pytest.raises(RuntimeError): speaker._stream_piper("texto", speaker.cancel_generation)

    assert player.killed
    assert speaker.current_player is None
