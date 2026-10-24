# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import math
import json
import os
import re
import time
from pathlib import Path

from PySide6.QtCore import QTimer

from .text import normalize_words

MAX_TIMER_SECONDS = 7 * 24 * 60 * 60

_UNITS = {
    'segundo': 1, 'segundos': 1, 's': 1,
    'minuto': 60, 'minutos': 60, 'min': 60, 'mins': 60, 'm': 60,
    'hora': 3600, 'horas': 3600, 'h': 3600,
}
_ONES = {
    'zero': 0, 'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'tres': 3,
    'quatro': 4, 'cinco': 5, 'seis': 6, 'sete': 7, 'oito': 8, 'nove': 9,
    'dez': 10, 'onze': 11, 'doze': 12, 'treze': 13, 'quatorze': 14,
    'catorze': 14, 'quinze': 15, 'dezesseis': 16, 'dezessete': 17,
    'dezoito': 18, 'dezenove': 19,
}
_TENS = {
    'vinte': 20, 'trinta': 30, 'quarenta': 40, 'cinquenta': 50,
    'sessenta': 60, 'setenta': 70, 'oitenta': 80, 'noventa': 90,
}
_NUMBER_WORD = r'(?:' + '|'.join(sorted((*_ONES, *_TENS), key=len, reverse=True)) + r')(?:\s+e\s+(?:' + '|'.join(sorted((word for word, value in _ONES.items() if 0 < value < 10), key=len, reverse=True)) + r'))?'
_DURATION = re.compile(
    r'(?P<number>\d+(?:[,.]\d+)?|' + _NUMBER_WORD + r')\s*(?P<unit>segundos?|minutos?|mins?|min|horas?|hrs?|s|m|h)\b'
)


def _number_value(value: str) -> float:
    if re.fullmatch(r'\d+(?:[,.]\d+)?', value):
        return float(value.replace(',', '.'))
    parts = value.split(' e ', 1)
    total = 0
    for word in parts:
        if word in _ONES:
            total += _ONES[word]
        elif word in _TENS:
            total += _TENS[word]
        else:
            return 0
    return float(total)


def parse_timer_duration(text: str) -> int | None:
    """Read one or more Portuguese hour/minute/second amounts from speech."""
    normalized = normalize_words(text)
    total = 0.0
    found = False
    for match in _DURATION.finditer(normalized):
        found = True
        unit = match.group('unit')
        factor = 3600 if unit.startswith('h') else 60 if unit.startswith('m') else 1
        total += _number_value(match.group('number')) * factor
    if not found or total <= 0:
        return None
    seconds = math.ceil(total)
    return seconds if seconds <= MAX_TIMER_SECONDS else None


def parse_timer_command(prompt: str):
    text = normalize_words(prompt)
    if not re.search(r'\b(timers?|temporizador(?:es)?|cronometros?|contagem regressiva)\b', text):
        return None
    if re.search(r'\b(cancele|cancelar|cancela|interrompa|interromper|interrompe|pare|parar|encerre|encerrar)\b', text):
        if re.search(r'\b(todos|todas|geral|gerais)\b', text):
            return ('timer_cancel', {'timer_id': None})
        match = re.search(r'\b(?:timers?|temporizador(?:es)?)\s+(?:numero\s+)?(\d+)\b', text)
        return ('timer_cancel', {'timer_id': int(match.group(1)) if match else None})
    seconds = parse_timer_duration(text)
    if seconds is not None:
        return ('timer_start', {'seconds': seconds})
    # Any remaining explicit timer reference is a request to inspect it. This
    # keeps short questions such as "tem timer?" out of the language model.
    if re.search(r'\b(coloque|coloca|crie|cria|inicie|inicia|defina|define|configure|configura|programe|programa|arme|armar)\b', text):
        return ('timer_missing_duration', {})
    return ('timer_list', {})


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    parts = []
    for amount, name in ((3600, 'hora'), (60, 'minuto'), (1, 'segundo')):
        value, seconds = divmod(seconds, amount)
        if value:
            parts.append(f'{value} {name if value == 1 else name + "s"}')
    return ' e '.join(parts) if parts else 'menos de um segundo'


