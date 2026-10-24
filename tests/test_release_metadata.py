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
    assert changelog.splitlines()[2].startswith(
        f"## Aurora Desktop {__version__} — {CODENAME.title()}, "
    )
    assert "## Aurora Desktop 1.6.0 — Bellatrix Stability Baseline" in changelog
