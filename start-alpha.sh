#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/../.." && pwd)"
mkdir -p "$ROOT_DIR/work"
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
  if [ -x "$ROOT_DIR/work/ollama-runtime/bin/ollama" ]; then
    export OLLAMA_MODELS="$ROOT_DIR/work/ollama-models"
    OLLAMA_BIN="$ROOT_DIR/work/ollama-runtime/bin/ollama"
  elif command -v ollama >/dev/null 2>&1; then
    OLLAMA_BIN="$(command -v ollama)"
  else
    OLLAMA_BIN=''
  fi
  if [ -n "$OLLAMA_BIN" ]; then
    export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_VULKAN=1 OLLAMA_KEEP_ALIVE=5m OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 GGML_VK_VISIBLE_DEVICES=0
    "$OLLAMA_BIN" serve >"$ROOT_DIR/work/aurora-ollama.log" 2>&1 &
    OLLAMA_PID=$!
    for _ in $(seq 1 60); do
      if check_api; then break; fi
      sleep 1
    done
  fi
fi
cleanup() {
  if [ -n "$OLLAMA_PID" ]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
    wait "$OLLAMA_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM
"$APP_DIR/run.sh" 2>>"$ROOT_DIR/work/aurora-app.log"
