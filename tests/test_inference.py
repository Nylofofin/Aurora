import json

import aurora_core.llm.inference as inference_module


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


def test_agent_speaks_action_result_instead_of_model_reinterpreting_it(monkeypatch):
    class Response:
        def __init__(self, message): self.message = message
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def __iter__(self):
            yield json.dumps({"message": self.message}).encode()

    responses = iter((
        Response({"tool_calls": [{"function": {
            "name": "volume_control", "arguments": {"action": "set", "value": 30}
        }}]}),
        Response({"content": "Não consegui confirmar a ação."}),
    ))
    monkeypatch.setattr(inference_module.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(inference_module.Inference, "execute_tool",
                        lambda *_args, **_kwargs: "Volume ajustado para 30%.")
    cfg = {
        "endpoint": "http://localhost:11434", "model": "gemma4:test",
        "keep_alive": "5m", "num_ctx": 1024, "agent_num_ctx": 1024,
        "agent_num_predict": 96, "num_thread": 4, "num_gpu": 99,
    }
    worker = inference_module.Inference(cfg, "coloque o volume em 30%", use_tools=True)
    sentences, results = [], []
    worker.sentence.connect(sentences.append)
    worker.result.connect(results.append)

    worker.run()

    assert sentences == ["Volume ajustado para 30%."]
    assert results == ["Volume ajustado para 30%."]


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
