#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${AURORA_VENV:-$APP_DIR/.venv}"
MODEL_DIR="$APP_DIR/assets/vosk-model"
DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/aurora"
STT_MODEL_DIR="$DATA_ROOT/models"
STT_MODEL="$STT_MODEL_DIR/ggml-base-q5_1.bin"
STT_MODEL_SHA256="422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898"
VOICE_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/aurora/voices"
PIPER_DIR="$VOICE_ROOT/pt_BR-faber-medium"
TMP_DIRS=()
cleanup() { for tmp in "${TMP_DIRS[@]}"; do rm -rf -- "$tmp"; done; }
trap cleanup EXIT
"$APP_DIR/run.sh" --setup-only
"$VENV/bin/python" -m pip install -r "$APP_DIR/requirements-voice.txt"
# PyPI's x86_64 wheel is built on newer CPUs and can execute AVX2 instructions
# unconditionally. Rebuild on older x86 hosts with only the instruction set
# actually supported by this machine; this keeps old-but-capable CPUs safe.
CPU_FLAGS="$(awk '/^flags[[:space:]]*:/{print; exit}' /proc/cpuinfo 2>/dev/null || true)"
if [ "$(uname -m)" = "x86_64" ] && { ! grep -qw avx2 <<<"$CPU_FLAGS" || ! grep -qw bmi2 <<<"$CPU_FLAGS" || ! grep -qw fma <<<"$CPU_FLAGS" || ! grep -qw f16c <<<"$CPU_FLAGS" || ! grep -qw sse4_2 <<<"$CPU_FLAGS"; }; then
  if ! command -v cmake >/dev/null 2>&1 || ! command -v c++ >/dev/null 2>&1; then
    printf 'Este processador não tem AVX2. Para compilar o Whisper seguro para ele, instale cmake e gcc-c++.\n' >&2
    exit 1
  fi
  AVX_FLAG=OFF
  SSE42_FLAG=OFF
  if grep -qw avx <<<"$CPU_FLAGS"; then AVX_FLAG=ON; fi
  if grep -qw sse4_2 <<<"$CPU_FLAGS"; then SSE42_FLAG=ON; fi
  CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_AVX=$AVX_FLAG -DGGML_AVX2=OFF -DGGML_BMI2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_SSE42=$SSE42_FLAG -DGGML_OPENMP=ON" \
    "$VENV/bin/python" -m pip install --force-reinstall --no-binary=pywhispercpp pywhispercpp==1.5.1
  printf 'Runtime Whisper.cpp recompilado para as instruções suportadas por este processador.\n'
fi
mkdir -p "$(dirname "$MODEL_DIR")"
if [ -e "$MODEL_DIR" ] || [ -L "$MODEL_DIR" ]; then
  if [ ! -d "$MODEL_DIR" ] || [ -L "$MODEL_DIR" ]; then
    printf 'O destino do modelo Vosk já existe e não é uma pasta segura: %s\n' "$MODEL_DIR" >&2
    exit 1
  fi
fi
if [ ! -d "$MODEL_DIR" ]; then
  TMP_DIR="$(mktemp -d)"
  TMP_DIRS+=("$TMP_DIR")
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
printf 'Modelo Vosk pronto em %s\n' "$MODEL_DIR"
if [ -L "$DATA_ROOT" ] || [ -L "$STT_MODEL_DIR" ]; then
  printf 'O diretório de dados da Aurora para o modelo Whisper não pode ser um link simbólico.\n' >&2
  exit 1
fi
mkdir -p "$STT_MODEL_DIR"
chmod 700 "$DATA_ROOT" "$STT_MODEL_DIR"
if [ -e "$STT_MODEL" ] || [ -L "$STT_MODEL" ]; then
  if [ ! -f "$STT_MODEL" ] || [ -L "$STT_MODEL" ] || ! printf '%s  %s\n' "$STT_MODEL_SHA256" "$STT_MODEL" | sha256sum --check --status; then
    printf 'O modelo Whisper local já existe, mas não passou pela validação SHA-256: %s\n' "$STT_MODEL" >&2
    exit 1
  fi
else
  STT_TMP_DIR="$(mktemp -d)"
  TMP_DIRS+=("$STT_TMP_DIR")
  curl -L --fail --silent --show-error \
    'https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/ggml-base-q5_1.bin' \
    -o "$STT_TMP_DIR/ggml-base-q5_1.bin"
  if ! printf '%s  %s\n' "$STT_MODEL_SHA256" "$STT_TMP_DIR/ggml-base-q5_1.bin" | sha256sum --check --status; then
    printf 'O download do modelo Whisper não passou pela validação SHA-256.\n' >&2
    exit 1
  fi
  chmod 600 "$STT_TMP_DIR/ggml-base-q5_1.bin"
  mv "$STT_TMP_DIR/ggml-base-q5_1.bin" "$STT_MODEL"
fi
chmod 600 "$STT_MODEL"
printf 'Modelo local Whisper.cpp pronto em %s (base quantizado, 57 MB).\n' "$STT_MODEL"
if [ -f "$PIPER_DIR/pt_BR-faber-medium.onnx" ] && [ -f "$PIPER_DIR/pt_BR-faber-medium.onnx.json" ]; then
  printf 'Modelo Faber encontrado em %s\n' "$PIPER_DIR"
else
  printf 'Runtime Piper instalado. O modelo Faber é opcional e não é baixado automaticamente; consulte assets/voices/README.md e confira seus termos antes de instalá-lo.\n'
fi
