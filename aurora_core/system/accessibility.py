from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from .apps import find_desktop_app

_WORKER = Path(__file__).with_name("atspi_worker.py")
_MAX_TEXT_LENGTH = 1000


def _audit(action: str, outcome: str, details: dict) -> None:
    try:
        import aurora_integrations
        aurora_integrations._append_action_log(action, outcome, details)
    except Exception:
        pass


@lru_cache(maxsize=1)
def _atspi_python() -> str | None:
    """Find a system interpreter with the distro-provided AT-SPI bindings."""
    candidates = [getattr(sys, "_base_executable", ""), shutil.which("python3") or ""]
    for executable in dict.fromkeys(item for item in candidates if item):
        try:
            result = subprocess.run(
                [executable, "-c", "import pyatspi"], capture_output=True,
                text=True, timeout=2, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return executable
    return None


def _application_descriptor(query: str, allowed_apps: list[str]) -> tuple[dict | None, str | None]:
    app = find_desktop_app(query)
    if not app:
        return None, f"Não encontrei o aplicativo instalado “{query}”."
    desktop_id = app["file"].stem
    allowed = {str(item).strip().casefold() for item in allowed_apps if str(item).strip()}
    if desktop_id.casefold() not in allowed:
        return None, f"O aplicativo {app['name']} não está na allowlist de controle de tela da Aurora."
    names = {app["name"], desktop_id}
    if app.get("class"):
        names.add(app["class"])
    try:
        command = shlex.split(app.get("exec", ""))
        if command:
            executable = Path(command[0]).name
            if executable not in {"flatpak", "snap", "env"}:
                names.add(executable)
    except ValueError:
        pass
    return {"desktop_id": desktop_id, "label": app["name"], "accessible_names": sorted(names)}, None


def _call_worker(operation: str, app: dict, **arguments) -> dict:
    executable = _atspi_python()
    if not executable:
        raise RuntimeError("AT-SPI não está disponível no Python do sistema.")
    payload = {"operation": operation, "accessible_names": app["accessible_names"], **arguments}
    try:
        result = subprocess.run(
            [executable, str(_WORKER)], input=json.dumps(payload, ensure_ascii=False),
            capture_output=True, text=True, timeout=2, check=False,
            env={**os.environ, "PYTHONNOUSERSITE": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("O aplicativo demorou demais para responder pelo AT-SPI.") from exc
    if result.returncode:
        raise RuntimeError("Não consegui consultar a árvore de acessibilidade do aplicativo.")
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("A resposta da ponte AT-SPI foi inválida.") from exc
    if not isinstance(response, dict):
        raise RuntimeError("A resposta da ponte AT-SPI foi inválida.")
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "A ação AT-SPI falhou."))
    return response


def inspect_accessible_windows(application: str, allowed_apps: list[str]) -> str:
    app, error = _application_descriptor(application, allowed_apps)
    if error:
        _audit("screen_inspect", "denied", {"application": application})
        return error
    try:
        response = _call_worker("inspect", app)
    except Exception as exc:
        _audit("screen_inspect", "failed", {"application": app["desktop_id"]})
        return f"Não consegui inspecionar as janelas de {app['label']}: {exc}"
    windows = response.get("windows", [])
    if not windows:
        _audit("screen_inspect", "completed_empty", {"application": app["desktop_id"]})
        return f"Não encontrei janelas acessíveis abertas em {app['label']}."
    lines = []
    for window in windows[:8]:
        title = str(window.get("title") or "janela sem título")[:120]
        controls = window.get("controls", [])
        description = ", ".join(
            f"{str(control.get('role','controle'))}: {str(control.get('name') or '(sem nome)')[:60]}"
            for control in controls[:16]
        )
        lines.append(f"{title}" + (f" — {description}" if description else ""))
    _audit("screen_inspect", "completed", {"application": app["desktop_id"], "windows": len(windows)})
    return "Janelas e controles acessíveis (sem ler o conteúdo dos campos):\n" + "\n".join(lines)


def focus_accessible_window(application: str, window: str, allowed_apps: list[str]) -> str:
    app, error = _application_descriptor(application, allowed_apps)
    if error:
        _audit("screen_focus", "denied", {"application": application})
        return error
    try:
        response = _call_worker("focus", app, window=window)
    except Exception as exc:
        _audit("screen_focus", "failed", {"application": app["desktop_id"]})
        return f"Não consegui focar a janela de {app['label']}: {exc}"
    _audit("screen_focus", "focused", {"application": app["desktop_id"]})
    return f"Foquei uma janela de {app['label']}."


def type_into_accessible_field(
    application: str, window: str, field: str, text: str, allowed_apps: list[str]
) -> str:
    text = str(text)
    if not text or len(text) > _MAX_TEXT_LENGTH:
        _audit("screen_type", "denied", {"application": application, "characters": len(text)})
        return f"O texto precisa ter entre 1 e {_MAX_TEXT_LENGTH} caracteres."
    app, error = _application_descriptor(application, allowed_apps)
    if error:
        _audit("screen_type", "denied", {"application": application, "field": field, "characters": len(text)})
        return error
    try:
        response = _call_worker("type", app, window=window, field=field, text=text)
    except Exception as exc:
        _audit("screen_type", "failed", {"application": app["desktop_id"],
                                          "field": field, "characters": len(text)})
        return f"Não inseri texto em {app['label']}: {exc}"
    _audit("screen_type", "inserted", {"application": app["desktop_id"],
                                         "field": response["field"], "characters": len(text)})
    return f"Inseri {response['characters']} caracteres no campo “{response['field']}” em {app['label']}."
