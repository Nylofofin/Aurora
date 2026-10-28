from aurora_core.ui.onboarding import (
    BUBBLE_STYLES, BUBBLE_STYLE_KEYS, FEEDBACK_THEMES, FEEDBACK_THEME_KEYS,
)


def test_removed_finish_is_not_offered_anywhere_in_the_onboarding_catalog():
    assert len(BUBBLE_STYLES) == 10
    assert "io" not in BUBBLE_STYLE_KEYS
    assert all(title != "Crosta Incandescente" for _key, title, _detail in BUBBLE_STYLES)
    assert {"quasar", "lunar"} <= BUBBLE_STYLE_KEYS


def test_sound_catalog_has_matching_original_entry_and_exit_assets():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert len(FEEDBACK_THEMES) == 9
    assert {"aether", "quasar", "ember"} <= FEEDBACK_THEME_KEYS
    for key in FEEDBACK_THEME_KEYS:
        for direction in ("entrada", "saida"):
            asset = root / "assets" / "audio" / f"{direction}-{key}.wav"
            assert asset.is_file(), f"missing sound asset: {asset.name}"

