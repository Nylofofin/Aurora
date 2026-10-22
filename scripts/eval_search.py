#!/usr/bin/env python3
"""Trace Aurora's existing ask/search/answer path without opening UI or audio."""
from __future__ import annotations

import argparse
import base64
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin, urlparse

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, Signal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import aurora

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
        self.current_prompt = ""
        self.active_search_context = ""
        self.orb = OrbStub()
        self.voice = SimpleNamespace(speaking=False)
        self.speaker = SpeakerStub()
        self.trace = None
        self.local_action = ""
        self.done = False

    def start_background_request(self, request):
        self.background_requests.append(request)
        request.start()

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

    def quick_summary_done(self, summary, generation=None, context_extra=""):
        aurora.AuroraService.quick_summary_done(self, summary, generation, context_extra)
        self._finish()

    def quick_search_error(self, query, message, generation=None):
        aurora.AuroraService.quick_search_error(self, query, message, generation)
        self._finish()

    def weather_done(self, text, generation=None):
        aurora.AuroraService.weather_done(self, text, generation)
        self._finish()

    def weather_error(self, message, generation=None):
        aurora.AuroraService.weather_error(self, message, generation)
        self._finish()

    def answer_done(self, text):
        aurora.AuroraService.answer_done(self, text)
        self._finish()

    def answer_error(self, text):
        aurora.AuroraService.answer_error(self, text)
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


def canonical_result_url(url, provider):
    url = urljoin("https://duckduckgo.com", url) if provider == "DuckDuckGo Lite" else url
    parsed = urlparse(url)
    if provider == "DuckDuckGo Lite" and parsed.hostname and parsed.hostname.endswith("duckduckgo.com") and parsed.path == "/l/":
        url = (parse_qs(parsed.query).get("uddg") or [""])[0]
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
    original_search = aurora.search_public_web
    original_page = aurora._search_page_excerpt
    original_open = aurora.PUBLIC_OPENER.open
    original_urlopen = aurora.urllib.request.urlopen
    original_ddg_feed = aurora.DuckDuckGoLiteResults.feed
    original_xml_fromstring = aurora.ET.fromstring
    request_context = threading.local()

    def request_kind(url):
        if getattr(request_context, "reading_page", False):
            return "página candidata"
        host = urlparse(url).hostname or ""
        if host == "lite.duckduckgo.com":
            return "DuckDuckGo Lite"
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
                if isinstance(exc, aurora.urllib.error.HTTPError):
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
        request_context.current_request = None
        return result

    def traced_xml_fromstring(data, *args, **kwargs):
        record = getattr(request_context, "current_request", None)
        try:
            root = original_xml_fromstring(data, *args, **kwargs)
            if record and record["kind"] in ("Bing RSS", "Google Notícias"):
                items = root.findall("./channel/item")
                record["extracted"] = len(items)
                record["candidate_urls"] = [item.findtext("link") or "" for item in items]
            return root
        except Exception as exc:
            if record:
                record["parse_error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            request_context.current_request = None

    def traced_search(query, freshness=None, news_only=None):
        trace.append("search_calls", {"query": query, "freshness": freshness, "news_only": news_only})
        request_start = len(trace.network_requests)
        result = original_search(query, freshness, news_only)
        trace.raw_result_text = result
        returned_urls = {
            canonical_result_url(row[3], "") for row in parse_provider_result_lines(result)
        }
        for record in trace.network_requests[request_start:]:
            if record["kind"] not in ("DuckDuckGo Lite", "Bing RSS", "Google Notícias"):
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
    })
    aurora.search_public_web = traced_search
    aurora._search_page_excerpt = traced_page
    aurora.PUBLIC_OPENER.open = instrumented_open(original_open)
    aurora.urllib.request.urlopen = instrumented_open(original_urlopen)
    aurora.DuckDuckGoLiteResults.feed = traced_ddg_feed
    aurora.ET.fromstring = traced_xml_fromstring
    return originals


def restore_trace(originals):
    aurora.search_public_web = originals["search_public_web"]
    aurora._search_page_excerpt = originals["_search_page_excerpt"]
    aurora.PUBLIC_OPENER.open = originals["opener_open"]
    aurora.urllib.request.urlopen = originals["urlopen"]
    aurora.DuckDuckGoLiteResults.feed = originals["ddg_feed"]
    aurora.ET.fromstring = originals["xml_fromstring"]


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
    lines.append("- **Diagnóstico HTTP por provedor:**")
    provider_requests = [item for item in trace.network_requests if item["kind"] in ("DuckDuckGo Lite", "Bing RSS", "Google Notícias")]
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
    else:
        lines.append("  - nenhuma requisição a provedor capturada")
    lines.append("  - O código não expõe um motivo individual de descarte por resultado; as contagens são observacionais.")
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
    answer = service.response_summary or " ".join(service.speaker.parts).strip()
    if timed_out["value"] and not answer:
        answer = f"tempo limite após {timeout_seconds:g}s; sem resposta final"
    lines.append("- **Resposta final:** " + (answer or "sem resposta final capturada"))
    lines.append(f"- **Tempo total:** {elapsed:.2f}s")
    return "\n".join(lines), answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", metavar="ARQUIVO.md", help="salva o trace em Markdown")
    parser.add_argument("--de", type=int, default=1, metavar="N", help="primeira linha inclusiva (padrão: 1)")
    parser.add_argument("--ate", type=int, metavar="M", help="última linha inclusiva (padrão: última pergunta)")
    parser.add_argument("--timeout", type=float, default=240, help="tempo máximo por pergunta (segundos)")
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
                _, first_answer = evaluate(
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
        block, answer = evaluate(
            line_number, question, cfg, args.timeout, history=history, context_note=context_note
        )
        answers[line_number] = (question, answer)
        with destination.open("a", encoding="utf-8") as output:
            output.write("\n\n---\n\n" + block + "\n")
            output.flush()
            os.fsync(output.fileno())
        print(block + "\n", flush=True)
    print(f"Trace salvo incrementalmente em: {destination}", flush=True)
    return app


if __name__ == "__main__":
    main()
