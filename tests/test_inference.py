# SPDX-License-Identifier: GPL-3.0-only
import json
import threading
import time

import aurora_core.llm.inference as inference_module
from aurora_core.web.language import likely_portuguese, likely_spanish


def test_spanish_output_is_detected_and_never_spoken_as_portuguese_when_translation_fails(monkeypatch):
    spanish = "La grabación comenzó correctamente. Ya puedes pedirme que la detenga."
    portuguese = "A gravação começou corretamente. Você pode pedir para eu parar."
    assert likely_spanish(spanish)
    assert not likely_spanish(portuguese)
    assert likely_portuguese(portuguese)

    cfg = {"endpoint": "http://localhost:11434", "model": "gemma3:1b",
           "keep_alive": "5m", "num_ctx": 1024, "num_thread": 4, "num_gpu": 99}
    worker = inference_module.Inference(cfg, "", response_language="Português brasileiro")
    assert worker._needs_translation(spanish)
    monkeypatch.setattr(worker, "translate_to_language", lambda *_args: spanish)
    assert worker._translate_before_speaking(spanish) == (
        "Não consegui responder em português agora. Pode repetir, por favor?"
    )


def test_spanish_output_is_translated_before_it_is_spoken(monkeypatch):
    cfg = {"endpoint": "http://localhost:11434", "model": "gemma3:1b",
           "keep_alive": "5m", "num_ctx": 1024, "num_thread": 4, "num_gpu": 99}
    worker = inference_module.Inference(cfg, "", response_language="Português brasileiro")
    monkeypatch.setattr(worker, "translate_to_language", lambda *_args: "A gravação começou corretamente.")
    assert worker._translate_before_speaking("La grabación comenzó correctamente.") == (
        "A gravação começou corretamente."
    )


def test_short_spanish_and_english_voice_lines_are_detected():
    from aurora_core.web.language import likely_english, likely_spanish

    assert likely_spanish("Grabación iniciada.")
    assert likely_english("Recording started.")


def test_failed_translation_never_returns_the_foreign_original(monkeypatch):
    cfg = {"endpoint": "http://localhost:11434", "model": "gemma3:1b",
           "keep_alive": "5m", "num_ctx": 1024, "num_thread": 4, "num_gpu": 99}
    worker = inference_module.Inference(cfg, "", response_language="Português brasileiro")
    spanish = "Grabación iniciada."
    monkeypatch.setattr(worker, "translate_to_language", lambda *_args: spanish)
    assert worker._translate_before_speaking(spanish) == (
        "Não consegui responder em português agora. Pode repetir, por favor?"
    )
    monkeypatch.setattr(worker, "translate_to_language", lambda *_args: "")
    assert worker._translate_before_speaking("Recording started.") == (
        "Não consegui responder em português agora. Pode repetir, por favor?"
    )


