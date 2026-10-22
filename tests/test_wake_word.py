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
