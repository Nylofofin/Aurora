#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${AURORA_VENV:-$APP_DIR/.venv}"
mkdir -p "$(dirname "$VENV")"
if [ ! -x "$VENV/bin/python" ]; then python3 -m venv "$VENV"; fi
if ! "$VENV/bin/python" -c 'import PySide6, babel, edge_tts, speech_recognition, sounddevice, numpy, vosk, certifi' >/dev/null 2>&1; then "$VENV/bin/python" -m pip install -r "$APP_DIR/requirements.txt"; fi
CERT_BUNDLE="$($VENV/bin/python -c 'import certifi; print(certifi.where())')"
if [ -f "$CERT_BUNDLE" ]; then export SSL_CERT_FILE="$CERT_BUNDLE"; fi
if [ "${1:-}" = '--setup-only' ]; then exit 0; fi
if [ -n "${WAYLAND_DISPLAY:-}" ] && [ -n "${DISPLAY:-}" ]; then export QT_QPA_PLATFORM=xcb; fi
exec "$VENV/bin/python" "$APP_DIR/aurora.py"
