# SPDX-License-Identifier: GPL-3.0-only
import io
import json
from pathlib import Path
from types import SimpleNamespace

from aurora_core.system import actions
from aurora_core.system import diagnostics
from aurora_core.system.commands import parse_local_command


def test_diagnostic_command_is_a_direct_read_only_action():
    assert parse_local_command("Aurora, faça um diagnóstico da Aurora") == (
        "system_diagnostics", {}
    )
    assert parse_local_command("verifique se a assistente está funcionando") == (
        "system_diagnostics", {}
    )


def test_diagnostic_action_dispatches_without_the_llm(monkeypatch):
    monkeypatch.setattr(actions, "run_local_diagnostics", lambda cfg: f"local: {cfg['model']}")

    result = actions.execute_action(
        SimpleNamespace(cfg={"model": "test-model"}), "system_diagnostics", {}
    )

    assert result == "local: test-model"


def test_diagnostics_report_local_models_voice_and_xwayland(monkeypatch, tmp_path):
    for name in ("final.mdl", "Gr.fst", "HCLr.fst", "mfcc.conf"):
        (tmp_path / name).write_bytes(b"model")
    monkeypatch.setattr(diagnostics, "VOSK_PATH", tmp_path)
    stt_model = tmp_path / "ggml-base-q5_1.bin"
    stt_model.touch()
    stt_model.open("r+b").truncate(20_000_001)
    monkeypatch.setattr(diagnostics, "STT_MODEL_PATH", stt_model)
    monkeypatch.setattr(diagnostics.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/wpctl")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    payload = {"models": [{"name": "gemma3:1b-it-qat"}, {"name": "gemma4:e2b-it-q4_K_M"}]}
    monkeypatch.setattr(
        diagnostics.urllib.request,
        "urlopen",
        lambda request, timeout: Response(json.dumps(payload).encode()),
    )
    result = diagnostics.run_local_diagnostics({
        "endpoint": "http://127.0.0.1:11434",
        "model": "gemma3:1b-it-qat",
        "agent_model": "gemma4:e2b-it-q4_K_M",
    })

    assert "Ollama local: ativo, modelos de conversa e agente instalados" in result
    assert "modelos locais Vosk (wake word) e Whisper.cpp (transcrição) presentes" in result
    assert "Wayland com XWayland disponível" in result
    assert "somente leitura" in result
    assert "Não testei reconhecimento online" in result


def test_diagnostics_never_queries_a_remote_ollama_endpoint(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("diagnóstico tentou acessar rede")

    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(diagnostics.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(diagnostics, "VOSK_PATH", Path("/missing-vosk-model"))

    result = diagnostics.run_local_diagnostics({
        "endpoint": "https://example.invalid",
        "model": "conversation",
        "agent_model": "agent",
    })

    assert "endpoint recusado" in result
    assert "example.invalid" not in result


def test_diagnostics_detect_incomplete_vosk_model(monkeypatch, tmp_path):
    (tmp_path / "final.mdl").write_bytes(b"model")
    monkeypatch.setattr(diagnostics, "VOSK_PATH", tmp_path)
    monkeypatch.setattr(diagnostics.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(OSError()))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    result = diagnostics.run_local_diagnostics({"endpoint": "http://127.0.0.1:11434"})

    assert "modelo Vosk ausente ou incompleto" in result
    assert "nenhuma sessão gráfica detectada" in result


def test_diagnostics_warn_when_wayland_has_no_xwayland(monkeypatch):
    monkeypatch.setattr(diagnostics.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/wpctl")
    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(diagnostics, "VOSK_PATH", Path("/missing-vosk-model"))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)

    result = diagnostics.run_local_diagnostics({"endpoint": "http://127.0.0.1:11434"})

    assert "Wayland sem XWayland" in result


def test_service_diagnostics_only_reads_user_unit_state(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: "/usr/bin/systemctl")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="active\nenabled\n")

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)

    result = diagnostics._service_status()

    assert result == "serviço systemd --user: active, inicialização enabled"
    assert calls[0][0][1:4] == ["--user", "show", "aurora.service"]
    assert calls[0][1]["timeout"] <= 2
