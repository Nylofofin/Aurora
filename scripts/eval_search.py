#!/usr/bin/env python3
"""Trace Aurora's existing ask/search/answer path without opening UI or audio."""
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin, urlparse

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, Signal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import aurora
import aurora_core.service as aurora_service
import aurora_core.web.pipeline as web_pipeline
import aurora_core.web.requests as web_requests
import aurora_core.web.security as web_security
import aurora_core.web.fetch as web_fetch
import aurora_core.web.providers as web_providers
import aurora_core.web.intent as web_intent
import aurora_core.web.freshness as web_freshness

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "tests" / "eval" / "questions.txt"
CONTEXT_PAIR_START = 427
CONTEXT_PAIR_END = 466


class Trace:
    def __init__(self):
        self.lock = threading.Lock()
        self.search_calls = []
        self.network_requests = []
        self.raw_result_text = ""
        self.pages_read = []
        self.current_query = ""
        self.fx_api_json = []
        self.fx_guard = None
        self.fx_quote = None
        self.fx_api_timings = ()
        self.errors = []
        self.filter_counts = {"relevancia": 0, "data_fonte": 0, "data_pagina_ausente": 0, "url": 0, "redirecionamento": 0}

    def append(self, name, value):
        with self.lock:
            getattr(self, name).append(value)


class OrbStub:
    def isVisible(self):
        return False

    def set_mode(self, _mode):
        pass

    def reveal(self, _mode):
        pass

    def dismiss(self):
        pass

    def frameGeometry(self):
        return None


class ResearchCardStub:
    """Capture the card API without creating any GUI widget during eval."""

    def __init__(self):
        self.generation = None
        self.events = []

    def begin(self, generation, *_args, **_kwargs):
        self.generation = generation

    def update_progress(self, generation, event):
        if generation == self.generation:
            self.events.append(event)

    def set_sources(self, generation, items):
        if generation == self.generation:
            self.events.append({"stage": "sources", "items": items})

    def finish(self, generation, summary):
        if generation == self.generation:
            self.events.append({"stage": "finished", "summary": summary})
            self.generation = None

    def hide(self):
        self.generation = None


class SpeakerStub:
    def __init__(self):
        self.q = queue.Queue()
        self.active = False
        self.playing = False
        self.parts = []

    def say(self, text):
        if text:
            self.parts.append(str(text))


