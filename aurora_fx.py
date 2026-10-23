"""Structured FX reference lookup using local ISO 4217 labels and public APIs."""
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import gettext
import json
import re
import queue
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo
from aurora_core.web.security import PUBLIC_OPENER, public_http_url


LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
DEFAULT_QUOTE = "BRL"
API_TIMEOUT = 2.0
QUOTE_CUES = re.compile(r"\b(cotacao|taxa|quanto\s+(?:vale|esta|ta)|converter|conversao)\b")
CURRENT_CUES = re.compile(r"\b(agora|hoje|atual|atualmente|neste\s+momento|tempo\s+real|ao\s+vivo)\b")
DATE_PATTERNS = (re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"), re.compile(r"\b(\d{2})/(\d{2})/(20\d{2})\b"))
FUNCTION_WORDS = {"do", "de", "da", "em", "para", "por", "no", "na", "o", "a", "e", "um", "ao", "as", "dos", "das", "pra", "the", "of", "and", "to"}
ASSET_CATALOG = (("BTC", "Bitcoin", "Bitcoin"),)
AMOUNT_RE = re.compile(r"\b(\d{1,12}(?:[.,]\d{1,8})?)\b")
_CATALOG_CACHE = None


@dataclass(frozen=True)
class FXIntent:
    base: str
    quote: str
    amount: Decimal | None = None
    requested_date: date | None = None
    conversion: bool = False
    current: bool = True
    reference_supported: bool = True


@dataclass(frozen=True)
class FXQuote:
    source: str
    base: str
    quote: str
    rate: Decimal
    quote_date: date
    quote_time: str = ""
    bid: Decimal | None = None
    ask: Decimal | None = None
    amount: Decimal | None = None
    converted: Decimal | None = None
    retrieved_at: datetime | None = None
    api_timings: tuple[tuple[str, float], ...] = ()
    stale: bool = False


@dataclass(frozen=True)
class FXLookup:
    quote: FXQuote | None = None
    fallback_output: str | None = None
    api_timings: tuple[tuple[str, float], ...] = ()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", text)
    singular = []
    for word in words:
        if len(word) > 4 and word.endswith("ais"):
            word = word[:-3] + "al"
        elif len(word) > 4 and word.endswith("oes"):
            word = word[:-3] + "ao"
        elif len(word) > 4 and word.endswith("es"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s"):
            word = word[:-1]
        singular.append(word)
    return " ".join(singular)


def _system_currency_rows():
    paths = (Path("/usr/share/iso-codes/json/iso_4217.json"), Path("/usr/share/iso-codes/iso_4217.json"))
    data = None
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError):
            continue
    if not data:
        return []
    translations = gettext.translation("iso_4217", localedir="/usr/share/locale", languages=["pt_BR", "pt"], fallback=True)
    rows = []
    for item in data.get("4217", []):
        code = str(item.get("alpha_3", "")).upper()
        name = str(item.get("name", "")).strip()
        if code and len(code) == 3 and name:
            rows.append((code, name, translations.gettext(name)))
    return rows


def currency_catalog():
    """Return ISO codes and system-localized display names; cache static data."""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        _CATALOG_CACHE = _system_currency_rows()
    return tuple(_CATALOG_CACHE)


def _currency_mentions(text: str, rows):
    normalized = normalize_text(text)
    token_matches = list(re.finditer(r"[a-z0-9]+", normalized))
    mentions = []
    for code, _, _ in rows:
        for match in re.finditer(r"(?<![a-z0-9])" + re.escape(code.lower()) + r"(?![a-z0-9])", normalized):
            mentions.append((match.start(), match.end(), code, 3))
    aliases = []
    for code, english, localized in rows:
        for name in {english, localized}:
            name_tokens = normalize_text(name).split()
            if name_tokens and len(name_tokens) <= 4:
                aliases.append((code, name_tokens))
    # Resolve complete, localized names before matching a shared head word.
    for code, name_tokens in aliases:
        phrase = " ".join(name_tokens)
        if len(name_tokens) > 1:
            for match in re.finditer(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", normalized):
                mentions.append((match.start(), match.end(), code, 2))
    occupied = [(start, end) for start, end, _, priority in mentions if priority >= 2]
    for match in token_matches:
        token = match.group()
        if token in FUNCTION_WORDS:
            continue
        candidates = {code for code, name_tokens in aliases if name_tokens and token in {name_tokens[0], name_tokens[-1]}}
        if not candidates:
            continue
        start, end = match.span()
        if any(start < right and end > left for left, right in occupied):
            continue
        # Names that share a generic head word are disambiguated by the most
        # concise official label in the active locale, without code-specific rules.
        lengths = {}
        for code, english, localized in rows:
            if code in candidates:
                lengths[code] = min(len(normalize_text(english)), len(normalize_text(localized)))
        shortest = min(lengths.values())
        winners = {code for code, length in lengths.items() if length == shortest}
        if len(winners) == 1:
            mentions.append((start, end, next(iter(winners)), 1))
    mentions.sort(key=lambda item: (item[0], -item[3], -(item[1] - item[0])))
    selected = []
    for start, end, code, priority in mentions:
        if any(old_code == code and start < old_end and end > old_start for old_start, old_end, old_code, _ in selected):
            continue
        if any(priority < old_priority and start < old_end and end > old_start for old_start, old_end, _, old_priority in selected):
            continue
        selected.append((start, end, code, priority))
    return [(start, end, code) for start, end, code, _ in selected]


def _requested_date(text: str, today=None):
    today = today or datetime.now(LOCAL_TZ).date()
    if re.search(r"\banteontem\b", text):
        return today - timedelta(days=2)
    if re.search(r"\bontem\b", text):
        return today - timedelta(days=1)
    for index, pattern in enumerate(DATE_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        parts = [int(value) for value in match.groups()]
        try:
            return date(*parts) if index == 0 else date(parts[2], parts[1], parts[0])
        except ValueError:
            return None
    return None


def detect_fx_intent(prompt: str, catalog=None, today=None):
    """Recognize a quote or conversion request using ISO labels/codes."""
    text = normalize_text(prompt)
    if not QUOTE_CUES.search(text):
        return None
    rows = tuple(catalog if catalog is not None else currency_catalog())
    fiat_codes = {row[0] for row in rows}
    detection_rows = rows + ASSET_CATALOG if catalog is None else rows
    occurrences = _currency_mentions(text, detection_rows)
    if not occurrences:
        return None
    distinct = []
    for _, _, code in occurrences:
        if code not in distinct:
            distinct.append(code)
    if len(distinct) > 2:
        return None
    base = distinct[0]
    quote = distinct[1] if len(distinct) == 2 else DEFAULT_QUOTE
    if base == quote:
        return None
    amount_match = AMOUNT_RE.search(text) if re.search(r"\b(converter|conversao)\b", text) else None
    amount = None
    if amount_match:
        try:
            amount = Decimal(amount_match.group(1).replace(",", "."))
        except InvalidOperation:
            return None
        if amount <= 0:
            return None
    requested_date = _requested_date(text, today)
    conversion = amount is not None or bool(re.search(r"\b(converter|conversao)\b", text))
    current = requested_date is None and not conversion
    reference_supported = base in fiat_codes and quote in fiat_codes
    return FXIntent(base, quote, amount, requested_date, conversion, current, reference_supported)


def _decimal(value):
    if isinstance(value, bool):
        raise ValueError("numeric field is boolean")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("numeric field is invalid") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError("rate must be finite and positive")
    return result


def _read_json(url: str, timeout=API_TIMEOUT, headers=None):
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Aurora-FX/1.0", **(headers or {})})
    started = time.monotonic()
    result_queue = queue.Queue(maxsize=1)

    def read_response():
        try:
            public_http_url(request.full_url)
            with PUBLIC_OPENER.open(request, timeout=timeout) as response:
                status = response.status
                public_http_url(response.geturl())
                content_type = response.headers.get("Content-Type", "")
                if not 200 <= status < 300:
                    raise ValueError(f"HTTP {status}")
                if content_type and "application/json" not in content_type.lower():
                    raise ValueError("API did not return JSON")
                result_queue.put((status, response.read(128_000), None))
        except Exception as exc:
            result_queue.put((None, None, exc))

    worker = threading.Thread(target=read_response, name="aurora-fx-http", daemon=True)
    worker.start()
    worker.join(max(0.01, float(timeout)))
    if worker.is_alive():
        raise TimeoutError("API exceeded total timeout")
    status, body, error = result_queue.get_nowait()
    if error:
        raise error
    if not 200 <= status < 300:
        raise ValueError(f"HTTP {status}")
    payload = json.loads(body.decode("utf-8"))
    if time.monotonic() - started > timeout:
        raise TimeoutError("API exceeded total timeout")
    if not isinstance(payload, (dict, list)):
        raise ValueError("invalid JSON response type")
    return payload


def fetch_awesome(intent: FXIntent, timeout=API_TIMEOUT, now=None):
    if intent.requested_date:
        raise ValueError("the last endpoint does not satisfy a dated lookup")
    pair = f"{intent.base}-{intent.quote}"
    payload = _read_json(f"https://economia.awesomeapi.com.br/json/last/{pair}", timeout=timeout)
    row = payload.get(intent.base + intent.quote) if isinstance(payload, dict) else None
    if not isinstance(row, dict) or row.get("code") != intent.base or row.get("codein") != intent.quote:
        raise ValueError("missing pair fields")
    bid = _decimal(row.get("bid"))
    ask = _decimal(row.get("ask"))
    stamp = row.get("create_date")
    try:
        quote_dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=-3)))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid quote time") from exc
    retrieved = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    converted = ((intent.amount * ((bid + ask) / 2)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if intent.amount else None)
    stale = retrieved - quote_dt.astimezone(LOCAL_TZ) > timedelta(minutes=30)
    return FXQuote("AwesomeAPI", intent.base, intent.quote, (bid + ask) / 2, quote_dt.date(), quote_dt.strftime("%H:%M:%S UTC-3"), bid, ask, intent.amount, converted, retrieved, stale=stale)


def fetch_frankfurter(intent: FXIntent, timeout=API_TIMEOUT, now=None):
    url = f"https://api.frankfurter.dev/v2/rate/{intent.base}/{intent.quote}"
    if intent.requested_date:
        url += "?date=" + intent.requested_date.isoformat()
    payload = _read_json(url, timeout=timeout)
    if not isinstance(payload, dict) or payload.get("base") != intent.base or payload.get("quote") != intent.quote:
        raise ValueError("missing pair fields")
    rate = _decimal(payload.get("rate"))
    try:
        quote_date = date.fromisoformat(payload.get("date", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid rate date") from exc
    if intent.requested_date and quote_date != intent.requested_date:
        raise ValueError("API returned a different date")
    retrieved = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    converted = (intent.amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if intent.amount else None
    return FXQuote("Frankfurter", intent.base, intent.quote, rate, quote_date, "", amount=intent.amount, converted=converted, retrieved_at=retrieved)


def _format_pt_decimal(value):
    text = format(Decimal(value).normalize(), "f")
    sign = "-" if text.startswith("-") else ""
    if sign:
        text = text[1:]
    integer, separator, fraction = text.partition(".")
    grouped = f"{int(integer):,}".replace(",", ".")
    return sign + grouped + (("," + fraction) if separator else "")


def format_quote(quote: FXQuote):
    rate_text = _format_pt_decimal(quote.rate)
    names = {code: localized for code, _, localized in currency_catalog() + ASSET_CATALOG}
    base_name = names.get(quote.base) or quote.base
    quote_name = names.get(quote.quote) or quote.quote
    if quote.source == "AwesomeAPI" and quote.bid is not None and quote.ask is not None:
        bid_text, ask_text = _format_pt_decimal(quote.bid), _format_pt_decimal(quote.ask)
        text = f"{base_name} ({quote.base}/{quote.quote}): {quote_name} {bid_text} de compra e {quote_name} {ask_text} de venda, segundo a AwesomeAPI, cotação de {quote.quote_time} em {quote.quote_date:%d/%m/%Y}."
        if quote.stale:
            text += " Essa cotação pode estar desatualizada ou o mercado pode estar fechado; não a apresento como valor de agora."
    else:
        text = f"{base_name} ({quote.base}/{quote.quote}): {rate_text} {quote_name}, taxa de referência diária da Frankfurter de {quote.quote_date:%d/%m/%Y}."
    if quote.amount is not None and quote.converted is not None:
        amount_text = _format_pt_decimal(quote.amount)
        converted_text = _format_pt_decimal(quote.converted)
        text += f" {amount_text} {quote.base} equivalem a {quote_name} {converted_text}, arredondado a duas casas decimais."
    if quote.retrieved_at:
        text += f" Consultado às {quote.retrieved_at:%H:%M:%S} BRT."
    return text


def get_quote(intent: FXIntent, *, awesome=fetch_awesome, frankfurter=fetch_frankfurter, search_fallback=None, timeout=API_TIMEOUT):
    """Return structured evidence or a web fallback, using the requested order."""
    if not intent.reference_supported:
        sources = (("AwesomeAPI", awesome),) if not intent.requested_date else ()
    elif intent.conversion or intent.requested_date:
        sources = (("Frankfurter", frankfurter),)
    else:
        sources = (("AwesomeAPI", awesome), ("Frankfurter", frankfurter))
    timings = []
    for source_name, source in sources:
        started = time.monotonic()
        try:
            quote = source(intent, timeout=timeout)
            timings.append((quote.source, time.monotonic() - started))
            quote = replace(quote, api_timings=tuple(timings))
            return FXLookup(quote=quote, api_timings=tuple(timings))
        except Exception:
            timings.append((source_name, time.monotonic() - started))
            continue
    if search_fallback:
        return FXLookup(fallback_output=search_fallback(intent), api_timings=tuple(timings))
    return FXLookup(api_timings=tuple(timings))
