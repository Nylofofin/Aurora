#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${AURORA_VENV:-$APP_DIR/.venv}"
MODEL_DIR="$APP_DIR/assets/vosk-model"
"$APP_DIR/run.sh" --setup-only
"$VENV/bin/pip" install -r "$APP_DIR/requirements-voice.txt"
mkdir -p "$(dirname "$MODEL_DIR")"
if [ ! -d "$MODEL_DIR" ]; then
  TMP_DIR="$(mktemp -d)"
  curl -L --fail --silent --show-error 'https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip' -o "$TMP_DIR/model.zip"
  python3 - "$TMP_DIR/model.zip" "$MODEL_DIR" <<'PYCODE'
import sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as z: z.extractall(sys.argv[2].rsplit('/',1)[0])
PYCODE
  mv "$(dirname "$MODEL_DIR")/vosk-model-small-pt-0.3" "$MODEL_DIR"
  python3 -c 'import shutil,sys; shutil.rmtree(sys.argv[1],ignore_errors=True)' "$TMP_DIR"
fi
printf 'Voz local pronta. Modelo salvo em %s\n' "$MODEL_DIR"
