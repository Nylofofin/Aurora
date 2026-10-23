# SPDX-License-Identifier: GPL-3.0-only
from aurora_core.llm.inference import Inference
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
