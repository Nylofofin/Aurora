# SPDX-License-Identifier: GPL-3.0-only
from aurora_core.llm.inference import ACTION_TOOL_NAMES, Inference, _tool_progress_label
import aurora_core.llm.tools as tools_module
from aurora_core.llm.tools import TOOLS


def test_screen_injection_tools_are_not_exposed_on_wayland_build():
    names = {tool["function"]["name"] for tool in TOOLS}
    assert "type_text" not in names
    assert "click_screen" not in names


def test_unavailable_screen_tool_cannot_wait_for_approval():
    inference = Inference({"model": "test"}, "test", use_tools=True)
    assert inference.execute_tool("type_text", {"text": "unsafe"}) == "Ferramenta indisponível."
    assert inference.execute_tool("click_screen", {"x": 1, "y": 1}) == "Ferramenta indisponível."


def test_system_health_tool_is_read_only_and_returns_structured_report(monkeypatch):
    report = {
        "rpm": {"ok": True, "packages": ["pkg-a"], "security_count": 1},
        "flatpak": {"ok": True, "apps": [], "available": True},
        "firmware": {"ok": True, "devices": [], "available": False},
        "warnings": [],
    }
    seen = []
    monkeypatch.setattr(tools_module, "check_system_health", lambda cfg: seen.append(cfg) or report)
    monkeypatch.setattr(tools_module, "format_health_response", lambda value: "RPM: 1 atualização de segurança.")

    result = tools_module.execute_local_tool("check_system_health", {}, {"model": "local-test"})

    assert seen == [{"model": "local-test"}]
    assert result == "RPM: 1 atualização de segurança."
    assert "check_system_health" not in ACTION_TOOL_NAMES


def test_system_health_tool_is_advertised_as_read_only():
    definition = next(tool["function"] for tool in TOOLS if tool["function"]["name"] == "check_system_health")
    assert "sem alterar nada" in definition["description"]
    assert definition["parameters"]["required"] == []
    assert _tool_progress_label("check_system_health") == "Verificando o estado do sistema"


def test_file_search_skips_hidden_private_directories(monkeypatch, tmp_path):
    visited = []
    monkeypatch.setattr(tools_module.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(tools_module, "audit_action", lambda *_args: None)

    def walk(_root):
        dirs = [".ssh", ".gnupg", ".config", "Documents"]
        yield str(tmp_path), dirs, []
        visited.extend(dirs)
        yield str(tmp_path / "Documents"), [], ["report.txt"]

    monkeypatch.setattr(tools_module.os, "walk", walk)
    result = tools_module.execute_local_tool("search_files", {"query": "report"})
    assert result == str(tmp_path / "Documents" / "report.txt")
    assert visited == ["Documents"]