class EvalService(QObject):
    """Small QObject facade; the routing method itself is AuroraService.ask."""

    completed = Signal()
    ask = aurora.AuroraService.ask

    def __init__(self, cfg):
        super().__init__()
        self.app = QCoreApplication.instance()
        self.cfg = cfg
        self.hw = aurora.hardware_profile()
        self.pending = None
        self.inf = None
        self.response_summary = ""
        self.response_finished = False
        self.activity_generation = 0
        self.request_generation = 0
        self.last_wake = 0.0
        self.background_requests = []
        self.context_history = []
        self.inferences = []
        self.current_prompt = ""
        self.active_search_context = ""
        self.response_language = "Português brasileiro"
        self.orb = OrbStub()
        self.research_card = ResearchCardStub()
        self.voice = SimpleNamespace(
            speaking=False,
            request_active=threading.Event(),
            interrupt_active=threading.Event(),
        )
        self.voice.request_active.set()
        self.speaker = SpeakerStub()
        self.trace = None
        self.fx_api_timings = ()
        self.local_action = ""
        self.done = False

    def start_background_request(self, request):
        self.background_requests.append(request)
        request.start()

    def _mobile_audio_owned(self):
        # No mobile Companion is connected in this headless evaluation.
        return False

    def research_progress(self, event, generation):
        aurora.AuroraService.research_progress(self, event, generation)

    def queue_sentence(self, _text, _generation):
        # Evaluation records the completed spoken answer, not streamed audio.
        pass

    def start_inference(self, inference, generation):
        # Keep Aurora's actual local inference path in evaluations, while
        # avoiding the production voice/UI lifecycle.
        inference.request_generation = generation
        self.inf = inference
        self.inferences.append(inference)
        inference.finished.connect(self.inference_finished)
        inference.start()

    def run_local_action(self, name, args):
        # Diagnostic safety: record the route without opening apps or changing PC state.
        self.local_action = f"Ação local reconhecida: {name}({args!r}); não executada pela bancada."
        self.quick_summary_done(self.local_action, self.request_generation)

    def _finish(self):
        if not self.done:
            self.done = True
            self.completed.emit()

    def quick_search_done(self, query, output, generation=None):
        if self.trace is not None:
            self.trace.raw_result_text = output
        aurora.AuroraService.quick_search_done(self, query, output, generation)

    def quick_search_answer_done(self, text, generation, evidence, sources):
        aurora.AuroraService.quick_search_answer_done(self, text, generation, evidence, sources)
        self._finish()

    def speak_in_selected_language(self, text, generation=None):
        # Evaluation captures spoken text but never starts an audio device.
        if generation is None or generation == self.request_generation:
            self.speaker.say(text)

    def fx_lookup_done(self, lookup, generation=None):
        if self.trace is not None:
            quote = lookup.quote
            self.trace.fx_api_timings = lookup.api_timings
            if quote:
                formatted = aurora.aurora_fx.format_quote(quote)
                checked = aurora._verified_fx_answer(formatted, quote)
                self.trace.fx_guard = {"approved": checked == formatted, "formatted": formatted, "checked": checked}
                self.trace.fx_quote = {
                    "source": quote.source, "pair": f"{quote.base}/{quote.quote}",
                    "rate": str(quote.rate), "bid": str(quote.bid) if quote.bid is not None else None,
                    "ask": str(quote.ask) if quote.ask is not None else None,
                    "quote_date": quote.quote_date.isoformat(), "quote_time": quote.quote_time or None,
                    "amount": str(quote.amount) if quote.amount is not None else None,
                    "converted": str(quote.converted) if quote.converted is not None else None,
                    "retrieved_at": quote.retrieved_at.isoformat() if quote.retrieved_at else None,
                }
            elif lookup.fallback_output:
                self.trace.fx_guard = {"approved": False, "checked": "fallback para busca web"}
        aurora.AuroraService.fx_lookup_done(self, lookup, generation)
        self._finish()

    def quick_summary_done(self, summary, generation=None, context_extra=""):
        aurora.AuroraService.quick_summary_done(self, summary, generation, context_extra)
        self._finish()

    def quick_search_error(self, query, message, generation=None):
        if self.trace is not None:
            self.trace.errors.append({"kind": "search", "query": query, "message": str(message)})
        aurora.AuroraService.quick_search_error(self, query, message, generation)
        self._finish()

    def weather_done(self, text, generation=None):
        aurora.AuroraService.weather_done(self, text, generation)
        self._finish()

    def weather_error(self, message, generation=None):
        aurora.AuroraService.weather_error(self, message, generation)
        self._finish()

    def answer_done(self, text, generation=None):
        aurora.AuroraService.answer_done(self, text, generation)
        self._finish()

    def answer_error(self, text, generation=None):
        aurora.AuroraService.answer_error(self, text, generation)
        self._finish()

    def remember_exchange(self, user_text, assistant_text):
        aurora.AuroraService.remember_exchange(self, user_text, assistant_text)

    def search_update(self, query, output):
        aurora.AuroraService.search_update(self, query, output)

    def inference_finished(self):
        if not self.speaker.active and self.speaker.q.empty():
            self.voice.speaking = False

    def schedule_dismiss(self, _delay):
        pass

    def start_warmup(self):
        # Avoid background warmup as a side effect of an evaluation run.
        pass

    def request_approval(self, name, detail):
        self.quick_summary_done(
            f"Ação que exigiria aprovação reconhecida ({name}); não executada pela bancada.",
            self.request_generation,
        )


def decision_explanation(question):
    """Explain with the same pure predicates used inside AuroraService.ask."""
    direct = aurora.parse_local_command(question)
    if direct:
        return False, f"comando local reconhecido ({direct[0]}); a bancada não executa ações locais"
    local = aurora.local_datetime_answer(question)
    if local:
        return False, "pergunta respondida pela data/hora local do sistema"
    normalized = aurora.normalize_words(question)
    hardware_temp = bool(re.search(
        r"\b(cpu|gpu|processador|placa de video|computador|pc|hardware|placa grafica)\b",
        normalized,
    ))
    if not hardware_temp and re.search(r"\b(tempo|clima|previs[aã]o|temperatura|vai chover|chove)\b", question, re.I):
        return False, "rota direta de clima (API), sem busca web genérica"
    if aurora.aurora_fx.detect_fx_intent(question):
        return True, "rota estruturada de cotação/conversão; consulta API antes da busca web"
    explicit_query = aurora.search_intent(question)
    freshness = aurora.current_search_window(question)
    factual = aurora.factual_web_intent(question)
    if explicit_query:
        return True, f"pedido explícito de pesquisa; consulta inicial: {explicit_query!r}"
    if freshness:
        return True, f"sinal de atualidade; janela: {freshness}"
    if factual:
        return True, "reconhecida como pergunta factual por factual_web_intent"
    return False, "não corresponde a busca explícita, atualidade, pergunta factual ou rota local"


