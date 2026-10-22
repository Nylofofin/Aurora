from datetime import datetime, timezone
from pathlib import Path
import re

import aurora
import aurora_core.web.pipeline as search_pipeline
import aurora_core.web.security as web_security
import aurora_core.web.providers as search_providers

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


def test_modified_timestamp_does_not_override_known_old_publication_date(monkeypatch):
    import aurora_core.web.fetch as search_fetch
    from email.message import Message

    body = (FIXTURES / "edited-old-source.html").read_bytes()
    headers = Message()
    headers["Content-Type"] = "text/html; charset=utf-8"

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return "https://example.org/nexa-network-status"
        def read(self, _limit): return body

    monkeypatch.setattr(search_fetch, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_fetch.PUBLIC_OPENER, "open", lambda *_args, **_kwargs: Response())
    Response.headers = headers
    excerpt, published = search_fetch._search_page_excerpt(
        "https://example.org/nexa-network-status", "Nexa network status"
    )

    assert "Nexa network status" in excerpt
    assert published == "12/03/2024"


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


def test_publication_windows_use_elapsed_time_not_calendar_days():
    assert aurora._publication_within_window("2026-10-21T12:01:00Z", "1d", NOW)
    assert not aurora._publication_within_window("2026-10-21T11:59:00Z", "1d", NOW)
    assert aurora._publication_within_window("2026-10-15T12:01:00Z", "7d", NOW)
    assert not aurora._publication_within_window("2026-10-15T11:59:00Z", "7d", NOW)
    assert not aurora._publication_within_window("2026-10-22T12:01:00Z", "1d", NOW)


def test_localized_and_machine_feed_dates_are_parsed():
    for value in ("qua., 21 out. 2026 13:06:00 GMT", "Tue, 21 Oct 2026 13:06:00 GMT", "2026-10-21T13:06:00Z", "21/10/2026 13:06"):
        assert aurora._parse_publication_date(value).strftime("%d/%m/%Y") == "21/10/2026"


def test_google_news_rss_hour_survives_pipeline_freshness_filter(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import aurora_core.web.freshness as freshness

    fixed_now = datetime(2026, 10, 22, 15, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    monkeypatch.setattr(search_providers, "public_http_url", lambda url: url)
    monkeypatch.setattr(
        search_providers,
        "_publication_within_window",
        lambda value, window: freshness._publication_within_window(value, window, now=fixed_now),
    )
    rss = "Google Notícias:\nNexa network measurement update [Jornal · 21/10/2026 16:00] :: Nexa network measurement data — https://news.google.com/articles/story"

    items = search_providers._google_news_pipeline_items(
        rss, "Nexa network measurement", "1d"
    )

    assert len(items) == 1
    assert items[0]["published"] == "21/10/2026 16:00"


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
    assert "Só informe um valor numérico se a mesma sequência numérica aparecer literalmente" in system


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


def test_news_results_must_match_subject_or_be_a_general_roundup():
    assert aurora._news_result_relevance(
        "quais as notícias de tecnologia hoje", "Novidades sobre tecnologia", ""
    ) > 0
    assert aurora._news_result_relevance(
        "quais as notícias de tecnologia hoje", "Notícias sobre edital", "concursos"
    ) == 0.0
    assert aurora._news_result_relevance(
        "notícias de hoje", "Principais notícias do mundo na manhã de hoje", ""
    ) > 0
    assert aurora._news_result_relevance(
        "notícias de hoje", "Notícias sobre edital de 22 de outubro", ""
    ) == 0.0
    assert aurora.news_unconfirmed_message().startswith("Não consegui confirmar notícias")


def test_news_prompt_never_turns_headline_into_price_request():
    prompt, system = aurora.search_answer_prompts(
        "notícias de hoje", "notícias de hoje", ["Notícias sobre edital; data 22/10/2026"]
    )
    assert "números e datas de manchetes são metadados" in prompt
    assert "Não consegui confirmar o valor" not in prompt + system
    assert "manchete isolada em resposta sobre preço" in system


def test_missing_page_date_uses_feed_timestamp_only_for_current_news(monkeypatch):
    monkeypatch.setattr(search_providers, "_search_page_excerpt", lambda *_args, **_kwargs: ("", ""))
    rss = "Google Notícias\nManchete [Jornal · 22/10/2026 10:30] :: resumo do feed — https://example.org/noticia"
    current = aurora._enrich_news_results(rss, "notícias de tecnologia hoje", "1d")
    assert "[Feed RSS: Jornal · 22/10/2026 10:30]" in current
    prompt, system = aurora.search_answer_prompts("notícias de tecnologia hoje", "tecnologia", [current])
    assert "segundo o feed, de [hora]" in prompt
    assert "segundo o feed, de [hora]" in system
    non_current = aurora._enrich_news_results(rss, "notícias de tecnologia", "7d")
    assert "Feed RSS:" not in non_current


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


def test_large_fx_values_use_thousands_separator_and_guard_accepts_both_forms():
    from datetime import date
    from decimal import Decimal
    quote = aurora.aurora_fx.FXQuote(
        "AwesomeAPI", "BTC", "BRL", Decimal("411528"), date(2026, 10, 22),
        "12:30:00 UTC-3", Decimal("411528"), Decimal("411529"),
    )
    formatted = aurora.aurora_fx.format_quote(quote)
    assert "411.528 de compra" in formatted
    assert "411.529 de venda" in formatted
    assert aurora._verified_fx_answer(formatted, quote) == formatted
    ungrouped = "Bitcoin compra 411528 reais e venda 411529 reais."
    assert aurora._verified_fx_answer(ungrouped, quote) == ungrouped


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
    monkeypatch.setattr(web_security.PUBLIC_OPENER, "open", fail)
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda query, window: _google_news_test_rows())


def test_google_news_fallback_uses_common_page_pipeline_and_caps_reads_at_two(monkeypatch):
    _force_provider_failure(monkeypatch)
    calls = []
    published = datetime.now().astimezone().strftime("%d/%m/%Y")
    def read(url, query, timeout=2.5):
        calls.append((url, timeout))
        return ("Nexa network measurement reported today in the page.", published)
    monkeypatch.setattr(search_providers, "_search_page_excerpt", read)
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached("Nexa network measurement today", "7d", False)
    assert len(calls) == 2
    assert "Google Notícias" in output
    assert "Trecho da página aberta agora" in output
    assert "Nexa network measurement" in output


def test_current_search_skips_duplicate_publisher_to_read_an_independent_source(monkeypatch):
    _force_provider_failure(monkeypatch)
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    rss = "Google Notícias:\n" + "\n".join((
        f"Nexa network measurement results [Daily News · {today}] :: Nexa network measurement reported today — https://news.google.com/articles/story-1",
        f"Nexa network measurement details [Daily News · {today}] :: Nexa network measurement reported today — https://news.google.com/articles/story-2",
        f"Sensor lab measures Nexa network [Independent Journal · {today}] :: Nexa network measurement reported today — https://news.google.com/articles/story-3",
    ))
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda *_args: rss)
    calls = []

    def read(url, query, timeout=2.5):
        calls.append(url)
        return ("Nexa network measurement reported today in the article.", today)

    monkeypatch.setattr(search_providers, "_search_page_excerpt", read)
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached(
        "Nexa network measurement today", "7d", False
    )

    assert calls == [
        "https://news.google.com/articles/story-1",
        "https://news.google.com/articles/story-3",
    ]
    assert "Independent Journal" in output
    assert "As fontes encontradas não bastam" not in output


