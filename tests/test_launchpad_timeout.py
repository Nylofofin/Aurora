# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
from pathlib import Path
import subprocess
import sys
import types


def _load_launchpad(monkeypatch):
    gi = types.ModuleType("gi")
    gi.require_version = lambda *_args: None
    repository = types.ModuleType("gi.repository")
    repository.Adw = types.SimpleNamespace(Application=type("Application", (), {}))
    repository.Gdk = types.SimpleNamespace()
    repository.Gio = types.SimpleNamespace()
    repository.GLib = types.SimpleNamespace()
    repository.Gtk = types.SimpleNamespace()
    gi.repository = repository
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "launchpad"))

    script = Path(__file__).resolve().parents[1] / "launchpad" / "aurora_launchpad.py"
    spec = importlib.util.spec_from_file_location("aurora_launchpad_timeout_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installation_health_timeout_is_reported_without_stopping_launchpad(monkeypatch):
    module = _load_launchpad(monkeypatch)
    launchpad = object.__new__(module.Launchpad)

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("systemctl", 5)

    monkeypatch.setattr(module.subprocess, "run", timeout)

    health = launchpad._installation_health()

    assert health.state == "unknown"
    assert not health.repairable
    assert "tempo limite" in health.details[0]
    assert launchpad.install_health_error == health.details[0]


def test_maintenance_refresh_reports_service_timeout(monkeypatch):
    module = _load_launchpad(monkeypatch)

    class Label:
        text = ""

        def set_text(self, text):
            self.text = text

    launchpad = object.__new__(module.Launchpad)
    launchpad.maintenance_status = Label()

    def timeout():
        return module.InstallationHealth(
            "unknown", ("O serviço não respondeu dentro do tempo limite.",), False
        )

    monkeypatch.setattr(launchpad, "_installation_health", timeout)

    launchpad._refresh_maintenance_status()

    assert "Tente atualizar" in launchpad.maintenance_status.text


def test_service_status_timeout_shows_a_friendly_dialog(monkeypatch):
    module = _load_launchpad(monkeypatch)
    dialogs = []

    class Box:
        def __init__(self):
            self.children = []

        def set_margin_top(self, _value):
            pass

        set_margin_bottom = set_margin_top
        set_margin_start = set_margin_top
        set_margin_end = set_margin_top

        def append(self, child):
            self.children.append(child)

    class Dialog:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.box = Box()
            dialogs.append(self)

        def add_button(self, *_args):
            pass

        def get_content_area(self):
            return self.box

        def connect(self, *_args):
            pass

        def present(self):
            self.presented = True

    module.Gtk.Dialog = Dialog
    module.Gtk.ResponseType = types.SimpleNamespace(CLOSE=1)
    launchpad = object.__new__(module.Launchpad)
    launchpad.window = object()
    launchpad._label = lambda text, *_args: text

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("systemctl", 15)

    monkeypatch.setattr(module.subprocess, "run", timeout)

    launchpad._show_service_status()

    assert dialogs[0].kwargs["title"] == "Status indisponível"
    assert dialogs[0].presented
    assert "Tente consultar" in dialogs[0].box.children[0]
