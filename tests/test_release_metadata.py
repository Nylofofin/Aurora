# SPDX-License-Identifier: GPL-3.0-only
import re
from pathlib import Path

from aurora_core.version import BUILD_ID, CODENAME, __version__


def test_readme_release_identity_matches_application_version():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"\*\*Versão:\*\* `([^`]+)` .*? \*\*Build:\*\* `([^`]+)`",
        readme,
    )

    assert match is not None
    assert match.group(1) == __version__
    assert match.group(2) == BUILD_ID

    changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert changelog.splitlines()[2].casefold().startswith(
        f"## Aurora Desktop {__version__} — {CODENAME.title()}, ".casefold()
    )
    assert "## Aurora Desktop 1.6.0 — Bellatrix Stability Baseline" in changelog


def test_launchpad_runtime_version_matches_rpm_metadata():
    root = Path(__file__).resolve().parents[1]
    runtime = (root / "launchpad" / "aurora_launchpad.py").read_text(encoding="utf-8")
    spec = (root / "packaging" / "rpm" / "aurora-launchpad.spec").read_text(encoding="utf-8")
    runtime_version = re.search(r'^INSTALLER_VERSION = "([^"]+)"$', runtime, re.MULTILINE)
    rpm_version = re.search(r"^Version:\s+(\S+)$", spec, re.MULTILINE)

    assert runtime_version is not None
    assert rpm_version is not None
    assert runtime_version.group(1) == rpm_version.group(1)


def test_aurora_studio_profile_settings_feed_the_system_prompt():
    from aurora_core.llm.prompts import assistant_system_prompt

    prompt = assistant_system_prompt(
        assistant_name="Luna",
        user_name="Nylo",
        preferences={
            "assistant_personality": "playful",
            "conversation_tone": 82,
            "response_detail": "concise",
            "custom_instructions": "Use exemplos curtos.",
        },
    )

    assert "Você é Luna" in prompt
    assert "Leve e espirituosa" in prompt
    assert "uma ou duas frases curtas" in prompt
    assert "Tom caloroso e expressivo" in prompt
    assert "Use exemplos curtos." in prompt
    assert "não mudam fatos, ferramentas, permissões" in prompt
