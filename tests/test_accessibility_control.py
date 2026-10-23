# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

import pytest

import aurora_core.service as service_module
import aurora_core.system.accessibility as accessibility
import aurora_core.system.atspi_worker as worker
import aurora_core.system.commands as commands
from aurora_core.llm.tools import TOOLS


def _desktop_app(tmp_path):
    return {
        "file": tmp_path / "org.example.Editor.desktop",
        "name": "Example Editor",
        "class": "example-editor",
        "exec": "example-editor %U",
    }


def test_screen_automation_requires_exact_desktop_id_allowlist(monkeypatch, tmp_path):
    monkeypatch.setattr(accessibility, "find_desktop_app", lambda _query: _desktop_app(tmp_path))

    app, error = accessibility._application_descriptor("Editor", ["example-editor"])
    assert app is None
    assert "allowlist" in error

    app, error = accessibility._application_descriptor("Editor", ["org.example.Editor"])
    assert error is None
    assert app["accessible_names"] == ["Example Editor", "example-editor", "org.example.Editor"]


def test_inspection_returns_names_only_and_uses_allowed_app(monkeypatch, tmp_path):
    monkeypatch.setattr(accessibility, "find_desktop_app", lambda _query: _desktop_app(tmp_path))
    monkeypatch.setattr(accessibility, "_audit", lambda *_args: None)
    calls = []

    def fake_worker(operation, app, **kwargs):
        calls.append((operation, app, kwargs))
        return {"ok": True, "windows": [{"title": "Editor", "controls": [{"role": "entry", "name": "Search"}]}]}

    monkeypatch.setattr(accessibility, "_call_worker", fake_worker)
    result = accessibility.inspect_accessible_windows("Editor", ["org.example.Editor"])

    assert "Editor" in result and "entry: Search" in result
    assert "secret document contents" not in result
    assert calls[0][0] == "inspect"


def test_text_insertion_is_bounded_and_does_not_return_or_log_text(monkeypatch, tmp_path):
    monkeypatch.setattr(accessibility, "find_desktop_app", lambda _query: _desktop_app(tmp_path))
    calls = []
    audit_rows = []
    monkeypatch.setattr(accessibility, "_audit", lambda action, outcome, details: audit_rows.append((action, outcome, details)))
    monkeypatch.setattr(accessibility, "_call_worker", lambda operation, app, **kwargs: (
        calls.append((operation, kwargs)) or {"ok": True, "window": "draft private text", "field": "Search", "characters": len(kwargs["text"])}
    ))

    result = accessibility.type_into_accessible_field(
        "Editor", "Editor", "Search", "draft private text", ["org.example.Editor"]
    )
    assert result == "Inseri 18 caracteres no campo “Search” em Example Editor."
    assert "draft private text" not in result
    assert calls[0][1]["text"] == "draft private text"
    assert "draft private text" not in repr(audit_rows)

    too_long = accessibility.type_into_accessible_field(
        "Editor", "Editor", "Search", "x" * 1001, ["org.example.Editor"]
    )
    assert "1000 caracteres" in too_long
    assert len(calls) == 1


def test_window_names_are_not_returned_or_logged_by_screen_focus(monkeypatch, tmp_path):
    monkeypatch.setattr(accessibility, "find_desktop_app", lambda _query: _desktop_app(tmp_path))
    audit_rows = []
    monkeypatch.setattr(accessibility, "_audit", lambda *args: audit_rows.append(args))
    monkeypatch.setattr(accessibility, "_call_worker", lambda *_args, **_kwargs: {
        "ok": True, "window": "private draft title",
    })

    result = accessibility.focus_accessible_window("Editor", "private draft title", ["org.example.Editor"])

    assert result == "Foquei uma janela de Example Editor."
    assert "private draft title" not in result
    assert "private draft title" not in repr(audit_rows)


def test_worker_rejects_credential_fields_before_insertion():
    class Desktop:
        childCount = 0

    with pytest.raises(RuntimeError, match="credenciais"):
        worker.type_text(Desktop(), {
            "field": "Password", "text": "should never type", "accessible_names": [],
        })


def test_worker_focus_accepts_namespaced_atspi_window_activate_action():
    class Action:
        nActions = 1
        def getName(self, _index): return "default.activate"
        def doAction(self, _index): return True

    class Component:
        def grabFocus(self): return False

    class Window:
        name = "Editor"
        childCount = 0
        def getRoleName(self): return "frame"
        def queryComponent(self): return Component()
        def queryAction(self): return Action()

    class App:
        name = "Example Editor"
        childCount = 1
        def getRoleName(self): return "application"
        def getChildAtIndex(self, _index): return Window()

    class Desktop:
        childCount = 1
        def getChildAtIndex(self, _index): return App()

    assert worker.focus(Desktop(), {
        "accessible_names": ["Example Editor"], "window": "Editor",
    }) == {"ok": True, "window": "Editor"}


