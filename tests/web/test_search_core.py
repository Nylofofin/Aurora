from datetime import datetime, timezone
from pathlib import Path
import re

import aurora

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def test_stale_publication_is_rejected_and_recent_is_accepted():
    old = "Published February 4, 2025"
    recent = "Published October 20, 2026"
    assert aurora._has_stale_source_date(old, "7d", now=NOW)
    assert not aurora._has_stale_source_date(recent, "7d", now=NOW)
    stale_html = (FIXTURES / "stale-source.html").read_text()
    metadata = aurora.PageMetadata()
    metadata.feed(stale_html)
    assert metadata.dates[0][1].startswith("2025-")


def test_conflicting_current_claims_remain_relevant_as_separate_evidence():
    query = "Nexa network measured"
    claims = []
    for name in ("recent-source-a.html", "recent-source-b.html"):
        html = (FIXTURES / name).read_text()
        text = " ".join(re.findall(r">([^<>]+)<", html))
        claims.append(text)
    assert "18 units" in claims[0]
    assert "21 units" in claims[1]
    assert aurora._search_relevance(query, "Nexa network measurement update", claims[0]) > 0
    assert aurora._search_relevance(query, "Nexa network measurement update", claims[1]) > 0
    prompt, system = aurora.search_answer_prompts(
        "What did the Nexa network measure?", "Nexa network measured",
        ["Source A, 21/10/2026: " + claims[0], "Source B, 20/10/2026: " + claims[1]], now=NOW,
    )
    assert "18 units" in prompt and "21 units" in prompt
    assert "mencione a divergência" in prompt
    assert "divergências" in system


def test_current_fact_requires_two_independent_dated_publishers():
    one = [{"host": "source-a.example", "published": "21/10/2026"}]
    two = one + [{"host": "source-b.example", "published": "20/10/2026"}]
    stale = [{"host": "source-a.example", "published": "04/02/2025"}]
    assert aurora._independent_recent_source_count([], "7d", NOW) == 0
    assert aurora._independent_recent_source_count(one, "7d", NOW) == 1
    assert aurora._independent_recent_source_count(two, "7d", NOW) == 2
    duplicate_story = [
        {"host": "source-a.example", "published": "21/10/2026", "title": "Nexa network measurement update"},
        {"host": "source-b.example", "published": "20/10/2026", "title": "Nexa network measurement update"},
    ]
    assert aurora._independent_recent_source_count(duplicate_story, "7d", NOW) == 1
    assert aurora._independent_recent_source_count(stale, "7d", NOW) == 0


def test_localized_and_machine_feed_dates_are_parsed():
    for value in ("qua., 21 out. 2026 13:06:00 GMT", "Tue, 21 Oct 2026 13:06:00 GMT", "2026-10-21T13:06:00Z", "21/10/2026 13:06"):
        assert aurora._parse_publication_date(value).strftime("%d/%m/%Y") == "21/10/2026"


def test_question_intent_and_time_window_are_topic_independent():
    assert aurora.factual_web_intent("Qual é a concentração atual da amostra?")
    assert aurora.current_search_window("Qual é a concentração atual da amostra?") == "30d"
    assert not aurora.factual_web_intent("Abra a calculadora")
    assert aurora.current_search_window("Qual era a concentração em 2024?") == ""
    assert aurora.current_web_query("Nexa network current measurement", "30d").endswith(str(NOW.year))


def test_news_format_terms_are_removed_only_when_a_subject_remains():
    query = "quais as notícias de tecnologia hoje"
    assert aurora._fresh_query_terms(query) == {"tecnologia"}
    assert aurora._search_relevance(query, "Novidades sobre tecnologia e ciência", "") > 0
    assert aurora._search_relevance(query, "Resultado sobre política e futebol", "") == 0.0
    assert aurora._fresh_query_terms("notícias de hoje") == {"noticias"}
    assert aurora._search_relevance("notícias de hoje", "Notícias do dia", "") == 1.0


def test_current_dollar_question_does_not_require_question_words_for_relevance():
    query = "Quanto está o dólar agora"
    assert aurora._fresh_query_terms(query) == {"dolar"}
    assert aurora._search_relevance(query, "Dólar hoje fica estável", "Cotação da moeda americana") == 1.0
    assert aurora._search_relevance(query, "Quanto - Dicio", "Significado da palavra quanto") == 0.0


