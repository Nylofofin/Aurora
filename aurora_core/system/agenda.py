# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_MONTHS = {
    'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3,
    'abril': 4, 'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
    'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12,
}
_WEEKDAYS = {
    'segunda': 0, 'segunda-feira': 0, 'terca': 1, 'terça': 1,
    'terca-feira': 1, 'terça-feira': 1, 'quarta': 2, 'quarta-feira': 2,
    'quinta': 3, 'quinta-feira': 3, 'sexta': 4, 'sexta-feira': 4,
    'sabado': 5, 'sábado': 5, 'domingo': 6,
}


def _state_path() -> Path:
    return (
        Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
        / 'aurora' / 'agenda.json'
    )


def _load() -> list[dict]:
    try:
        data = json.loads(_state_path().read_text(encoding='utf-8'))
        if isinstance(data, list):
            valid = []
            for event in data:
                if not isinstance(event, dict):
                    continue
                try:
                    event_id = int(event['id'])
                    when = float(event['when'])
                    created = float(event.get('created', 0))
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
                title = event.get('title')
                if (event_id < 1 or not math.isfinite(when) or not math.isfinite(created)
                        or not isinstance(title, str)
                        or not title.strip()):
                    continue
                valid.append({'id': event_id, 'when': when, 'created': created,
                              'title': title[:200], 'notes': str(event.get('notes', ''))[:500]})
            return valid
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _save(events: list[dict]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _next_id(events: list[dict]) -> int:
    return max((e.get('id', 0) for e in events), default=0) + 1


def _format_dt(ts: float) -> str:
    """Return a human-readable Portuguese date/time string."""
    dt = datetime.fromtimestamp(ts).astimezone()
    weekday = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'][dt.weekday()]
    return dt.strftime(f'{weekday}, %d/%m/%Y às %H:%M')


def parse_datetime(text: str) -> Optional[float]:
    """Try to extract an absolute timestamp from Portuguese natural language.

    Recognises patterns such as:
        "amanhã às 15h", "sexta às 9h30", "dia 5 de novembro às 8h",
        "25/12 às 10h", "27/10/2026 às 18:30"
    Returns a Unix timestamp or None if nothing matched.
    """
    from .text import normalize_words
    text_norm = normalize_words(text)
    now = datetime.now().astimezone()

    def make_datetime(year, month, day, hour, minute=0, *, roll_year=False):
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return None
        try:
            result = now.replace(year=year, month=month, day=day, hour=hour,
                                 minute=minute, second=0, microsecond=0)
            if roll_year and result <= now:
                result = result.replace(year=result.year + 1)
            return result.timestamp()
        except (ValueError, OverflowError):
            return None

    # Full ISO-like: 25/12/2026 18:30 or 25/12 18:30
    m = re.search(
        r'(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{4}))?\s+(?:as\s+)?(\d{1,2})(?:[h:h](\d{0,2}))?',
        text_norm,
    )
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        hour = int(m.group(4))
        minute = int(m.group(5)) if m.group(5) else 0
        return make_datetime(year, month, day, hour, minute, roll_year=m.group(3) is None)

    # "dia 5 de novembro às 18h"
    m = re.search(
        r'dia\s+(\d{1,2})\s+de\s+(' + '|'.join(_MONTHS) + r')\s+(?:as\s+)?(\d{1,2})(?:[h:](\d{0,2}))?',
        text_norm,
    )
    if m:
        day = int(m.group(1))
        month = _MONTHS[m.group(2)]
        hour = int(m.group(3))
        minute = int(m.group(4)) if m.group(4) else 0
        return make_datetime(now.year, month, day, hour, minute, roll_year=True)

    # "amanhã às 15h30"
    m = re.search(r'\bamanha\b(.*)', text_norm)
    if m:
        tm = re.search(r'\bas\s+(\d{1,2})(?:\s*(?:h|:)\s*(\d{1,2})?)?\b|\b(\d{1,2})\s*h\s*(\d{1,2})?\b', m.group(1))
        if tm:
            hour = int(tm.group(1) or tm.group(3))
            minute = int(tm.group(2) or tm.group(4) or 0)
            tomorrow = now + timedelta(days=1)
            return make_datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute)

    # "hoje às 15h"
    m = re.search(r'\bhoje\b(.*)', text_norm)
    if m:
        tm = re.search(r'\bas\s+(\d{1,2})(?:\s*(?:h|:)\s*(\d{1,2})?)?\b|\b(\d{1,2})\s*h\s*(\d{1,2})?\b', m.group(1))
        if tm:
            hour = int(tm.group(1) or tm.group(3))
            minute = int(tm.group(2) or tm.group(4) or 0)
            ts = make_datetime(now.year, now.month, now.day, hour, minute)
            if ts and ts > now.timestamp():
                return ts

    # "sexta às 9h" / "próxima quinta às 8h"
    for day_name, weekday_num in sorted(_WEEKDAYS.items(), key=lambda x: -len(x[0])):
        if day_name in text_norm:
            weekday_pos = text_norm.find(day_name)
            after_weekday = text_norm[weekday_pos + len(day_name):]
            m = re.search(r'\bas\s+(\d{1,2})(?:\s*(?:h|:)(\d{1,2})?)?\b|\b(\d{1,2})\s*h\s*(\d{1,2})?\b', after_weekday)
            if m:
                hour = int(m.group(1) or m.group(3))
                minute = int(m.group(2) or m.group(4) or 0)
                days_ahead = (weekday_num - now.weekday()) % 7 or 7
                day = now + timedelta(days=days_ahead)
                return make_datetime(day.year, day.month, day.day, hour, minute)
            break

    return None


