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
