#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/aurora.service"
mkdir -p "$UNIT_DIR"
cat >"$UNIT_FILE" <<UNIT
[Unit]
Description=Aurora floating local AI assistant
Documentation=file://$APP_DIR/README.md
After=graphical-session-pre.target
Wants=graphical-session-pre.target
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/start-alpha.sh
Restart=on-failure
RestartSec=4
KillMode=control-group
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_NO_CLOUD=1
Environment=OLLAMA_KEEP_ALIVE=5m
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=2
Environment=OLLAMA_VULKAN=1
Environment=QT_QPA_PLATFORM=xcb
EnvironmentFile=-%h/.config/aurora/runtime.env

[Install]
WantedBy=graphical-session.target
UNIT
chmod 644 "$UNIT_FILE"
rm -f "$HOME/.config/autostart/aurora.desktop"
systemctl --user daemon-reload
# Stop the manually launched instance so the user service owns the single Aurora process.
for pid in $(pgrep -f "$APP_DIR/aurora.py" || true); do
    command_line="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
    if [[ "$command_line" == *"$APP_DIR/.venv/bin/python $APP_DIR/aurora.py"* ]]; then kill -TERM "$pid" 2>/dev/null || true; fi
done
for _ in $(seq 1 30); do
    if ! pgrep -f "$APP_DIR/aurora.py" >/dev/null 2>&1; then break; fi
    sleep 0.1
done
systemctl --user enable --now aurora.service
printf 'Aurora instalada como serviço de usuário e habilitada para iniciar com a sessão gráfica.\n'
systemctl --user --no-pager --full status aurora.service