def test_numeric_answers_must_use_numbers_literal_in_evidence():
    evidence = ["Dólar fica estável hoje; petróleo a US$ 112."]
    assert aurora._ground_numeric_answer(
        "O dólar está em torno de 52,50 reais.", evidence,
        ["Folha de S.Paulo (22/10/2026)", "Estadão (22/10/2026)"],
    ) == "Não consegui confirmar os valores numéricos com os trechos consultados. Fontes: Folha de S.Paulo (22/10/2026), Estadão (22/10/2026)."
    assert aurora._ground_numeric_answer("O petróleo está a US$ 112.", evidence, []) == "O petróleo está a US$ 112."
    prompt, system = aurora.search_answer_prompts("Qual o valor?", "valor atual", evidence, now=NOW)
    assert "mesma sequência numérica aparecer literalmente" in prompt
    assert "a sequência numérica apareça literalmente" in system


def test_news_dates_and_headline_numbers_do_not_trigger_numeric_guard():
    answer = "Tecnopuc Experience 2026 reúne empresas de saúde e tecnologia, segundo o Jornal do Comércio em 22/10/2026."
    evidence = ["Título: Tecnopuc Experience 2026 reúne empresas de saúde e tecnologia | Data: 22/10/2026"]
    assert not aurora.numeric_answer_intent("quais as notícias de tecnologia hoje")
    assert aurora.ground_search_answer("quais as notícias de tecnologia hoje", answer, evidence, ["Jornal do Comércio"]) == answer
    assert aurora.ground_search_answer("notícias de hoje", "Custa 52,50 reais.", evidence, ["fonte"]) == "Custa 52,50 reais."


def test_numeric_guard_failure_message_matches_news_intent():
    result = aurora.ground_search_answer(
        "quantas notícias recentes sobre tecnologia?", "Foram 12 notícias.",
        ["A fonte menciona tecnologia."], ["Jornal"],
    )
    assert result.startswith("Não consegui confirmar notícias recentes sobre isso.")
    assert "valor" not in result.lower()


def test_incomplete_stream_tail_is_not_spoken():
    full = "As notícias incluem duas atualizações completas. A terceira começa em 21"
    assert aurora.complete_spoken_response(full) == "As notícias incluem duas atualizações completas."
    assert aurora.complete_spoken_response("A notícia termina corretamente.") == "A notícia termina corretamente."
    assert aurora.complete_spoken_response("fragmento sem pontuação") == ""


def test_numeric_guard_decimal_currency_percent_and_spelled_number_edges():
    fallback = "Não consegui confirmar os valores numéricos com os trechos consultados. Fontes: fonte."
    assert aurora._ground_numeric_answer("O valor é 5.40.", ["O valor é 5,40."], ["fonte"]) == "O valor é 5.40."
    assert aurora._ground_numeric_answer("O valor é 5,041.", ["O valor é 5.041."], ["fonte"]) == "O valor é 5,041."
    assert aurora._ground_numeric_answer("Custa R$ 5,40.", ["O valor é 5.40."], ["fonte"]) == "Custa R$ 5,40."
    assert aurora._ground_numeric_answer("A taxa é 0.5%.", ["A taxa é 0,5%."], ["fonte"]) == "A taxa é 0.5%."
    assert aurora._ground_numeric_answer("A taxa é 0,5%.", ["A taxa é 0,5."], ["fonte"]) == fallback
    assert aurora._ground_numeric_answer("A taxa é 0,5.", ["A taxa é 0,5%."], ["fonte"]) == fallback
    assert aurora._ground_numeric_answer("Custa cinquenta e dois reais.", ["O dólar está estável."], ["fonte"]) == fallback
    assert aurora._ground_numeric_answer("Custa cinquenta e dois reais.", ["O preço é cinquenta e dois reais."], ["fonte"]) == "Custa cinquenta e dois reais."
    assert aurora._ground_numeric_answer("É um ponto importante.", ["É uma observação relevante."], ["fonte"]) == "É um ponto importante."


def test_structured_fx_answer_must_say_api_values_and_accept_equivalent_decimal_format():
    from datetime import date
    from decimal import Decimal
    quote = aurora.aurora_fx.FXQuote(
        "AwesomeAPI", "USD", "BRL", Decimal("5.045"), date(2026, 10, 22),
        "12:30:00 UTC-3", Decimal("5.04"), Decimal("5.05"),
    )
    safe = aurora._verified_fx_answer("O dólar está em 5.03 e 5.05.", quote)
    assert safe.startswith("Não confirmei o valor numérico.")
    incomplete = "O dólar está em 5,04 para compra e R$ 5,05 para venda."
    assert aurora._verified_fx_answer(incomplete, quote) == incomplete
    spoken = "Compra R$ 5,04 e venda R$ 5,05, conforme a cotação."
    assert aurora._verified_fx_answer(spoken, quote) == spoken