def parse_provider_result_lines(text):
    rows = []
    for line in text.splitlines():
        if " — " not in line:
            continue
        label, url = line.rsplit(" — ", 1)
        host = urlparse(url).hostname or "domínio desconhecido"
        date_match = re.search(r"\b\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?\b", label)
        title = re.sub(r"\s*\[[^\]]+\]\s*$", "", label).strip()
        rows.append((title, host.removeprefix("www."), date_match.group(0) if date_match else "sem data", url))
    return rows


def build_eval_record(line_number, question, answer, trace, elapsed_seconds,
                      should_search, reason, timed_out=False):
    """Machine-readable evidence/latency summary; factual correctness stays human-reviewed."""
    providers = []
    for item in trace.network_requests:
        if item.get("kind") not in ("DuckDuckGo Lite", "Bing RSS", "Bing Notícias", "Google Notícias"):
            continue
        providers.append({
            "provider": item.get("kind"), "elapsed_ms": item.get("elapsed_ms"),
            "status": item.get("status"), "extracted": item.get("extracted"),
            "after_pipeline": item.get("after_pipeline"), "error": item.get("error"),
        })
    sources = parse_provider_result_lines(trace.raw_result_text)
    return {
        "line": line_number, "question": question,
        "decision": {"search": bool(should_search), "reason": reason},
        "elapsed_ms": round(elapsed_seconds * 1000), "timed_out": bool(timed_out),
        "provider_requests": providers,
        "sources": [{"title": title, "domain": domain, "date": date, "url": url}
                    for title, domain, date, url in sources],
        "pages_attempted": len(trace.pages_read),
        "filters": dict(trace.filter_counts),
        "answer": answer or "",
    }


def canonical_result_url(url, provider):
    url = urljoin("https://duckduckgo.com", url) if provider == "DuckDuckGo Lite" else url
    parsed = urlparse(url)
    if provider == "DuckDuckGo Lite" and parsed.hostname and parsed.hostname.endswith("duckduckgo.com") and parsed.path == "/l/":
        url = (parse_qs(parsed.query).get("uddg") or [""])[0]
    elif provider == "Bing Notícias" and parsed.hostname and parsed.hostname.endswith("bing.com") and parsed.path == "/news/apiclick.aspx":
        url = (parse_qs(parsed.query).get("url") or [""])[0]
    elif provider == "Bing RSS" and parsed.hostname and parsed.hostname.endswith("bing.com") and parsed.path == "/ck/a":
        encoded = (parse_qs(parsed.query).get("u") or [""])[0]
        if encoded.startswith("a1"):
            try:
                url = base64.urlsafe_b64decode(encoded[2:] + "=" * ((-len(encoded[2:])) % 4)).decode("utf-8")
            except Exception:
                return ""
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl().rstrip("/")


class ResponseCapture:
    """Transparent response wrapper that records metadata and bytes read by Aurora."""

    def __init__(self, response, record, started):
        self._response = response
        self._record = record
        self._started = started
        self._sample = bytearray()
        self._bytes = 0

    def __getattr__(self, name):
        return getattr(self._response, name)

    def __enter__(self):
        self._response.__enter__()
        return self

    def read(self, *args, **kwargs):
        data = self._response.read(*args, **kwargs)
        if data:
            self._bytes += len(data)
            if len(self._sample) < 300:
                self._sample.extend(data[:300 - len(self._sample)])
        return data

    def _finish(self, error=None):
        headers = getattr(self._response, "headers", None)
        self._record.update({
            "status": getattr(self._response, "status", None) or getattr(self._response, "code", None),
            "content_type": headers.get("Content-Type") if headers else None,
            "content_length": headers.get("Content-Length") if headers else None,
            "bytes": self._bytes,
            "final_url": self._response.geturl(),
            "elapsed_ms": round((time.perf_counter() - self._started) * 1000),
        })
        if error:
            self._record["error"] = f"{type(error).__name__}: {error}"
        if self._sample:
            self._record["body_prefix"] = bytes(self._sample).decode("utf-8", errors="replace")

    def __exit__(self, exc_type, exc, tb):
        try:
            return self._response.__exit__(exc_type, exc, tb)
        finally:
            self._finish(exc)


