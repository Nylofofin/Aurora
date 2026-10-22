#!/usr/bin/env python3
"""Trace Aurora's existing ask/search/answer path without opening UI or audio."""
from __future__ import annotations

import argparse
import os
import queue
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, Signal

import aurora

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "tests" / "eval" / "questions.txt"
PROVIDER_HOSTS = ("lite.duckduckgo.com", "bing.com", "news.google.com")
CONTEXT_PAIR_START = 427
CONTEXT_PAIR_END = 466


class Trace:
    def __init__(self):
        self.lock = threading.Lock()
        self.search_calls = []
        self.provider_requests = []
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


def install_trace(trace):
    originals = {}
    original_search = aurora.search_public_web
    original_page = aurora._search_page_excerpt
    original_request = aurora.urllib.request.Request

    def traced_search(query, freshness=None, news_only=None):
        trace.append("search_calls", {"query": query, "freshness": freshness, "news_only": news_only})
        result = original_search(query, freshness, news_only)
        trace.raw_result_text = result
        return result

    def traced_page(url, query, timeout=3.0):
        excerpt, published = original_page(url, query, timeout)
        trace.append("pages_read", {"url": url, "date": published or "sem data", "excerpt": excerpt})
        return excerpt, published

    def traced_request(url, *args, **kwargs):
        raw_url = getattr(url, "full_url", url)
        host = urlparse(str(raw_url)).hostname or ""
        if any(host == suffix or host.endswith("." + suffix) for suffix in PROVIDER_HOSTS):
            trace.append("provider_requests", str(raw_url))
        return original_request(url, *args, **kwargs)

    originals["search_public_web"] = original_search
    originals["_search_page_excerpt"] = original_page
    originals["Request"] = original_request
    aurora.search_public_web = traced_search
    aurora._search_page_excerpt = traced_page
    aurora.urllib.request.Request = traced_request
    return originals


def restore_trace(originals):
    aurora.search_public_web = originals["search_public_web"]
    aurora._search_page_excerpt = originals["_search_page_excerpt"]
    aurora.urllib.request.Request = originals["Request"]


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
    lines.append("- **URL(s) de consulta enviadas aos provedores:**")
    lines.extend(f"  - `{url}`" for url in trace.provider_requests)
    if not trace.provider_requests:
        lines.append("  - nenhuma capturada")
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
    lines.append("- **Páginas escolhidas pelo pipeline para leitura:**")
    if trace.pages_read:
        lines.extend(f"  - `{item['url']}` — {item['date']}" for item in trace.pages_read)
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
