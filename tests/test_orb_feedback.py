# SPDX-License-Identifier: GPL-3.0-only
import aurora_core.ui.orb as orb_module
from aurora_core.voice.tts import Speaker


def test_word_boundary_pulse_is_bounded_and_responds_to_word_length():
    short = Speaker.word_boundary_pulse("oi")
    long = Speaker.word_boundary_pulse("sincronização")

    assert 0.0 < short < long <= 0.88
    assert Speaker.word_boundary_pulse("…") == 0.18


def test_missing_ffplay_reports_voice_error_without_linux_speech_fallback(monkeypatch):
    monkeypatch.setattr("aurora_core.voice.tts.shutil.which", lambda _name: None)
    speaker = Speaker({})
    errors = []
    drained = []
    speaker.speech_error.connect(errors.append)
    speaker.drained.connect(lambda: drained.append(True))

    class OneItemQueue:
        def __init__(self): self.read = False
        def get(self, timeout):
            if not self.read:
                self.read = True
                return ("teste", 0.0, None, "piper")
            speaker.running = False
            raise __import__("queue").Empty
        def empty(self): return True

    speaker.q = OneItemQueue()
    speaker.run()

    assert errors == ["O ffplay é necessário para reproduzir a voz da Aurora."]
    assert drained == [True]


def test_completion_pulse_only_resets_from_latest_timer(monkeypatch):
    timers = []

    class Root:
        def __init__(self):
            self.values = []

        def setProperty(self, name, value):
            self.values.append((name, value))

    class OrbStub:
        pulse_complete = orb_module.AuroraOrb.pulse_complete

        def __init__(self):
            self.root = Root()
            self._completion_pulse_generation = 0

    monkeypatch.setattr(orb_module.QTimer, "singleShot", lambda _ms, callback: timers.append(callback))
    orb = OrbStub()
    orb.pulse_complete()
    first_timer = timers.pop()
    orb.pulse_complete()
    latest_timer = timers.pop()

    first_timer()
    assert orb.root.values[-1] == ("completionPulse", 1.0)
    latest_timer()
    assert orb.root.values[-1] == ("completionPulse", 0.0)


def test_orb_discards_late_speech_pulses_outside_playback():
    class Root:
        def __init__(self): self.values = []
        def setProperty(self, name, value): self.values.append((name, value))

    class OrbStub:
        set_mode = orb_module.AuroraOrb.set_mode
        set_speech_level = orb_module.AuroraOrb.set_speech_level
        def __init__(self): self.mode = "searching"; self.root = Root()

    orb = OrbStub()
    orb.set_speech_level(0.8)
    assert not orb.root.values

    orb.set_mode("speaking")
    orb.set_speech_level(0.8)
    assert orb.root.values[-1] == ("speechPulse", 0.8)

    orb.set_mode("idle")
    before = list(orb.root.values)
    orb.set_speech_level(0.8)
    assert orb.root.values == before