def test_inference_translates_spanish_sentences_before_emitting_them(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def __iter__(self):
            yield json.dumps({"message": {"content": (
                "La grabación comenzó correctamente. Ya puedes detenerla."
            )}}).encode()

    monkeypatch.setattr(inference_module.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: Response())
    translations = {
        "La grabación comenzó correctamente.": "A gravação começou corretamente.",
        "Ya puedes detenerla.": "Você já pode pedir para eu parar.",
    }
    monkeypatch.setattr(inference_module.Inference, "translate_to_language",
                        lambda _self, text, _language: translations[text])
    cfg = {"endpoint": "http://localhost:11434", "model": "gemma3:1b",
           "keep_alive": "5m", "num_ctx": 1024, "num_thread": 4, "num_gpu": 99}
    worker = inference_module.Inference(cfg, "Responda em português")
    spoken, results = [], []
    worker.sentence.connect(spoken.append)
    worker.result.connect(results.append)

    worker.run()

    assert spoken == list(translations.values())
    assert results == [" ".join(translations.values())]


def test_translation_waits_until_the_current_ollama_stream_is_closed(monkeypatch):
    class Response:
        closed = False
        def __enter__(self): return self
        def __exit__(self, *_args): self.closed = True
        def __iter__(self):
            yield json.dumps({"message": {"content": "Wrong language sentence. Next sentence."}}).encode()

    response = Response()
    monkeypatch.setattr(inference_module.urllib.request, "urlopen", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(inference_module, "likely_english", lambda text: text.startswith("Wrong language"))
    monkeypatch.setattr(inference_module, "likely_portuguese", lambda _text: False)
    translated = []

    def translate(self, text, language):
        assert self.active_response is None
        assert response.closed
        translated.append((text, language))
        return "Frase traduzida."

    monkeypatch.setattr(inference_module.Inference, "translate_to_language", translate)
    cfg = {
        "endpoint": "http://localhost:11434", "model": "gemma3:1b",
        "keep_alive": "5m", "num_ctx": 1024, "num_thread": 4, "num_gpu": 99,
    }
    worker = inference_module.Inference(cfg, "Responda diretamente")
    spoken, results, errors = [], [], []
    worker.sentence.connect(spoken.append)
    worker.result.connect(results.append)
    worker.error.connect(errors.append)

    worker.run()

    assert not errors
    assert translated == [("Wrong language sentence.", "Português brasileiro")]
    assert spoken == ["Frase traduzida.", "Next sentence."]
    assert results == ["Frase traduzida. Next sentence."]


def test_screenshot_action_returns_without_a_second_model_turn(monkeypatch):
    class Response:
        def __init__(self, message): self.message = message
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def __iter__(self):
            yield json.dumps({"message": self.message}).encode()

    responses = iter((Response({"tool_calls": [{"function": {
        "name": "take_screenshot", "arguments": {}
    }}]}),))
    requests = []
    monkeypatch.setattr(inference_module.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: requests.append(_args[0]) or next(responses))
    monkeypatch.setattr(inference_module.Inference, "execute_tool",
                        lambda *_args, **_kwargs: "Salvei a captura em Imagens/captura.png.")
    cfg = {
        "endpoint": "http://localhost:11434", "model": "gemma4:test",
        "keep_alive": "5m", "num_ctx": 1024, "agent_num_ctx": 1024,
        "agent_num_predict": 96, "num_thread": 4, "num_gpu": 99,
    }
    worker = inference_module.Inference(cfg, "Faça uma captura de tela", use_tools=True)
    sentences, results = [], []
    worker.sentence.connect(sentences.append)
    worker.result.connect(results.append)

    worker.run()

    assert sentences == ["Salvei a captura em Imagens/captura.png."]
    assert results == ["Salvei a captura em Imagens/captura.png."]
    assert len(requests) == 1


def test_cancel_before_tool_dispatch_prevents_local_side_effect(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): worker.cancelled = True
        def __iter__(self):
            yield json.dumps({"message": {"tool_calls": [{"function": {
                "name": "open_application", "arguments": {"command": "Editor"}
            }}]}}).encode()

    monkeypatch.setattr(inference_module.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    cfg = {
        "endpoint": "http://localhost:11434", "model": "gemma4:test",
        "keep_alive": "5m", "num_ctx": 1024, "agent_num_ctx": 1024,
        "agent_num_predict": 96, "num_thread": 4, "num_gpu": 99,
    }
    worker = inference_module.Inference(cfg, "Abra o Editor", use_tools=True)
    dispatched = []
    monkeypatch.setattr(worker, "execute_tool", lambda name, args: dispatched.append((name, args)))

    worker.run()

    assert worker.cancelled
    assert dispatched == []


def test_independent_local_read_tools_run_in_parallel_and_keep_model_order(monkeypatch):
    cfg = {"endpoint": "http://localhost:11434", "model": "gemma4:test",
           "keep_alive": "5m", "num_ctx": 1024, "agent_num_ctx": 1024,
           "agent_num_predict": 96, "num_thread": 4, "num_gpu": 99}
    worker = inference_module.Inference(cfg, "Consulte hardware e janelas", use_tools=True)
    monkeypatch.setattr(inference_module, "local_worker_limit", lambda count: 2)
    gate = threading.Barrier(2)
    calls = [
        {"function": {"name": "get_system_info", "arguments": {}}},
        {"function": {"name": "inspect_accessible_windows", "arguments": {"application": "Editor"}}},
    ]

    def execute(name, _args):
        gate.wait(timeout=1)
        if name == "get_system_info":
            time.sleep(0.03)
        return name

    monkeypatch.setattr(worker, "execute_tool", execute)
    events = []
    worker.progress.connect(events.append)
    outputs = worker._execute_tool_batch(calls)

    assert [output for _call, _name, output in outputs] == [
        "get_system_info", "inspect_accessible_windows"
    ]
    assert events[0]["mode"] == "local"
    assert events[0]["workers"] == 2
    assert events[-1]["completed"] == 2


def test_local_mutations_stay_sequential(monkeypatch):
    cfg = {"endpoint": "http://localhost:11434", "model": "gemma4:test",
           "keep_alive": "5m", "num_ctx": 1024, "agent_num_ctx": 1024,
           "agent_num_predict": 96, "num_thread": 4, "num_gpu": 99}
    worker = inference_module.Inference(cfg, "Abra o editor e verifique o hardware", use_tools=True)
    calls = [
        {"function": {"name": "open_application", "arguments": {"command": "Editor"}}},
        {"function": {"name": "get_system_info", "arguments": {}}},
    ]
    seen = []
    monkeypatch.setattr(worker, "execute_tool", lambda name, _args: seen.append(name) or name)
    monkeypatch.setattr(inference_module, "local_worker_limit",
                        lambda _count: (_ for _ in ()).throw(AssertionError("parallel fan-out not allowed")))

    outputs = worker._execute_tool_batch(calls)

    assert seen == ["open_application", "get_system_info"]
    assert [output for _call, _name, output in outputs] == seen
