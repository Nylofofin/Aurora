#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
WORK_DIR="${AURORA_WORK_DIR:-$STATE_HOME/aurora}"
OLLAMA_RUNTIME_DIR="${AURORA_OLLAMA_RUNTIME_DIR:-$WORK_DIR/ollama-runtime}"
OLLAMA_MODELS_DIR="${AURORA_OLLAMA_MODELS_DIR:-$WORK_DIR/ollama-models}"
mkdir -p "$WORK_DIR"
API='http://127.0.0.1:11434/api/tags'
OLLAMA_PID=''
check_api() { python3 - "$API" <<'PYCODE' >/dev/null 2>&1
import sys,urllib.request
try:
 with urllib.request.urlopen(sys.argv[1],timeout=1): pass
except Exception: raise SystemExit(1)
PYCODE
}
if ! check_api; then
  if [ -x "$OLLAMA_RUNTIME_DIR/bin/ollama" ]; then
    if [ -d "$OLLAMA_MODELS_DIR" ]; then export OLLAMA_MODELS="$OLLAMA_MODELS_DIR"; fi
    OLLAMA_BIN="$OLLAMA_RUNTIME_DIR/bin/ollama"
  elif command -v ollama >/dev/null 2>&1; then
    OLLAMA_BIN="$(command -v ollama)"
  else
    printf 'Ollama não encontrado. Instale o Ollama e baixe os modelos Gemma descritos no README.\n' >&2
    exit 127
  fi
  export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_VULKAN=1 OLLAMA_KEEP_ALIVE=5m OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 GGML_VK_VISIBLE_DEVICES=0
  "$OLLAMA_BIN" serve >"$WORK_DIR/aurora-ollama.log" 2>&1 &
  OLLAMA_PID=$!
  for _ in $(seq 1 60); do
    if check_api; then break; fi
    sleep 1
  done
fi
cleanup() {
  if [ -n "$OLLAMA_PID" ]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
    wait "$OLLAMA_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 0' INT TERM
"$APP_DIR/run.sh" 2>>"$WORK_DIR/aurora-app.log"
