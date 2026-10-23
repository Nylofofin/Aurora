"""Private local audit log shared by desktop integrations."""
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

def _append_action_log(action: str, outcome: str, details: dict | None = None) -> None:
    """Keep an auditable, local JSONL record; callers must omit credentials."""
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "aurora"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    row = {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
           "action": action, "outcome": outcome, "details": details or {}}
    path = root / "actions.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.chmod(path, 0o600)

