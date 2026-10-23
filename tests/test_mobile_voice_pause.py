import sys
import threading
import time
import types

from aurora_core.voice import wake


def test_mobile_control_closes_pc_audio_stream_and_reopens_after_release(monkeypatch, tmp_path):
    opened = []
    closed = []

    class Stream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]

        def __enter__(self):
            opened.append(time.monotonic())
            return self

        def __exit__(self, *_args):
            closed.append(time.monotonic())

    class Recognizer:
        def __init__(self, *_args):
            pass

        def SetWords(self, _enabled):
            pass

        def Reset(self):
            pass

        def AcceptWaveform(self, _block):
            return False

    sounddevice = types.SimpleNamespace(RawInputStream=Stream)
    vosk = types.SimpleNamespace(Model=lambda _path: object(), KaldiRecognizer=Recognizer)
    speech = types.SimpleNamespace(Recognizer=lambda: types.SimpleNamespace(operation_timeout=None))
    monkeypatch.setitem(sys.modules, "sounddevice", sounddevice)
    monkeypatch.setitem(sys.modules, "vosk", vosk)
    monkeypatch.setitem(sys.modules, "speech_recognition", speech)
    monkeypatch.setattr(wake, "VOSK_PATH", tmp_path)
    voice = wake.LocalVoice({})
    voice.status.connect(lambda _status: None)
    voice.unavailable.connect(lambda error: (_ for _ in ()).throw(AssertionError(error)))
    worker = threading.Thread(target=voice.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 3
    while not opened and time.monotonic() < deadline:
        time.sleep(.01)
    assert len(opened) == 1

    voice.mobile_owned.set()
    deadline = time.monotonic() + 3
    while len(closed) < 1 and time.monotonic() < deadline:
        time.sleep(.01)
    assert len(closed) == 1
    time.sleep(.2)
    assert len(opened) == 1  # The desktop microphone stays released during mobile ownership.

    voice.mobile_owned.clear()
    deadline = time.monotonic() + 3
    while len(opened) < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    assert len(opened) == 2
    voice.stop()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert len(closed) == 2