def install_trace(trace):
    originals = {}
    original_search = web_pipeline.search_public_web
    original_page = web_fetch._search_page_excerpt
    original_open = web_pipeline.PUBLIC_OPENER.open
    original_urlopen = urllib.request.urlopen
    original_ddg_feed = web_pipeline.DuckDuckGoLiteResults.feed
    original_xml_fromstring = ET.fromstring
    original_fx_read_json = aurora.aurora_fx._read_json
    original_relevance = web_intent._search_relevance
    original_publication_window = web_freshness._publication_within_window
    original_public_url = web_security.public_http_url
    original_redirect = web_security.PublicRedirectHandler.redirect_request
    request_context = threading.local()

    def traced_fx_read_json(url, *args, **kwargs):
        started = time.perf_counter()
        payload = original_fx_read_json(url, *args, **kwargs)
        if "awesomeapi" in url:
            key = next(iter(payload), "") if isinstance(payload, dict) else ""
            row = payload.get(key, {}) if isinstance(payload, dict) else {}
            fields = {name: row.get(name) for name in ("code", "codein", "bid", "ask", "create_date")}
        else:
            fields = {name: payload.get(name) for name in ("base", "quote", "rate", "date")} if isinstance(payload, dict) else payload
        trace.append("fx_api_json", {"url": url, "fields": fields, "elapsed_ms": round((time.perf_counter() - started) * 1000)})
        return payload

    def traced_relevance(*args, **kwargs):
        score = original_relevance(*args, **kwargs)
        if score <= 0:
            trace.filter_counts["relevancia"] += 1
        return score

    def traced_publication(value, window, *args, **kwargs):
        accepted = original_publication_window(value, window, *args, **kwargs)
        if not accepted:
            trace.filter_counts["data_fonte"] += 1
        return accepted

    def traced_public_url(url):
        try:
            return original_public_url(url)
        except Exception:
            key = "redirecionamento" if getattr(request_context, "checking_redirect", False) else "url"
            trace.filter_counts[key] += 1
            raise

    def traced_redirect(self, req, fp, code, msg, headers, newurl):
        request_context.checking_redirect = True
        try:
            return original_redirect(self, req, fp, code, msg, headers, newurl)
        finally:
            request_context.checking_redirect = False

    def request_kind(url):
        if getattr(request_context, "reading_page", False):
            return "página candidata"
        host = urlparse(url).hostname or ""
        if host == "lite.duckduckgo.com":
            return "DuckDuckGo Lite"
        if host in ("www.bing.com", "bing.com") and urlparse(url).path == "/news/search":
            return "Bing Notícias"
        if host == "www.bing.com" or host == "bing.com":
            return "Bing RSS"
        if host == "news.google.com":
            return "Google Notícias"
        return ""

    def request_headers(req):
        try:
            return dict(req.header_items())
        except Exception:
            return {}

    def diagnostic_item(title, url, snippet, published, provider, publisher="", domain_hint=""):
        resolved = canonical_result_url(url, provider)
        domain = domain_hint or (urlparse(resolved).hostname or "domínio desconhecido")
        score = original_relevance(trace.current_query, title, snippet)
        return {
            "title": title,
            "domain": domain.removeprefix("www."),
            "date": published or "sem data",
            "snippet": " ".join(snippet.split())[:150],
            "url": url,
            "publisher": publisher,
            "relevance_score": score,
            "relevance_pass": score > 0,
        }

    def instrumented_open(original):
        def open_request(req, *args, **kwargs):
            url = getattr(req, "full_url", str(req))
            kind = request_kind(url)
            if not kind:
                return original(req, *args, **kwargs)
            record = {
                "kind": kind, "url": url, "request_headers": request_headers(req),
                "extracted": None, "candidate_urls": [], "bytes": 0,
            }
            trace.append("network_requests", record)
            started = time.perf_counter()
            request_context.current_request = record
            try:
                response = original(req, *args, **kwargs)
            except Exception as exc:
                record.update({
                    "status": getattr(exc, "code", None),
                    "content_type": getattr(exc, "headers", {}).get("Content-Type") if getattr(exc, "headers", None) else None,
                    "content_length": getattr(exc, "headers", {}).get("Content-Length") if getattr(exc, "headers", None) else None,
                    "final_url": getattr(exc, "url", url),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000),
                    "error": f"{type(exc).__name__}: {exc}",
                })
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        body = exc.read(1_500_000)
                        record["bytes"] = len(body)
                        record["body_prefix"] = body[:300].decode("utf-8", errors="replace")
                    except Exception:
                        pass
                    finally:
                        exc.close()
                raise
            return ResponseCapture(response, record, started)
        return open_request

    def traced_ddg_feed(parser, data):
        result = original_ddg_feed(parser, data)
        record = getattr(request_context, "current_request", None)
        if record and record["kind"] == "DuckDuckGo Lite":
            record["extracted"] = len(parser.results)
            record["candidate_urls"] = [row[0] for row in parser.results]
            record["raw_items"] = [
                diagnostic_item(title, url, snippet, "", "DuckDuckGo Lite")
                for url, title, snippet in parser.results
            ]
        request_context.current_request = None
        return result

    def traced_xml_fromstring(data, *args, **kwargs):
        record = getattr(request_context, "current_request", None)
        try:
            root = original_xml_fromstring(data, *args, **kwargs)
            if record and record["kind"] in ("Bing RSS", "Bing Notícias", "Google Notícias"):
                items = root.findall("./channel/item")
                record["extracted"] = len(items)
                record["candidate_urls"] = [item.findtext("link") or "" for item in items]
                raw_rows = []
                for item in items:
                    title = " ".join((item.findtext("title") or "").split())
                    snippet = item.findtext("description") or ""
                    source = item.find("source")
                    publisher = " ".join((source.text or "").split()) if source is not None else ""
                    source_url = source.get("url", "") if source is not None else ""
                    if record["kind"] == "Google Notícias":
                        snippet = re.sub(r"<[^>]+>", " ", html.unescape(snippet))
                        try:
                            published_at = parsedate_to_datetime(item.findtext("pubDate")).astimezone()
                            published = published_at.strftime("%d/%m/%Y %H:%M")
                        except Exception:
                            published = ""
                        domain_hint = urlparse(source_url).hostname or ""
                    else:
                        try:
                            published = web_pipeline._parse_publication_date(item.findtext("pubDate")).astimezone().strftime("%d/%m/%Y")
                        except Exception:
                            published = ""
                        domain_hint = urlparse(source_url).hostname or ""
                    if record["kind"] == "Bing Notícias":
                        try:
                            published = web_pipeline._parse_publication_date(item.findtext("pubDate")).astimezone().strftime("%d/%m/%Y %H:%M")
                        except Exception:
                            published = ""
                        domain_hint = urlparse(source_url).hostname or ""
                    raw_rows.append(diagnostic_item(
                        title, item.findtext("link") or "", snippet, published,
                        record["kind"], publisher, domain_hint,
                    ))
                record["raw_items"] = raw_rows
            return root
        except Exception as exc:
            if record:
                record["parse_error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            request_context.current_request = None

    def traced_search(query, freshness=None, news_only=None, progress=None):
        trace.append("search_calls", {"query": query, "freshness": freshness, "news_only": news_only})
        trace.current_query = query
        request_start = len(trace.network_requests)
        result = original_search(query, freshness, news_only, progress=progress)
        trace.raw_result_text = result
        returned_urls = {
            canonical_result_url(row[3], "") for row in parse_provider_result_lines(result)
        }
        for record in trace.network_requests[request_start:]:
            if record["kind"] not in ("DuckDuckGo Lite", "Bing RSS", "Bing Notícias", "Google Notícias"):
                continue
            candidates = [canonical_result_url(url, record["kind"]) for url in record["candidate_urls"]]
            record["after_pipeline"] = sum(bool(url) and url in returned_urls for url in candidates)
        return result

    def traced_page(url, query, timeout=3.0):
        request_context.reading_page = True
        page = {"url": url, "date": "sem data", "excerpt": ""}
        try:
            result = original_page(url, query, timeout)
            if isinstance(result, tuple):
                excerpt, published = result
            else:
                excerpt, published = result, ""
            page.update({"excerpt": excerpt, "date": published or "sem data"})
            if not published:
                trace.filter_counts["data_pagina_ausente"] += 1
            return result
        except Exception as exc:
            page["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            request_context.reading_page = False
            request_context.current_request = None
            trace.append("pages_read", page)

    originals.update({
        "search_public_web": original_search, "_search_page_excerpt": original_page,
        "opener_open": original_open, "urlopen": original_urlopen,
        "ddg_feed": original_ddg_feed, "xml_fromstring": original_xml_fromstring,
        "fx_read_json": original_fx_read_json, "relevance": original_relevance,
        "publication_window": original_publication_window, "public_url": original_public_url,
        "redirect_request": original_redirect,
    })
    web_pipeline.search_public_web = traced_search
    web_requests.search_public_web = traced_search
    aurora_service.search_public_web = traced_search
    web_pipeline._search_page_excerpt = traced_page
    web_fetch._search_page_excerpt = traced_page
    web_providers._search_page_excerpt = traced_page
    web_pipeline.PUBLIC_OPENER.open = instrumented_open(original_open)
    urllib.request.urlopen = instrumented_open(original_urlopen)
    web_pipeline.DuckDuckGoLiteResults.feed = traced_ddg_feed
    ET.fromstring = traced_xml_fromstring
    aurora.aurora_fx._read_json = traced_fx_read_json
    web_pipeline._search_relevance = traced_relevance
    web_intent._search_relevance = traced_relevance
    web_providers._search_relevance = traced_relevance
    web_pipeline._publication_within_window = traced_publication
    web_freshness._publication_within_window = traced_publication
    web_providers._publication_within_window = traced_publication
    web_providers.public_http_url = traced_public_url
    web_fetch.public_http_url = traced_public_url
    web_pipeline.public_http_url = traced_public_url
    web_security.public_http_url = traced_public_url
    web_security.PublicRedirectHandler.redirect_request = traced_redirect
    return originals


def restore_trace(originals):
    web_pipeline.search_public_web = originals["search_public_web"]
    web_requests.search_public_web = originals["search_public_web"]
    aurora_service.search_public_web = originals["search_public_web"]
    web_pipeline._search_page_excerpt = originals["_search_page_excerpt"]
    web_fetch._search_page_excerpt = originals["_search_page_excerpt"]
    web_providers._search_page_excerpt = originals["_search_page_excerpt"]
    web_pipeline.PUBLIC_OPENER.open = originals["opener_open"]
    urllib.request.urlopen = originals["urlopen"]
    web_pipeline.DuckDuckGoLiteResults.feed = originals["ddg_feed"]
    ET.fromstring = originals["xml_fromstring"]
    aurora.aurora_fx._read_json = originals["fx_read_json"]
    web_pipeline._search_relevance = originals["relevance"]
    web_intent._search_relevance = originals["relevance"]
    web_providers._search_relevance = originals["relevance"]
    web_pipeline._publication_within_window = originals["publication_window"]
    web_freshness._publication_within_window = originals["publication_window"]
    web_providers._publication_within_window = originals["publication_window"]
    web_pipeline.public_http_url = originals["public_url"]
    web_providers.public_http_url = originals["public_url"]
    web_fetch.public_http_url = originals["public_url"]
    web_security.public_http_url = originals["public_url"]
    web_security.PublicRedirectHandler.redirect_request = originals["redirect_request"]


def evaluate(line_number, question, cfg, timeout_seconds, history=None, context_note=""):
    trace = Trace()
    should_search, why = decision_explanation(question)
    service = EvalService(cfg)
    service.context_history = list(history or [])
    service.trace = trace
    loop = QEventLoop()
    service.completed.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timed_out = {"value": False}

    def timeout():
        timed_out["value"] = True
        loop.quit()

    timer.timeout.connect(timeout)
    timer.start(round(timeout_seconds * 1000))
    originals = install_trace(trace)
    started = time.perf_counter()
    try:
        service.ask(question)
        if not service.done:
            loop.exec()
    finally:
        elapsed = time.perf_counter() - started
        restore_trace(originals)
        timer.stop()

    lines = [f"## Linha {line_number}: {question}", ""]
    if context_note:
        lines.append(f"- **Contexto:** {context_note}.")
    lines.append(f"- **Decisão:** {'busca' if should_search else 'sem busca web'} — {why}.")
    if trace.search_calls:
        lines.append("- **Consulta(s) passada(s) ao caminho de busca:** " + "; ".join(
            f"`{call['query']}` (janela={call['freshness'] or 'sem janela'}, notícias={call['news_only']})"
            for call in trace.search_calls
        ))
    else:
        lines.append("- **Consulta(s) passada(s) ao caminho de busca:** nenhuma.")
    for error in trace.errors:
        lines.append(f"- **Falha interna capturada:** {error['kind']}: `{error['message']}`.")
    if trace.fx_api_json:
        lines.append("- **JSON cru da API (campos usados):**")
        lines.extend(f"  - `{item['url']}` — `{json.dumps(item['fields'], ensure_ascii=False)}`; {item['elapsed_ms']} ms" for item in trace.fx_api_json)
    if trace.fx_guard:
        lines.append(f"- **Checagem numérica:** {'APROVADA' if trace.fx_guard['approved'] else 'BLOQUEADA'}.")
        if trace.fx_quote:
            q = trace.fx_quote
            lines.append(f"  - Valores API ({q['pair']}): bid `{q['bid']}`, ask `{q['ask']}`, taxa `{q['rate']}`, conversão `{q['converted']}`.")
    lines.append("- **Diagnóstico HTTP por provedor:**")
    provider_requests = [item for item in trace.network_requests if item["kind"] in ("DuckDuckGo Lite", "Bing RSS", "Bing Notícias", "Google Notícias")]
    if provider_requests:
        for item in provider_requests:
            extracted = item["extracted"] if item["extracted"] is not None else "não medido (falha antes do parser)"
            after = item.get("after_pipeline", "não disponível")
            lines.append(
                f"  - **{item['kind']}** — URL `{item['url']}`; status `{item.get('status', 'sem resposta')}`; "
                f"content-type `{item.get('content_type') or 'desconhecido'}`; {item.get('bytes', 0)} bytes lidos"
                + (f" (Content-Length: {item['content_length']} bytes)" if item.get("content_length") else "")
                + "; "
                f"{item.get('elapsed_ms', 0)} ms; extraídos antes dos filtros: {extracted}; "
                f"presentes no resultado final do pipeline: {after}."
            )
            headers = item.get("request_headers") or {}
            lines.append("    - Headers enviados: " + ("; ".join(f"`{key}: {value}`" for key, value in headers.items()) or "nenhum capturado"))
            if item.get("error"):
                lines.append(f"    - Erro HTTP/rede: `{item['error']}`")
            if item.get("parse_error"):
                lines.append(f"    - Erro ao interpretar corpo: `{item['parse_error']}`")
            if item.get("extracted") == 0 or (item.get("extracted") is None and (item.get("error") or item.get("parse_error"))):
                preview = item.get("body_prefix") or "(nenhum corpo recebido)"
                lines.append(f"    - Prefixo do corpo (máx. 300 caracteres): `{preview[:300]}`")
            raw_items = item.get("raw_items", [])
            lines.append(f"    - Itens extraídos antes dos filtros ({len(raw_items)}):")
            if raw_items:
                for index, row in enumerate(raw_items, 1):
                    status = "passa no filtro de relevância" if row["relevance_pass"] else "descartado pelo filtro de relevância (score zero)"
                    publisher = f"; publicação: {row['publisher']}" if row.get("publisher") else ""
                    lines.append(
                        f"      {index}. **{row['title'] or '(sem título)'}** — domínio `{row['domain']}`; "
                        f"data: {row['date']}{publisher}; score de relevância isolado: {row['relevance_score']:.3f} "
                        f"({status}); trecho: {row['snippet'] or '(sem trecho)'}"
                    )
            else:
                lines.append("      nenhum item interpretado")
    else:
        lines.append("  - nenhuma requisição a provedor capturada")
    lines.append("  - O código não expõe um texto de motivo individual; o score abaixo é recalculado pela função pura de relevância, separadamente dos filtros de data e URL.")
    lines.append(
        "- **Resultados da busca antes da resposta do LLM** "
        "(normalizados/filtrados pelo pipeline; o HTML bruto não é exposto):"
    )
    rows = parse_provider_result_lines(trace.raw_result_text)
    if rows:
        lines.extend(f"  - {title} — `{domain}` — {date} — {url}" for title, domain, date, url in rows)
    elif trace.raw_result_text:
        lines.append("  - " + " ".join(trace.raw_result_text.split()))
    else:
        lines.append("  - nenhum")
    lines.append("- **Tentativas de leitura de páginas candidatas:**")
    if trace.pages_read:
        for page in trace.pages_read:
            request = next((item for item in trace.network_requests if item["kind"] == "página candidata" and item["url"] == page["url"]), None)
            if request:
                lines.append(
                    f"  - URL `{page['url']}` → final `{request.get('final_url') or 'indisponível'}`; "
                    f"status `{request.get('status', 'sem resposta')}`; {request.get('bytes', 0)} bytes; "
                    f"{request.get('elapsed_ms', 0)} ms; data extraída: {page['date']}"
                    + (f"; erro: `{request['error']}`" if request.get("error") else "")
                    + (f"; erro no parser: `{request['parse_error']}`" if request.get("parse_error") else "")
                )
            else:
                lines.append(f"  - URL `{page['url']}`; sem tentativa HTTP registrada; data: {page['date']}" + (f"; erro: `{page['error']}`" if page.get("error") else ""))
    else:
        lines.append("  - nenhuma")
    if trace.search_calls:
        counts = trace.filter_counts
        lines.append("- **Contagem diagnóstica de filtros:** " + "; ".join(f"{name}: {value}" for name, value in counts.items()))
    answer = service.response_summary or " ".join(service.speaker.parts).strip()
    if service.fx_api_timings:
        lines.append("- **Latência das APIs de câmbio:** " + "; ".join(f"{name}: {seconds * 1000:.0f} ms" for name, seconds in service.fx_api_timings))
    if trace.fx_guard and trace.fx_guard.get("checked"):
        lines.append("- **Resposta candidata antes da proteção:** " + trace.fx_guard.get("formatted", ""))
    if timed_out["value"] and not answer:
        answer = f"tempo limite após {timeout_seconds:g}s; sem resposta final"
    lines.append("- **Resposta final:** " + (answer or "sem resposta final capturada"))
    lines.append(f"- **Tempo total:** {elapsed:.2f}s")
    record = build_eval_record(line_number, question, answer, trace, elapsed,
                               should_search, why, timed_out["value"])
    return "\n".join(lines), answer, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", metavar="ARQUIVO.md", help="salva o trace em Markdown")
    parser.add_argument("--de", type=int, default=1, metavar="N", help="primeira linha inclusiva (padrão: 1)")
    parser.add_argument("--ate", type=int, metavar="M", help="última linha inclusiva (padrão: última pergunta)")
    parser.add_argument("--timeout", type=float, default=240, help="tempo máximo por pergunta (segundos)")
    parser.add_argument("--jsonl", metavar="ARQUIVO.jsonl",
                        help="grava resumo de métricas por pergunta, incrementalmente")
    args = parser.parse_args()
    if not QUESTIONS.is_file():
        parser.error(f"arquivo de perguntas não encontrado: {QUESTIONS}")
    questions = QUESTIONS.read_text(encoding="utf-8").splitlines()
    if not questions or any(not line.strip() for line in questions):
        parser.error(f"nenhuma pergunta em {QUESTIONS}")
    first_line = args.de
    last_line = args.ate if args.ate is not None else len(questions)
    if first_line < 1 or last_line > len(questions) or first_line > last_line:
        parser.error(f"intervalo inválido; use 1 <= --de <= --ate <= {len(questions)}")

    destination = Path(args.out).expanduser().resolve() if args.out else ROOT / "eval-search.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8") as output:
            output.write(
                f"# Avaliação da busca Aurora\n\nLinhas {first_line}–{last_line} de {len(questions)}. "
                "Trace persistido incrementalmente após cada pergunta.\n"
            )
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        parser.error(f"o arquivo de saída já existe; escolha outro caminho: {destination}")
    metrics_destination = Path(args.jsonl).expanduser().resolve() if args.jsonl else None
    if metrics_destination:
        metrics_destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with metrics_destination.open("x", encoding="utf-8"):
                pass
        except FileExistsError:
            parser.error(f"o arquivo JSONL já existe; escolha outro caminho: {metrics_destination}")

    app = QCoreApplication.instance() or QCoreApplication([])
    cfg = aurora.settings_load()
    answers = {}
    paired_second_lines = set(range(CONTEXT_PAIR_START + 1, CONTEXT_PAIR_END + 1, 2))
    for line_number in range(first_line, last_line + 1):
        history = None
        context_note = ""
        if line_number in paired_second_lines:
            first_pair_line = line_number - 1
            if first_pair_line not in answers:
                # A range may start on the second half of a pair. Run its first
                # line only as hidden context setup; the report still contains
                # exactly the requested --de/--ate interval.
                first_question = questions[first_pair_line - 1].strip()
                _, first_answer, _ = evaluate(
                    first_pair_line, first_question, cfg, args.timeout,
                    context_note="preparação de contexto fora do intervalo solicitado",
                )
                answers[first_pair_line] = (first_question, first_answer)
                context_note = f"linha {first_pair_line} executada como preparação de contexto fora do intervalo"
            first_question, first_answer = answers[first_pair_line]
            if not context_note:
                context_note = f"histórico da linha {first_pair_line} fornecido ao caminho AuroraService.ask"
            history = [
                {"role": "user", "content": first_question},
                {"role": "assistant", "content": first_answer},
            ]
        question = questions[line_number - 1].strip()
        block, answer, record = evaluate(
            line_number, question, cfg, args.timeout, history=history, context_note=context_note
        )
        answers[line_number] = (question, answer)
        with destination.open("a", encoding="utf-8") as output:
            output.write("\n\n---\n\n" + block + "\n")
            output.flush()
            os.fsync(output.fileno())
        if metrics_destination:
            with metrics_destination.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
        print(block + "\n", flush=True)
    print(f"Trace salvo incrementalmente em: {destination}", flush=True)
    return app


if __name__ == "__main__":
    main()
