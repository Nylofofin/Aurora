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


def test_conversation_session_stays_active_until_explicitly_stopped():
    voice = aurora.LocalVoice({})
    assert not voice.session_active.is_set()

    voice.begin_session()
    assert voice.session_active.is_set()

    voice.end_session()
    assert not voice.session_active.is_set()
    assert not voice.one_shot.is_set()


def test_speaker_interrupt_discards_queued_speech():
    speaker = aurora.Speaker({})
    speaker.q.put("fala que ainda não começou")

    speaker.interrupt()

    assert speaker.q.empty()


def test_right_click_is_wired_to_end_conversation():
    from pathlib import Path

    root = Path(aurora.__file__).parent
    source = (root / "orb.qml").read_text()
    service = (root / "aurora.py").read_text()
    assert "if (mouse.button === Qt.RightButton)" in source
    assert "self.orb.hide_requested.connect(self.stop_conversation)" in service
