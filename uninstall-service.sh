#!/usr/bin/env bash
set -euo pipefail
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
systemctl --user disable --now aurora.service 2>/dev/null || true
rm -f "$UNIT_DIR/aurora.service"
systemctl --user daemon-reload
systemctl --user reset-failed aurora.service 2>/dev/null || true
printf 'Serviço de usuário da Aurora removido.\n'
