import aurora_core.service as service_module


def test_fast_search_answer_keeps_evidence_in_followup_context(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "ground_search_answer",
        lambda _question, answer, _evidence, _sources: answer,
    )

    class ServiceStub:
        current_prompt = "Quais são as notícias recentes?"
        request_generation = 7
        active_search_context = "Resultados da web usados como evidência: fonte e data"

        def quick_summary_done(self, summary, generation, context_extra=""):
            self.saved = (summary, generation, context_extra)

    stub = ServiceStub()
    service_module.AuroraService.quick_search_answer_done(
        stub, "Resumo confirmado.", 7, ["evidência"], ["fonte"],
    )

    assert stub.saved[0:2] == ("Resumo confirmado.", 7)
    assert "fonte e data" in stub.saved[2]
    assert stub.active_search_context == ""


def test_stale_fast_search_answer_does_not_consume_context(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "ground_search_answer",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must be ignored")),
    )

    class ServiceStub:
        current_prompt = "question"
        request_generation = 8
        active_search_context = "new request evidence"

    stub = ServiceStub()
    service_module.AuroraService.quick_search_answer_done(
        stub, "stale answer", 7, [], [],
    )

    assert stub.active_search_context == "new request evidence"