# ── Public API ──────────────────────────────────────────────────────────────

def agenda_add(title: str, when_ts: float, notes: str = '') -> str:
    """Add a new event. Returns a human-readable confirmation."""
    if not isinstance(title, str) or not title.strip():
        return 'Precisa de um título para o compromisso.'
    try:
        when_ts = float(when_ts)
    except (TypeError, ValueError, OverflowError):
        when_ts = 0
    if not math.isfinite(when_ts) or when_ts < time.time() - 60:
        return 'A data ou hora do compromisso não foi reconhecida ou já passou.'
    events = _load()
    event = {
        'id': _next_id(events),
        'title': title.strip()[:200],
        'when': when_ts,
        'notes': str(notes).strip()[:500],
        'created': time.time(),
    }
    events.append(event)
    events.sort(key=lambda e: e['when'])
    _save(events)
    return f'Compromisso "{event["title"]}" adicionado para {_format_dt(when_ts)}.'


def agenda_list(days: int = 7) -> str:
    """List upcoming events in the next *days* days."""
    try:
        days = max(1, min(365, int(days)))
    except (TypeError, ValueError, OverflowError):
        days = 7
    events = _load()
    now = time.time()
    cutoff = now + days * 86400
    upcoming = [e for e in events if now - 60 <= e.get('when', 0) <= cutoff]
    upcoming.sort(key=lambda e: e['when'])
    if not upcoming:
        return f'Nenhum compromisso nos próximos {days} dias.'
    lines = [f'Agenda para os próximos {days} dias:']
    for e in upcoming:
        label = _format_dt(e['when'])
        notes = f' — {e["notes"]}' if e.get('notes') else ''
        lines.append(f'• [{e["id"]}] {e["title"]}: {label}{notes}')
    return '\n'.join(lines)


def agenda_cancel(event_id: Optional[int] = None) -> str:
    """Remove one event by id. Bulk cleanup is a separate confirmed action."""
    if event_id is None:
        return 'Informe o número do compromisso que deseja remover.'
    try:
        event_id = int(event_id)
    except (TypeError, ValueError, OverflowError):
        return 'O identificador do compromisso é inválido.'
    if event_id < 1:
        return 'O identificador do compromisso é inválido.'
    events = _load()
    remaining = [e for e in events if e.get('id') != event_id]
    if len(remaining) == len(events):
        return f'Não encontrei o compromisso {event_id}.'
    _save(remaining)
    return f'Compromisso {event_id} removido.'


def agenda_clear() -> str:
    """Clear all events completely."""
    events = _load()
    if not events:
        return 'A agenda já está vazia.'
    count = len(events)
    _save([])
    return f'Limpei todos os {count} compromisso(s) da sua agenda.'


def agenda_nearest() -> str:
    """Return the next upcoming event as a short spoken string."""
    events = _load()
    now = time.time()
    upcoming = sorted(
        (e for e in events if e.get('when', 0) >= now - 60),
        key=lambda e: e['when'],
    )
    if not upcoming:
        return 'Não há compromissos agendados.'
    e = upcoming[0]
    return f'Próximo compromisso: {e["title"]}, {_format_dt(e["when"])}.'
