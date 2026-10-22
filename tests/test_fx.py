import json
import threading
from datetime import date, datetime
from decimal import Decimal

import pytest

import aurora_fx


CATALOG = (
    ("USD", "US Dollar", "Dólar americano"),
    ("CAD", "Canadian Dollar", "Dólar canadense"),
    ("EUR", "Euro", "Euro"),
    ("BRL", "Brazilian Real", "Real brasileiro"),
)


def test_detects_named_and_code_based_quote_pairs_without_topic_branches():
    assert aurora_fx.detect_fx_intent("Quanto está o dólar agora", CATALOG) == aurora_fx.FXIntent("USD", "BRL")
    assert aurora_fx.detect_fx_intent("Quanto está o euro hoje", CATALOG).base == "EUR"
    conversion = aurora_fx.detect_fx_intent("converter 100 dólares para reais", CATALOG)
    assert (conversion.base, conversion.quote, conversion.amount, conversion.conversion) == ("USD", "BRL", Decimal("100"), True)
    assert aurora_fx.detect_fx_intent("cotação USD para BRL", CATALOG).base == "USD"
    assert aurora_fx.detect_fx_intent("quanto custa um café", CATALOG) is None
    assert aurora_fx.detect_fx_intent("abra a calculadora", CATALOG) is None


def test_relative_date_and_portuguese_prepositions_do_not_become_currency_names():
    today = date(2026, 10, 22)
    intent = aurora_fx.detect_fx_intent("cotação do dólar ontem", today=today)
    assert intent == aurora_fx.FXIntent("USD", "BRL", requested_date=date(2026, 10, 21), current=False)
    two_days_ago = aurora_fx.detect_fx_intent("taxa do euro anteontem", today=today)
    assert two_days_ago.base == "EUR" and two_days_ago.requested_date == date(2026, 10, 20)


@pytest.mark.parametrize(("phrase", "expected"), [
    ("quanto está o dólar do Brasil", ["USD"]),
    ("valor do euro em reais", ["EUR", "BRL"]),
    ("100 reais em dólares", ["BRL", "USD"]),
])
def test_currency_function_words_are_never_detected_as_currency_names(phrase, expected):
    mentions = aurora_fx._currency_mentions(phrase, aurora_fx.currency_catalog())
    assert [code for _, _, code in mentions] == expected


class FakeResponse:
    status = 200
    headers = {}

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body


def test_awesomeapi_validates_fields_and_parses_utc_minus_three(monkeypatch):
    seen = {}
    body = json.dumps({"USDBRL": {
        "code": "USD", "codein": "BRL", "bid": "5.0400", "ask": "5.0410",
        "create_date": "2026-10-22 12:27:52", "timestamp": "1792682872",
    }}).encode()

    def urlopen(request, timeout):
        seen.update(url=request.full_url, timeout=timeout)
        return FakeResponse(body)

    monkeypatch.setattr(aurora_fx.urllib.request, "urlopen", urlopen)
    quote = aurora_fx.fetch_awesome(aurora_fx.FXIntent("USD", "BRL"), timeout=2)
    assert seen == {"url": "https://economia.awesomeapi.com.br/json/last/USD-BRL", "timeout": 2}
    assert quote.bid == Decimal("5.0400") and quote.ask == Decimal("5.0410")
    assert quote.quote_time == "12:27:52 UTC-3"


def test_frankfurter_current_and_requested_date_validate_pair_and_positive_rate(monkeypatch):
    seen = []

    def read(url, timeout):
        seen.append((url, timeout))
        return {"date": "2026-10-21", "base": "USD", "quote": "BRL", "rate": 5.03}

    monkeypatch.setattr(aurora_fx, "_read_json", read)
    quote = aurora_fx.fetch_frankfurter(aurora_fx.FXIntent("USD", "BRL"), timeout=1.4)
    assert quote.rate == Decimal("5.03")
    assert seen[-1] == ("https://api.frankfurter.dev/v2/rate/USD/BRL", 1.4)
    with pytest.raises(ValueError, match="different date"):
        aurora_fx.fetch_frankfurter(aurora_fx.FXIntent("USD", "BRL", requested_date=date(2026, 10, 22)))


@pytest.mark.parametrize("bad_rate", [0, -1, "NaN", "Infinity", None])
def test_frankfurter_rejects_invalid_json_rate_values(monkeypatch, bad_rate):
    monkeypatch.setattr(aurora_fx, "_read_json", lambda *args, **kwargs: {
        "date": "2026-10-22", "base": "USD", "quote": "BRL", "rate": bad_rate,
    })
    with pytest.raises(ValueError):
        aurora_fx.fetch_frankfurter(aurora_fx.FXIntent("USD", "BRL"))


