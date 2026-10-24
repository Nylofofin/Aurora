#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$APP_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then PYTHON="$(command -v python3)"; fi
cd "$APP_DIR"
"$PYTHON" -m compileall -q aurora.py aurora_core aurora_fx.py aurora_integrations.py scripts
"$PYTHON" -m pytest -q
for script in ./*.sh scripts/*.sh; do
  [[ -f "$script" ]] && bash -n "$script"
done
printf 'Desktop release checks passed.\n'
