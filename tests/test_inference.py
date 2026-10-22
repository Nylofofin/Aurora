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
