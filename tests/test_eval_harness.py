# SPDX-License-Identifier: GPL-3.0-only
from scripts.eval_search import EvalService, ResearchCardStub, Trace, install_trace, restore_trace
import aurora_core.web.pipeline as web_pipeline
import aurora_core.web.requests as web_requests


def test_eval_service_starts_with_one_shot_request_active():
    service = EvalService({})

    assert service.voice.request_active.is_set()
    assert not service.voice.interrupt_active.is_set()
    assert service.response_language == "Português brasileiro"
    assert service._mobile_audio_owned() is False


def test_eval_service_captures_speech_without_audio_output():
    service = EvalService({})

    service.speak_in_selected_language("Resposta de teste")

    assert service.speaker.parts == ["Resposta de teste"]


def test_eval_service_accepts_streamed_sentence_and_completion_generation():
    service = EvalService({})
    service.request_generation = 1
    service.queue_sentence("Início de frase", 1)
    service.answer_done("Resposta final", 1)

    assert service.response_summary == "Resposta final"
    assert service.speaker.parts == ["Resposta final"]
    assert service.done


def test_eval_research_card_stub_records_progress_without_gui():
    card = ResearchCardStub()
    card.begin(7, "consulta")
    card.update_progress(7, {"stage": "searching"})
    card.finish(7, "resumo")

    assert [event["stage"] for event in card.events] == ["searching", "finished"]


def test_eval_trace_patches_search_request_module_and_restores_it(monkeypatch):
    monkeypatch.setattr(web_pipeline, "search_public_web", lambda *_args, **_kwargs: "fixture result")
    originals = install_trace(Trace())
    try:
        assert web_requests.search_public_web is web_pipeline.search_public_web
        assert web_requests.search_public_web("query", progress=lambda _event: None) == "fixture result"
    finally:
        restore_trace(originals)

    assert web_requests.search_public_web is web_pipeline.search_public_web


def test_eval_record_has_machine_readable_freshness_sources_and_latency():
    from scripts.eval_search import build_eval_record

    trace = Trace()
    trace.raw_result_text = "Fonte oficial 23/10/2026 — https://example.org/news"
    trace.filter_counts["data_pagina_ausente"] = 1
    trace.pages_read.append({"url": "https://example.org/news"})
    trace.network_requests.append({
        "kind": "Bing RSS", "elapsed_ms": 240, "status": 200,
        "extracted": 4, "after_pipeline": 1,
    })

    record = build_eval_record(8, "o que aconteceu hoje?", "Resposta com fonte.", trace,
                              1.25, True, "sinal de atualidade")

    assert record["elapsed_ms"] == 1250
    assert record["decision"]["search"] is True
    assert record["provider_requests"][0]["extracted"] == 4
    assert record["filters"]["data_pagina_ausente"] == 1
    assert record["pages_attempted"] == 1
    assert record["sources"][0]["domain"] == "example.org"
