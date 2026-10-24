# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
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
            return data
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
        try:
            dt = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            if dt < now:
                dt = dt.replace(year=dt.year + 1)
            return dt.timestamp()
        except ValueError:
            pass

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
        try:
            dt = now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            if dt < now:
                dt = dt.replace(year=dt.year + 1)
            return dt.timestamp()
        except ValueError:
            pass

    # "amanhã às 15h30"
    m = re.search(r'\bamanha\b.*?(\d{1,2})(?:[h:](\d{0,2}))?', text_norm)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        dt = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt.timestamp()

    # "hoje às 15h"
    m = re.search(r'\bhoje\b.*?(\d{1,2})(?:[h:](\d{0,2}))?', text_norm)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt > now:
            return dt.timestamp()

    # "sexta às 9h" / "próxima quinta às 8h"
    for day_name, weekday_num in sorted(_WEEKDAYS.items(), key=lambda x: -len(x[0])):
        if day_name in text_norm:
            m = re.search(r'(\d{1,2})(?:[h:](\d{0,2}))?', text_norm)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                days_ahead = (weekday_num - now.weekday()) % 7 or 7
                dt = (now + timedelta(days=days_ahead)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                return dt.timestamp()
            break

    return None


# ── Public API ──────────────────────────────────────────────────────────────

def agenda_add(title: str, when_ts: float, notes: str = '') -> str:
    """Add a new event. Returns a human-readable confirmation."""
    if not title.strip():
        return 'Precisa de um título para o compromisso.'
    if not when_ts or when_ts < time.time() - 60:
        return 'A data ou hora do compromisso não foi reconhecida ou já passou.'
    events = _load()
    event = {
        'id': _next_id(events),
        'title': title.strip()[:200],
        'when': when_ts,
        'notes': notes.strip()[:500],
        'created': time.time(),
    }
    events.append(event)
    events.sort(key=lambda e: e['when'])
    _save(events)
    return f'Compromisso "{event["title"]}" adicionado para {_format_dt(when_ts)}.'


def agenda_list(days: int = 7) -> str:
    """List upcoming events in the next *days* days."""
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
    """Remove an event by id, or all past events if id is None."""
    events = _load()
    if event_id is None:
        now = time.time()
        kept = [e for e in events if e.get('when', 0) >= now - 60]
        removed = len(events) - len(kept)
        if not removed:
            return 'Não havia compromissos passados para remover.'
        _save(kept)
        return f'Removi {removed} compromisso(s) já passado(s).'
    remaining = [e for e in events if e.get('id') != event_id]
    if len(remaining) == len(events):
        return f'Não encontrei o compromisso {event_id}.'
    _save(remaining)
    return f'Compromisso {event_id} removido.'


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
