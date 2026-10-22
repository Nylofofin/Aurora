from scripts.eval_search import EvalService, Trace, install_trace, restore_trace
import aurora_core.web.pipeline as web_pipeline
import aurora_core.web.requests as web_requests


def test_eval_service_starts_with_one_shot_request_active():
    service = EvalService({})

    assert service.voice.request_active.is_set()
    assert not service.voice.interrupt_active.is_set()
    assert service.response_language == "Português brasileiro"


def test_eval_service_captures_speech_without_audio_output():
    service = EvalService({})

    service.speak_in_selected_language("Resposta de teste")

    assert service.speaker.parts == ["Resposta de teste"]


def test_eval_trace_patches_search_request_module_and_restores_it():
    original = web_requests.search_public_web
    originals = install_trace(Trace())
    try:
        assert web_requests.search_public_web is web_pipeline.search_public_web
    finally:
        restore_trace(originals)

    assert web_requests.search_public_web is original
