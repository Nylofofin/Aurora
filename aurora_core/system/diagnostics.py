"""Read-only experimental diagnostics for the local Aurora installation."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import urllib.request

from ..config import VOSK_PATH, local_endpoint


_REQUIRED_MODULES = (
    ("PySide6", "PySide6"),
    ("SpeechRecognition", "speech_recognition"),
    ("sounddevice", "sounddevice"),
    ("Vosk", "vosk"),
    ("Edge TTS", "edge_tts"),
    ("certifi", "certifi"),
)


def _ollama_status(cfg: dict) -> str:
    endpoint = str(cfg.get("endpoint", ""))
    if not local_endpoint(endpoint):
        return "Ollama local: endpoint recusado"
    request = urllib.request.Request(endpoint.rstrip("/") + "/api/tags")
    try:
        with urllib.request.urlopen(request, timeout=1.0) as response:
            payload = json.loads(response.read(1_000_000))
        models = payload.get("models", []) if isinstance(payload, dict) else []
        names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
    except Exception:
        return "Ollama local: indisponível"

    def present(expected: str) -> bool:
        return any(name == expected or name.startswith(expected + ":") for name in names)

    conversation = present(str(cfg.get("model", "")))
    agent_model = str(cfg.get("agent_model", ""))
    agent = present(agent_model) if agent_model else False
    if conversation and agent:
        return "Ollama local: ativo, modelos de conversa e agente instalados"
    if conversation:
        return "Ollama local: ativo, modelo de conversa instalado; modelo de agente ausente"
    return "Ollama local: ativo, modelo de conversa ausente"


def _voice_status() -> str:
    missing = [label for label, module in _REQUIRED_MODULES
               if importlib.util.find_spec(module) is None]
    layouts = (
        ("final.mdl", "Gr.fst", "HCLr.fst", "mfcc.conf"),
        ("am/final.mdl", "graph/HCLG.fst", "conf/mfcc.conf"),
    )
    model_ready = any(all((VOSK_PATH / item).is_file() for item in layout)
                      for layout in layouts)
    if missing:
        return "dependências principais ausentes (" + ", ".join(missing) + ")"
    if not model_ready:
        return "dependências principais instaladas; modelo Vosk ausente ou incompleto"
    return "dependências principais instaladas e modelo Vosk presente"


def _desktop_status() -> str:
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    x11 = bool(os.environ.get("DISPLAY"))
    if wayland and x11:
        session = "sessão Wayland com XWayland disponível"
    elif wayland:
        session = "sessão Wayland sem XWayland; a interface configurada pode não iniciar"
    elif x11:
        session = "sessão X11"
    else:
        session = "nenhuma sessão gráfica detectada"
    if not shutil.which("wpctl"):
        session += "; controle de volume indisponível (wpctl ausente)"
    return session


def run_local_diagnostics(cfg: dict) -> str:
    """Summarize local prerequisites without sending data or changing state."""
    if not isinstance(cfg, dict):
        cfg = {}
    return "Diagnóstico experimental, somente leitura: " + "; ".join(
        (_ollama_status(cfg), _voice_status(), _desktop_status())
    ) + ". Não testei reconhecimento online, voz Edge, OBS ou Spotify."
