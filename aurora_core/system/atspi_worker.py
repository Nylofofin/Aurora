"""Small subprocess bridge to distro PyAT-SPI, isolated from the Qt venv."""
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import re
import sys
import unicodedata

UNIQUE_UNLABELLED_TEXT = "área de texto única (sem rótulo)"


def role_name(node):
    try:
        return str(node.getRoleName()).casefold()
    except Exception:
        return ""


def normalized(value):
    return " ".join(unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold().split())


def descendants(root, limit=3000):
    stack = [root]
    visited = 0
    while stack and visited < limit:
        node = stack.pop()
        visited += 1
        yield node
        try:
            stack.extend(node.getChildAtIndex(index) for index in reversed(range(node.childCount)))
        except Exception:
            continue


def safe_name(node):
    try:
        return " ".join(str(node.name or "").split())[:160]
    except Exception:
        return ""


def editable_label(node):
    """Use only the label relation; an editable control's name can be its value."""
    try:
        import pyatspi
        for relation in node.getRelationSet():
            if relation.getRelationType() == pyatspi.RELATION_LABELLED_BY:
                if relation.getNTargets():
                    return safe_name(relation.getTarget(0))
    except Exception:
        pass
    return ""


def find_application(desktop, names):
    expected = {normalized(item) for item in names if normalized(item)}
    matches = []
    for index in range(desktop.childCount):
        try:
            app = desktop.getChildAtIndex(index)
            if app.getRoleName().casefold() == "application" and normalized(safe_name(app)) in expected:
                matches.append(app)
        except Exception:
            continue
    if len(matches) != 1:
        raise RuntimeError("Não encontrei uma única instância acessível desse aplicativo.")
    return matches[0]


def windows_for(app):
    windows = []
    for index in range(app.childCount):
        try:
            node = app.getChildAtIndex(index)
            if node.getRoleName().casefold() in {"window", "frame", "dialog"}:
                windows.append(node)
            else:
                for child in descendants(node):
                    if child is not node and child.getRoleName().casefold() in {"window", "frame", "dialog"}:
                        windows.append(child)
        except Exception:
            continue
    unique = []
    seen = set()
    for item in windows:
        key = (safe_name(item), item.getRoleName())
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def choose_window(windows, requested):
    if not requested:
        if len(windows) == 1:
            return windows[0]
        raise RuntimeError("Há várias janelas; informe o título exato da janela.")
    wanted = normalized(requested)
    matches = [item for item in windows if normalized(safe_name(item)) == wanted]
    if len(matches) != 1:
        raise RuntimeError("O título não identificou uma única janela. Consulte as janelas acessíveis e tente novamente.")
    return matches[0]


def list_controls(window):
    allowed_roles = {"entry", "text", "password text", "combo box", "push button", "toggle button", "check box", "radio button", "menu item"}
    controls = []
    editable_index = 0
    nodes = list(descendants(window))
    text_nodes = [node for node in nodes if role_name(node) == "text"]
    unique_text_area = len(text_nodes) == 1 and not editable_label(text_nodes[0])
    for node in nodes:
        try:
            role = role_name(node)
            if role in allowed_roles:
                if role in {"entry", "text", "combo box"}:
                    editable_index += 1
                    label = editable_label(node)
                    if not label:
                        label = UNIQUE_UNLABELLED_TEXT if role == "text" and unique_text_area else f"campo editável sem rótulo {editable_index} (bloqueado)"
                    controls.append({"role": role, "name": label})
                elif role == "password text":
                    controls.append({"role": role, "name": "campo de senha (bloqueado)"})
                else:
                    controls.append({"role": role, "name": safe_name(node)})
                if len(controls) >= 24:
                    break
        except Exception:
            continue
    return controls


def inspect(desktop, request):
    app = find_application(desktop, request.get("accessible_names", []))
    result = []
    for window in windows_for(app)[:8]:
        result.append({"title": safe_name(window), "controls": list_controls(window)})
    return {"ok": True, "windows": result}


def focus(desktop, request):
    app = find_application(desktop, request.get("accessible_names", []))
    window = choose_window(windows_for(app), request.get("window", ""))
    focus_window(window)
    return {"ok": True, "window": safe_name(window)}


def focus_window(window):
    focused = False
    try:
        focused = bool(window.queryComponent().grabFocus())
    except Exception:
        pass
    try:
        actions = window.queryAction()
        for index in range(actions.nActions):
            name = normalized(actions.getName(index))
            if name.rsplit(".", 1)[-1] in {"activate", "raise", "focus"}:
                focused = bool(actions.doAction(index)) or focused
                break
    except Exception:
        pass
    if not focused:
        raise RuntimeError("O aplicativo não permitiu focar essa janela pelo AT-SPI.")


def type_text(desktop, request):
    text = str(request.get("text", ""))
    field_name = str(request.get("field", ""))
    if not field_name or not text:
        raise RuntimeError("Informe um campo acessível e um texto não vazio.")
    if re.search(r"\b(password|senha|passcode|pin|token|credential|credencial)\b", normalized(field_name)):
        raise RuntimeError("Campos que parecem conter credenciais são bloqueados.")
    app = find_application(desktop, request.get("accessible_names", []))
    window = choose_window(windows_for(app), request.get("window", ""))
    wanted = normalized(field_name)
    candidates = []
    nodes = list(descendants(window))
    text_controls = [node for node in nodes if role_name(node) == "text"]
    unique_unlabelled_text = len(text_controls) == 1 and not editable_label(text_controls[0])
    for node in nodes:
        try:
            role = role_name(node)
            if role in {"entry", "text", "combo box"}:
                label = editable_label(node)
                if label and normalized(label) == wanted:
                    candidates.append((node, label))
                elif role == "text" and unique_unlabelled_text and wanted == normalized(UNIQUE_UNLABELLED_TEXT):
                    candidates.append((node, UNIQUE_UNLABELLED_TEXT))
        except Exception:
            continue
    if len(candidates) != 1:
        raise RuntimeError("O nome não identificou um único campo editável acessível.")
    target, label = candidates[0]
    try:
        states = target.getState()
        read_only = states.contains(43)  # ATSPI_STATE_READ_ONLY
    except Exception:
        read_only = False
    if read_only or role_name(target) == "password text" or re.search(
        r"\b(password|senha|passcode|pin|token|credential|credencial)\b", normalized(label)
    ):
        raise RuntimeError("Campos protegidos ou de senha nunca recebem texto da Aurora.")
    try:
        focus_window(window)
        offset = int(target.queryText().get_caretOffset())
        editable = target.queryEditableText()
        if not editable.insertText(offset, text, len(text)):
            raise RuntimeError("O campo recusou a inserção de texto.")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("O campo não oferece uma interface de texto editável segura.") from exc
    return {"ok": True, "window": safe_name(window), "field": label, "characters": len(text)}


def main():
    import pyatspi

    request = json.load(sys.stdin)
    desktop = pyatspi.Registry.getDesktop(0)
    operation = request.get("operation")
    handlers = {"inspect": inspect, "focus": focus, "type": type_text}
    handler = handlers.get(operation)
    if not handler:
        raise RuntimeError("Operação AT-SPI desconhecida.")
    return handler(desktop, request)


if __name__ == "__main__":
    try:
        print(json.dumps(main(), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(0)
