from aurora_core.ui.onboarding import BUBBLE_STYLES, BUBBLE_STYLE_KEYS


def test_removed_finish_is_not_offered_anywhere_in_the_onboarding_catalog():
    assert len(BUBBLE_STYLES) == 8
    assert "io" not in BUBBLE_STYLE_KEYS
    assert all(title != "Crosta Incandescente" for _key, title, _detail in BUBBLE_STYLES)