def test_structured_conversion_requires_both_rate_and_converted_value():
    from datetime import date, datetime
    from decimal import Decimal
    quote = aurora.aurora_fx.FXQuote(
        "Frankfurter", "USD", "BRL", Decimal("5.6528"), date(2026, 10, 22),
        amount=Decimal("100"), converted=Decimal("565.28"),
        retrieved_at=datetime(2026, 10, 22, 12, 50, 31, tzinfo=aurora.aurora_fx.LOCAL_TZ),
    )
    answer = aurora.aurora_fx.format_quote(quote)
    assert aurora._verified_fx_answer(answer, quote) == answer
    assert aurora._verified_fx_answer("100 USD equivalem a R$ 565,28.", quote).startswith("Não confirmei o valor numérico.")


def test_old_awesome_quote_warning_preserves_numeric_verification():
    from datetime import date
    from decimal import Decimal
    quote = aurora.aurora_fx.FXQuote(
        "AwesomeAPI", "USD", "BRL", Decimal("5.045"), date(2026, 10, 22),
        "12:00:00 UTC-3", Decimal("5.04"), Decimal("5.05"), stale=True,
    )
    answer = aurora.aurora_fx.format_quote(quote)
    assert "não a apresento como valor de agora" in answer
    assert aurora._verified_fx_answer(answer, quote) == answer


def _google_news_test_rows(count=3):
    from datetime import date
    published = date.today().strftime("%d/%m/%Y")
    return "Google Notícias:\n" + "\n".join(
        f"Nexa network measurement update {index} [Publisher {index} · {published}] :: Nexa network measurement reported today — https://news.google.com/articles/story-{index}"
        for index in range(1, count + 1)
    )


def _force_provider_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("provider unavailable")
    monkeypatch.setattr(aurora.PUBLIC_OPENER, "open", fail)
    monkeypatch.setattr(aurora, "public_http_url", lambda url: url)
    monkeypatch.setattr(aurora, "search_google_news", lambda query, window: _google_news_test_rows())


def test_google_news_fallback_uses_common_page_pipeline_and_caps_reads_at_two(monkeypatch):
    _force_provider_failure(monkeypatch)
    calls = []
    published = datetime.now().astimezone().strftime("%d/%m/%Y")
    def read(url, query, timeout=2.5):
        calls.append((url, timeout))
        return ("Nexa network measurement reported today in the page.", published)
    monkeypatch.setattr(aurora, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached("Nexa network measurement today", "7d", False)
    assert len(calls) == 2
    assert "Google Notícias" in output
    assert "Trecho da página aberta agora" in output
    assert "Nexa network measurement" in output


def test_google_news_feed_date_is_not_page_date_and_failed_redirect_is_discarded(monkeypatch):
    _force_provider_failure(monkeypatch)
    calls = []
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    def read(url, query, timeout=2.5):
        calls.append(url)
        if url.endswith("story-1"):
            return ("Nexa network measurement reported today in the page.", today)
        if url.endswith("story-2"):
            return ("Nexa network measurement reported today in the page.", "")
        raise ValueError("redirect destination failed public URL validation")
    monkeypatch.setattr(aurora, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached("Nexa network measurement today", "7d", False)
    assert len(calls) == 2
    assert "Publisher 2" not in output
    assert "Google Notícias, publicações" not in output
    assert "não bastam para confirmar" in output


def test_subject_specific_search_adapters_are_absent():
    source = Path(aurora.__file__).read_text().lower()
    for forbidden in ("def robux_price_answer", "def currency_rate_answer", "def minecraft_java_latest_release", "_authoritative_host"):
        assert forbidden not in source


def test_short_cache_avoids_duplicate_search(monkeypatch):
    aurora._SEARCH_CACHE.clear()
    calls = []
    def fake(query, freshness=None, news_only=None):
        calls.append(query)
        return "cached evidence"
    monkeypatch.setattr(aurora, "_search_public_web_uncached", fake)
    assert aurora.search_public_web("Nexa current value", "30d") == "cached evidence"
    assert aurora.search_public_web("Nexa current value", "30d") == "cached evidence"
    assert calls == ["Nexa current value"]
    aurora._SEARCH_CACHE.clear()
