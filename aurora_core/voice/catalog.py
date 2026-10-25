# SPDX-License-Identifier: GPL-3.0-only
"""Catalog of the retained Faber Piper voice and local Supertonic voice styles."""
from __future__ import annotations

from dataclasses import dataclass
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import time
import importlib.util

from ..config import VOICE_ROOT


@dataclass(frozen=True)
class Voice:
    key: str
    name: str
    gender: str
    detail: str
    repo: str
    revision: str
    model_file: str
    config_file: str
    license_note: str
    engine: str = "piper"
    model_voice: str = ""

    @property
    def directory(self) -> Path:
        return VOICE_ROOT / self.key

    @property
    def model_path(self) -> Path:
        return self.directory / self.model_file

    @property
    def config_path(self) -> Path:
        return self.directory / f"{self.model_file}.json"


VOICES = (
    Voice("pt_BR-faber-medium", "Faber", "Masculina", "Piper · medium · já instalada",
          "rhasspy/piper-voices", "v1.0.0", "pt_BR-faber-medium.onnx",
          "pt_BR-faber-medium.onnx.json", "Pesos não redistribuídos; veja assets/voices/README.md."),
    *(Voice(f"supertonic:{name}", title, gender,
            f"Supertonic 3 · perfil {name} · CPU local",
            "Supertone/supertonic-3", "", "", "",
            "Modelo OpenRAIL-M: requer atribuição e tem restrições de uso; veja a licença upstream.",
            engine="supertonic", model_voice=name)
      for name, title, gender in (
          ("F1", "Soreli", "Feminina"),
          ("F2", "Averin", "Feminina"),
          ("F3", "Neriva", "Feminina"),
          ("F4", "Velune", "Feminina"),
          ("F5", "Calira", "Feminina"),
          ("M1", "Jorven", "Masculina"),
          ("M2", "Orvel", "Masculina"),
          ("M3", "Tavren", "Masculina"),
          ("M4", "Kaelor", "Masculina"),
          ("M5", "Zevran", "Masculina"),
      )),
)
VOICE_BY_KEY = {voice.key: voice for voice in VOICES}


def voice_files(voice_id: str) -> tuple[Path, Path]:
    voice = VOICE_BY_KEY.get(str(voice_id or ""))
    if voice is None:
        raise ValueError("Voz local desconhecida.")
    return voice.model_path, voice.config_path


def voice_available(voice_id: str) -> bool:
    voice = VOICE_BY_KEY.get(str(voice_id or ""))
    if voice and voice.engine == "supertonic":
        return _supertonic_marker(voice).is_file()
    try:
        model, config = voice_files(voice_id)
        return model.is_file() and config.is_file() and model.stat().st_size > 1_000_000
    except (OSError, ValueError):
        return False


def voice_runtime_available(voice_id: str) -> bool:
    voice = VOICE_BY_KEY.get(str(voice_id or ""))
    if voice is None:
        return False
    try:
        return importlib.util.find_spec("supertonic" if voice.engine == "supertonic" else "piper") is not None
    except (ImportError, ValueError, OSError):
        return False


def _supertonic_marker(voice: Voice) -> Path:
    return VOICE_ROOT / ".supertonic" / f"{voice.model_voice}.ready"


def _download(url: str, destination: Path, maximum: int = 100 * 1024 * 1024,
              progress=None) -> None:
    """Download one model/config, resuming a partial transfer when possible."""
    partial = destination.with_suffix(destination.suffix + ".part")
    last_error = None
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "Aurora-Local-TTS/1.1", "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=120) as response:
                # Some mirrors ignore Range. Restart cleanly instead of
                # appending a second copy of the file.
                append = offset > 0 and response.status == 206
                if offset and not append:
                    offset = 0
                mode = "ab" if append else "wb"
                length = response.headers.get("Content-Length")
                expected = offset + int(length) if length and length.isdigit() else 0
                with partial.open(mode) as output:
                    total = offset
                    if progress:
                        progress(total, expected)
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > maximum:
                            raise ValueError("O arquivo de voz excede o limite esperado de 100 MiB.")
                        output.write(chunk)
                        if progress:
                            progress(total, expected)
                    output.flush()
                    os.fsync(output.fileno())
                if expected and total != expected:
                    raise ConnectionError(f"Transferência incompleta ({total} de {expected} bytes).")
                # Config JSON files are only a few KiB; the ONNX model size is
                # checked separately after both files have arrived.
                if total < 100:
                    raise ValueError("O arquivo baixado parece incompleto.")
                os.replace(partial, destination)
                return
        except (HTTPError, URLError, TimeoutError, ConnectionError, IncompleteRead, OSError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(.6 * (attempt + 1))
                continue
            break
    if isinstance(last_error, HTTPError):
        raise RuntimeError(f"Servidor de vozes respondeu HTTP {last_error.code}.") from last_error
    raise RuntimeError(f"A conexão caiu durante o download da voz: {last_error or 'erro de rede'}.") from last_error


def ensure_voice(voice_id: str, progress=None) -> Path:
    """Install only the requested voice, atomically, under private user data."""
    voice = VOICE_BY_KEY.get(str(voice_id or ""))
    if voice is None:
        raise ValueError("Voz local desconhecida.")
    if voice.engine == "supertonic":
        marker = _supertonic_marker(voice)
        if marker.is_file():
            return marker
        try:
            from supertonic import TTS
            synthesizer = TTS(auto_download=True)
            synthesizer.get_voice_style(voice_name=voice.model_voice)
        except Exception as exc:
            raise RuntimeError(f"Não consegui preparar Supertonic: {exc}") from exc
        marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(marker.parent, 0o700)
        marker.write_text("supertonic-3\n", encoding="utf-8")
        os.chmod(marker, 0o600)
        return marker
    model, config = voice.model_path, voice.config_path
    if voice_available(voice.key):
        return model

    relative = "pt/pt_BR/faber/medium"
    source_files = (voice.model_file, voice.config_file)

    VOICE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(VOICE_ROOT, 0o700)
    temporary = Path(tempfile.mkdtemp(prefix=f".{voice.key}-", dir=VOICE_ROOT))
    try:
        for filename in source_files:
            path = f"{relative}/{filename}"
            url = f"https://huggingface.co/{voice.repo}/resolve/{voice.revision}/{path}"
            target_name = voice.model_file if filename == voice.model_file else f"{voice.model_file}.json"
            _download(url, temporary / target_name,
                      progress=(lambda done, total, label=filename: progress(label, done, total)) if progress else None)
        staged_model = temporary / voice.model_file
        staged_config = temporary / f"{voice.model_file}.json"
        if not staged_model.is_file() or staged_model.stat().st_size <= 1_000_000:
            raise ValueError("O modelo de voz baixado é inválido.")
        config_data = json.loads(staged_config.read_text(encoding="utf-8"))
        if not isinstance(config_data, dict) or not isinstance(config_data.get("audio"), dict):
            raise ValueError("A configuração Piper dessa voz está inválida.")
        target = voice.directory
        if target.exists():
            shutil.rmtree(target)
        os.replace(temporary, target)
        os.chmod(target, 0o700)
        return model
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)

