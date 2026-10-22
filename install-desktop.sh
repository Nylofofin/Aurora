#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat >"$DESKTOP_DIR/aurora.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Aurora
Comment=Assistente local por IA
Exec=systemctl --user start aurora.service
Terminal=false
Categories=Utility;Accessibility;
StartupNotify=false
ENTRY
chmod 644 "$DESKTOP_DIR/aurora.desktop"
"$APP_DIR/install-service.sh"