def test_google_news_feed_candidate_with_failed_redirect_is_discarded(monkeypatch):
    _force_provider_failure(monkeypatch)
    calls = []
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    def read(url, query, timeout=2.5):
        calls.append(url)
        if url.endswith("story-1"):
            return ("Nexa network measurement reported today in the page.", today)
        if url.endswith("story-2"):
            raise ValueError("redirect destination failed public URL validation")
        raise ValueError("redirect destination failed public URL validation")
    monkeypatch.setattr(search_providers, "_search_page_excerpt", read)
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached("Nexa network measurement today", "7d", False)
    assert len(calls) == 2
    assert "Publisher 2" not in output
    assert "Google Notícias, publicações" not in output
    assert "não bastam para confirmar" in output


def test_google_news_feed_date_is_accepted_when_read_page_has_no_date(monkeypatch):
    _force_provider_failure(monkeypatch)
    calls = []

    def read(url, query, timeout=2.5):
        calls.append(url)
        return ("Nexa network measurement reported today in the page.", "")

    monkeypatch.setattr(search_providers, "_search_page_excerpt", read)
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached(
        "Nexa network measurement today", "7d", False
    )

    assert len(calls) == 2
    assert "Feed RSS: Publisher 1 ·" in output
    assert "Feed RSS: Publisher 2 ·" in output
    assert "Trecho da página aberta agora" in output


def test_unread_current_pages_are_not_reported_as_stale(monkeypatch):
    _force_provider_failure(monkeypatch)

    def fail_read(*_args, **_kwargs):
        raise ValueError("page redirect rejected")

    monkeypatch.setattr(search_providers, "_search_page_excerpt", fail_read)
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", fail_read)
    output = aurora._search_public_web_uncached(
        "Nexa network measurement today", "7d", False
    )

    assert "Não consegui ler páginas" in output
    assert "páginas abertas estavam fora" not in output


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
    monkeypatch.setattr(search_pipeline, "_search_public_web_uncached", fake)
    assert aurora.search_public_web("Nexa current value", "30d") == "cached evidence"
    assert aurora.search_public_web("Nexa current value", "30d") == "cached evidence"
    assert calls == ["Nexa current value"]
    aurora._SEARCH_CACHE.clear()


def test_search_retries_with_subject_terms_without_question_formatting():
    variants = aurora._search_query_variants(
        "Me mostra um tutorial de como jogar Starfield no Linux", ""
    )
    assert variants[0][0] == "Me mostra um tutorial de como jogar Starfield no Linux"
    assert variants[1][0] == "Starfield Linux"
    assert aurora._search_relevance(variants[1][1], "Como jogar Starfield no Linux", "") > 0


def test_final_search_filter_uses_subject_terms_not_instruction_words():
    query = "Me mostra um tutorial de como jogar Starfield no Linux"
    assert aurora._search_relevance(query, "Starfield Linux beginner guide", "") == 0.0
    assert aurora._result_query_relevance(query, "Starfield Linux beginner guide", "") == 1.0


def test_search_failure_keeps_the_pipeline_reason_instead_of_replacing_it():
    output = "Os provedores responderam, mas nenhum resultado passou pelos filtros de endereço público, atualidade e relação com a pergunta.\n"
    assert aurora.search_failure_summary(output, "Como jogar Starfield?") == output.splitlines()[0]
    assert "não conseguiu consultar" in aurora.search_failure_summary(
        "A busca não conseguiu consultar os provedores disponíveis (DuckDuckGo Lite: URLError; Bing RSS: URLError).",
        "Qual é a versão atual?",
    )
