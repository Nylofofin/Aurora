"""Guard production sources against one-off web-answer adapters.

Allowed system exceptions, deliberately not banned here:
- Weather/climate: a dedicated system service for local weather, explicitly
  permitted by AGENTS.md; it is not a topic-specific web answer adapter.
- Local date/time: answered from the computer clock, explicitly permitted.
- Local computer commands: app/window/volume/hardware/file operations are
  the assistant's operating-system tools, not web-search topics.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_EXCLUDES = {".git", ".venv", "__pycache__", "tests", "scripts"}

# Subject terms and historical adapter identifiers that must never return to
# production logic. Test fixtures and this guard itself are outside the scan.
FORBIDDEN = (
    re.compile(r"\brobux\b", re.IGNORECASE),
    re.compile(r"\bcurrency\b", re.IGNORECASE),
    re.compile(r"\bc[aâ]mbio\b", re.IGNORECASE),
    re.compile(r"\bd[oó]lar(?:es)?\b", re.IGNORECASE),
    re.compile(r"\bminecraft\b", re.IGNORECASE),
    re.compile(r"\brobux_price_answer\b", re.IGNORECASE),
    re.compile(r"\bcurrency_rate_answer\b", re.IGNORECASE),
    re.compile(r"\bminecraft_java_latest_release\b", re.IGNORECASE),
    re.compile(r"\b_authoritative_host\b", re.IGNORECASE),
    re.compile(r"\b_current_role_identity_supported\b", re.IGNORECASE),
)


def production_python_files():
    for path in ROOT.rglob("*.py"):
        if any(part in PRODUCTION_EXCLUDES for part in path.relative_to(ROOT).parts):
            continue
        yield path


def test_production_has_no_subject_specific_search_adapters():
    violations = []
    for path in production_python_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern in FORBIDDEN:
                if pattern.search(line):
                    violations.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
                    break
    assert not violations, "Assunto/adapter específico encontrado em produção:\n" + "\n".join(violations)