def test_invalid_json_body_is_rejected(monkeypatch):
    monkeypatch.setattr(aurora_fx.urllib.request, "urlopen", lambda *a, **kw: FakeResponse(b"not-json"))
    with pytest.raises(json.JSONDecodeError):
        aurora_fx.fetch_frankfurter(aurora_fx.FXIntent("USD", "BRL"))


def test_http_timeout_is_a_total_deadline(monkeypatch):
    release = threading.Event()

    def slow_open(*args, **kwargs):
        release.wait(0.5)
        return FakeResponse(b"{}")

    monkeypatch.setattr(aurora_fx.urllib.request, "urlopen", slow_open)
    with pytest.raises(TimeoutError, match="total timeout"):
        aurora_fx._read_json("https://example.invalid", timeout=0.03)
    release.set()


def test_awesomeapi_timeout_uses_frankfurter_then_success(monkeypatch):
    calls = []

    def primary(intent, timeout):
        calls.append("awesome")
        raise TimeoutError("slow")

    def secondary(intent, timeout):
        calls.append("frankfurter")
        return aurora_fx.FXQuote("Frankfurter", "USD", "BRL", Decimal("5.03"), date(2026, 10, 22))

    result = aurora_fx.get_quote(aurora_fx.FXIntent("USD", "BRL"), awesome=primary, frankfurter=secondary)
    assert calls == ["awesome", "frankfurter"]
    assert result.quote.source == "Frankfurter"
    assert [name for name, _ in result.quote.api_timings] == ["AwesomeAPI", "Frankfurter"]


def test_conversion_prefers_frankfurter_and_uses_search_only_after_both_fail():
    calls = []

    def fail(name):
        def action(intent, timeout):
            calls.append(name)
            raise OSError("offline")
        return action

    intent = aurora_fx.FXIntent("USD", "BRL", amount=Decimal("100"), conversion=True)
    result = aurora_fx.get_quote(intent, awesome=fail("awesome"), frankfurter=fail("frankfurter"), search_fallback=lambda i: "web evidence")
    assert calls == ["frankfurter"]
    assert result.quote is None and result.fallback_output == "web evidence"
    assert [name for name, _ in result.api_timings] == ["Frankfurter"]


def test_current_quote_falls_back_to_search_when_both_apis_fail():
    calls = []
    def fail(intent, timeout):
        calls.append(timeout)
        raise TimeoutError("offline")

    result = aurora_fx.get_quote(aurora_fx.FXIntent("USD", "BRL"), awesome=fail, frankfurter=fail, search_fallback=lambda _: "search result")
    assert len(calls) == 2
    assert result.quote is None and result.fallback_output == "search result"


def test_awesomeapi_crypto_asset_uses_no_frankfurter_fallback():
    intent = aurora_fx.detect_fx_intent("Quanto está o bitcoin agora")
    assert intent is not None and (intent.base, intent.quote, intent.reference_supported) == ("BTC", "BRL", False)
    calls = []
    quote = aurora_fx.FXQuote("AwesomeAPI", "BTC", "BRL", Decimal("411892.5"), date(2026, 10, 22), "13:07:20 UTC-3", Decimal("411892"), Decimal("411893"))
    result = aurora_fx.get_quote(intent,
        awesome=lambda i, timeout: (calls.append("awesome") or quote),
        frankfurter=lambda i, timeout: (calls.append("frankfurter") or quote),
    )
    assert calls == ["awesome"]
    assert "Bitcoin (BTC/BRL)" in aurora_fx.format_quote(result.quote)


def test_awesome_quote_older_than_thirty_minutes_is_labeled_stale(monkeypatch):
    now = datetime(2026, 10, 22, 13, 0, 0, tzinfo=aurora_fx.LOCAL_TZ)
    payload = json.dumps({"USDBRL": {
        "code": "USD", "codein": "BRL", "bid": "5.04", "ask": "5.05",
        "create_date": "2026-10-22 12:29:59",
    }}).encode()
    monkeypatch.setattr(aurora_fx.urllib.request, "urlopen", lambda *a, **k: FakeResponse(payload))
    quote = aurora_fx.fetch_awesome(aurora_fx.FXIntent("USD", "BRL"), now=now)
    assert quote.stale is True
    answer = aurora_fx.format_quote(quote)
    assert "cotação de 12:29:59 UTC-3" in answer
    assert "pode estar desatualizada" in answer
    assert "não a apresento como valor de agora" in answer


