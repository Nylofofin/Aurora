from aurora_core.llm.inference import Inference
from aurora_core.llm.tools import TOOLS


def test_screen_injection_tools_are_not_exposed_on_wayland_build():
    names = {tool["function"]["name"] for tool in TOOLS}
    assert "type_text" not in names
    assert "click_screen" not in names


def test_unavailable_screen_tool_cannot_wait_for_approval():
    inference = Inference({"model": "test"}, "test", use_tools=True)
    assert inference.execute_tool("type_text", {"text": "unsafe"}) == "Ferramenta indisponível."
    assert inference.execute_tool("click_screen", {"x": 1, "y": 1}) == "Ferramenta indisponível."
