import aurora


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


def test_recognized_command_does_not_auto_rearm_continuous_listening():
    from pathlib import Path

    source = (Path(aurora.__file__).parent / "aurora.py").read_text()
    assert "if self.one_shot.is_set():" in source
    assert "self.one_shot.is_set() or self.request_active.is_set()" not in source
    assert "pcm=b''.join(buffer[-40:]); active=False" in source


def test_speaker_interrupt_discards_queued_speech():
    speaker = aurora.Speaker({})
    speaker.q.put("fala que ainda não começou")

    speaker.interrupt()

    assert speaker.q.empty()


def test_right_click_is_wired_to_stop_the_current_request():
    from pathlib import Path

    root = Path(aurora.__file__).parent
    source = (root / "orb.qml").read_text()
    service = (root / "aurora.py").read_text()
    assert "if (mouse.button === Qt.RightButton)" in source
    assert "self.orb.hide_requested.connect(self.stop_conversation)" in service