def test_accessible_listing_never_reads_editable_control_value():
    class Entry:
        childCount = 0

        @property
        def name(self):
            raise AssertionError("editable value must not be read")

        def getRoleName(self):
            return "entry"

    class Window:
        childCount = 1

        def getRoleName(self):
            return "frame"

        def getChildAtIndex(self, index):
            assert index == 0
            return Entry()

    assert worker.list_controls(Window()) == [{"role": "entry", "name": "campo editável sem rótulo 1 (bloqueado)"}]


def test_only_unique_unlabelled_document_text_area_can_be_targeted():
    inserted = []

    class EditableText:
        def insertText(self, offset, text, length):
            inserted.append((offset, text, length))
            return True

    class TextArea:
        childCount = 0
        def getRoleName(self): return "text"
        def getRelationSet(self): return []
        def getState(self): return type("States", (), {"contains": lambda *_: False})()
        def queryComponent(self): return type("Component", (), {"grabFocus": lambda *_: True})()
        def queryText(self): return type("Text", (), {"get_caretOffset": lambda *_: 0})()
        def queryEditableText(self): return EditableText()

    class Window:
        name = "Editor"
        childCount = 1
        def getRoleName(self): return "frame"
        def getChildAtIndex(self, _index): return TextArea()
        def queryComponent(self): return type("Component", (), {"grabFocus": lambda *_: True})()

    assert worker.list_controls(Window()) == [{"role": "text", "name": worker.UNIQUE_UNLABELLED_TEXT}]

    class App:
        name = "Example Editor"
        childCount = 1
        def getRoleName(self): return "application"
        def getChildAtIndex(self, _index): return Window()

    class Desktop:
        childCount = 1
        def getChildAtIndex(self, _index): return App()

    result = worker.type_text(Desktop(), {
        "accessible_names": ["Example Editor"], "window": "Editor",
        "field": worker.UNIQUE_UNLABELLED_TEXT, "text": "temporary smoke test",
    })
    assert result["ok"]
    assert inserted == [(0, "temporary smoke test", 20)]


def test_multiple_unlabelled_text_areas_remain_blocked():
    class TextArea:
        childCount = 0
        def getRoleName(self): return "text"
        def getRelationSet(self): return []

    class Window:
        childCount = 2
        def getRoleName(self): return "frame"
        def getChildAtIndex(self, index): return TextArea()

    controls = worker.list_controls(Window())
    assert all(control["name"].endswith("(bloqueado)") for control in controls)


def test_direct_commands_keep_screen_control_arguments_explicit():
    assert commands.parse_local_command('foque a janela "Editor - sem título" do aplicativo "Example Editor"') == (
        "focus_accessible_window", {"window": "Editor - sem título", "application": "Example Editor"}
    )
    assert commands.parse_local_command('liste as janelas acessíveis do aplicativo "Example Editor"') == (
        "inspect_accessible_windows", {"application": "Example Editor"}
    )
    assert commands.parse_local_command(
        'digite "pesquisa" no campo "Search" da janela "Browser" do aplicativo "Example Browser"'
    ) == (
        "type_accessible_text", {
            "text": "pesquisa", "field": "Search", "window": "Browser", "application": "Example Browser"
        }
    )


def test_screen_text_action_requires_bubble_approval():
    class Orb:
        def set_mode(self, _mode):
            pass

    class Stub:
        orb = Orb()
        calls = []

        def request_approval(self, name, detail):
            self.calls.append((name, detail))

    stub = Stub()
    service_module.AuroraService.run_local_action(stub, "type_accessible_text", {"text": "approved text"})
    assert len(stub.calls) == 1
    assert stub.calls[0][0] == "type_accessible_text"


def test_voice_cancel_only_interrupts_pending_screen_control():
    class Stub:
        def __init__(self, pending):
            self.pending = pending
            self.cancelled = False

        def stop_conversation(self):
            self.cancelled = True

    for name in ("focus_accessible_window", "type_accessible_text"):
        stub = Stub({"name": name})
        service_module.AuroraService.cancel_pending_screen_control(stub)
        assert stub.cancelled

    for pending in (None, {"name": "take_screenshot"}, {"name": "close_application"}):
        stub = Stub(pending)
        service_module.AuroraService.cancel_pending_screen_control(stub)
        assert not stub.cancelled


def test_screen_control_tools_have_closed_arguments():
    by_name = {tool["function"]["name"]: tool["function"]["parameters"] for tool in TOOLS}
    assert by_name["focus_accessible_window"]["required"] == ["application", "window"]
    assert by_name["type_accessible_text"]["required"] == ["application", "window", "field", "text"]
