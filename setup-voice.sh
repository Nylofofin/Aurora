#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${AURORA_VENV:-$APP_DIR/.venv}"
MODEL_DIR="$APP_DIR/assets/vosk-model"
"$APP_DIR/run.sh" --setup-only
"$VENV/bin/pip" install -r "$APP_DIR/requirements-voice.txt"
mkdir -p "$(dirname "$MODEL_DIR")"
if [ -e "$MODEL_DIR" ] || [ -L "$MODEL_DIR" ]; then
  if [ ! -d "$MODEL_DIR" ] || [ -L "$MODEL_DIR" ]; then
    printf 'O destino do modelo Vosk já existe e não é uma pasta segura: %s\n' "$MODEL_DIR" >&2
    exit 1
  fi
fi
if [ ! -d "$MODEL_DIR" ]; then
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf -- "$TMP_DIR"' EXIT
  curl -L --fail --silent --show-error 'https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip' -o "$TMP_DIR/model.zip"
  mkdir -p "$TMP_DIR/extracted"
  PYTHONPATH="$APP_DIR" python3 - "$TMP_DIR/model.zip" "$TMP_DIR/extracted" <<'PYCODE'
import sys,zipfile
from aurora_core.system.archives import extract_zip_safely
extract_zip_safely(sys.argv[1], sys.argv[2])
PYCODE
  MODEL_SOURCE="$TMP_DIR/extracted/vosk-model-small-pt-0.3"
  for required in final.mdl Gr.fst HCLr.fst mfcc.conf; do
    if [ ! -f "$MODEL_SOURCE/$required" ]; then
      printf 'O arquivo do modelo Vosk está incompleto: %s\n' "$required" >&2
      exit 1
    fi
  done
  mv "$MODEL_SOURCE" "$MODEL_DIR"
fi
printf 'Voz local pronta. Modelo salvo em %s\n' "$MODEL_DIR"