class TimerManager:
    """Small in-process countdown timers; no worker thread or external service."""

    def __init__(self, on_finish, parent=None, timer_factory=QTimer, state_path=None):
        self.on_finish = on_finish
        self.parent = parent
        self.timer_factory = timer_factory
        self._timers = {}
        self._next_id = 1
        self.state_path = Path(state_path) if state_path else (
            Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
            / 'aurora' / 'timers.json'
        )
        self._restore()

    def _new_timer(self, timer_id, deadline, seconds):
        timer = self.timer_factory(self.parent)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda identifier=timer_id: self._finish(identifier))
        self._timers[timer_id] = {'timer': timer, 'deadline': deadline, 'seconds': seconds}
        remaining_ms = max(1, math.ceil((deadline - time.time()) * 1000))
        timer.start(remaining_ms)

    def _persist(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_path.parent, 0o700)
        state = {
            'next_id': self._next_id,
            'timers': [
                {'id': timer_id, 'deadline': item['deadline'], 'seconds': item['seconds']}
                for timer_id, item in sorted(self._timers.items())
            ],
        }
        temporary = self.state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.state_path)

    def _restore(self):
        try:
            state = json.loads(self.state_path.read_text(encoding='utf-8'))
            if not isinstance(state, dict) or not isinstance(state.get('timers'), list):
                raise ValueError('invalid timer state')
            self._next_id = max(1, int(state.get('next_id', 1)))
            for item in state['timers']:
                timer_id = int(item['id'])
                deadline = float(item['deadline'])
                seconds = int(item['seconds'])
                if timer_id < 1 or seconds < 1 or seconds > MAX_TIMER_SECONDS or not math.isfinite(deadline):
                    continue
                self._new_timer(timer_id, deadline, seconds)
                self._next_id = max(self._next_id, timer_id + 1)
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self._timers.clear()
            self._next_id = 1
            print('[timer] saved timer state could not be read; starting empty', flush=True)

    def start(self, seconds: int) -> str:
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return 'Não entendi a duração do timer.'
        if seconds <= 0 or seconds > MAX_TIMER_SECONDS:
            return 'O timer precisa ter uma duração entre um segundo e sete dias.'
        timer_id = self._next_id
        self._next_id += 1
        deadline = time.time() + seconds
        self._new_timer(timer_id, deadline, seconds)
        try:
            self._persist()
        except OSError:
            item = self._timers.pop(timer_id)
            item['timer'].stop()
            print('[timer] could not save state; timer was not started', flush=True)
            return 'Não consegui salvar o timer; não o iniciei.'
        print(f'[timer] started id={timer_id} seconds={seconds}', flush=True)
        return f'Timer {timer_id} iniciado para {format_duration(seconds)}.'

    def cancel(self, timer_id=None) -> str:
        if timer_id is None:
            previous = self._timers.copy()
            timers = list(self._timers.values())
            for item in timers:
                item['timer'].stop()
            self._timers.clear()
            try:
                self._persist()
            except OSError:
                self._timers = previous
                for item in self._timers.values():
                    item['timer'].start(max(1, math.ceil((item['deadline'] - time.time()) * 1000)))
                return 'Não consegui salvar o cancelamento; os timers continuam ativos.'
            return 'Cancelei todos os timers ativos.' if timers else 'Não há timers ativos para cancelar.'
        try:
            timer_id = int(timer_id)
        except (TypeError, ValueError):
            return 'Diga o número do timer ou peça para cancelar todos.'
        item = self._timers.pop(timer_id, None)
        if item is None:
            return f'Não encontrei o timer {timer_id} ativo.'
        item['timer'].stop()
        try:
            self._persist()
        except OSError:
            self._timers[timer_id] = item
            item['timer'].start(max(1, math.ceil((item['deadline'] - time.time()) * 1000)))
            return f'Não consegui salvar o cancelamento; o timer {timer_id} continua ativo.'
        return f'Cancelado o timer {timer_id}.'

    def list_active(self) -> str:
        if not self._timers:
            return 'Não há timers ativos.'
        now = time.time()
        lines = [
            f'Timer {timer_id}: faltam {format_duration(math.ceil(item["deadline"] - now))}.'
            for timer_id, item in sorted(self._timers.items())
        ]
        return ' '.join(lines)

    def _finish(self, timer_id):
        item = self._timers.pop(timer_id, None)
        if item is not None:
            try:
                self._persist()
            except OSError:
                print(f'[timer] could not persist completion id={timer_id}', flush=True)
            self.on_finish(timer_id, item['seconds'])
