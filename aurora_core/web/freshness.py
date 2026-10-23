# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from ..system.files import normalize_words
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import re, unicodedata
from .intent import _fresh_query_terms

def _has_expired_deadline(text,now=None):
    """Detect an explicitly expired offer/event instead of calling it current."""
    plain=unicodedata.normalize('NFKD',str(text)).encode('ascii','ignore').decode('ascii').lower()
    now=now or datetime.now().astimezone()
    months={'janeiro':1,'fevereiro':2,'marco':3,'abril':4,'maio':5,'junho':6,'julho':7,'agosto':8,'setembro':9,'outubro':10,'novembro':11,'dezembro':12,
            'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,'july':7,'august':8,'september':9,'october':10,'november':11,'december':12}
    pattern=r'\b(?:ate|valido ate|disponivel ate|termina em|termina no dia|until|valid until|available until|ends on|through)\s+(?:o\s+dia\s+)?(\d{1,2})\s+(?:de\s+)?([a-z]+)\s+(?:de\s+)?(20\d{2})\b'
    for day,month,year in re.findall(pattern,plain):
        if month in months:
            try:
                deadline=datetime(int(year),months[month],int(day),23,59,tzinfo=now.tzinfo)
                if deadline<now: return True
            except ValueError: pass
    for year,month,day in re.findall(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b',plain):
        try:
            deadline=datetime(int(year),int(month),int(day),23,59,tzinfo=now.tzinfo)
            if deadline<now and re.search(r'\b(ate|until|valid|available|termina|ends|promo|promocao|offer|oferta)\b',plain): return True
        except ValueError: pass
    return False

def _has_stale_source_date(text,window='30d',now=None):
    """Reject pages that declare a publication/update/check date outside the requested window."""
    now=now or datetime.now().astimezone()
    days={'1d':1,'7d':7,'30d':30}.get(window)
    if not days: return False
    plain=unicodedata.normalize('NFKD',str(text)).encode('ascii','ignore').decode('ascii').lower()
    markers=r'(?:published|updated|last checked|checked|revised|publicado|publicada|atualizado|atualizada|ultima verificacao|verificado|consultado)'
    months='january|february|march|april|may|june|july|august|september|october|november|december|janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro'
    candidates=[]
    for match in re.finditer(rf'{markers}[^.\n]{{0,35}}?\b({months})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(20\d{{2}})\b',plain):
        candidates.append((match.group(1),match.group(2),match.group(3),'month-first'))
    for match in re.finditer(rf'{markers}[^.\n]{{0,35}}?\b(\d{{1,2}})\s+(?:de\s+)?({months})[,]?\s+(?:de\s+)?(20\d{{2}})\b',plain):
        candidates.append((match.group(1),match.group(2),match.group(3),'day-first'))
    month_numbers={'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,'july':7,'august':8,'september':9,'october':10,'november':11,'december':12,
                   'janeiro':1,'fevereiro':2,'marco':3,'abril':4,'maio':5,'junho':6,'julho':7,'agosto':8,'setembro':9,'outubro':10,'novembro':11,'dezembro':12}
    cutoff=now-timedelta(days=days)
    for first,second,year,kind in candidates:
        try:
            month=month_numbers[second if kind=='day-first' else first]
            day=int(first if kind=='day-first' else second)
            if datetime(int(year),month,day,tzinfo=now.tzinfo)<cutoff: return True
        except (ValueError,KeyError): pass
    for match in re.finditer(rf'{markers}[^.\n]{{0,25}}?\b(\d{{1,2}})[/-](\d{{1,2}})[/-](20\d{{2}})\b',plain):
        try:
            if datetime(int(match.group(3)),int(match.group(2)),int(match.group(1)),tzinfo=now.tzinfo)<cutoff: return True
        except ValueError: pass
    return False

def _has_stale_url_date(url,window='30d',now=None):
    """Treat date-stamped article URLs as dated evidence, even if snippets omit the date."""
    now=now or datetime.now().astimezone()
    days={'1d':1,'7d':7,'30d':30}.get(window)
    if not days: return False
    cutoff=(now-timedelta(days=days)).date()
    for year,month,day in re.findall(r'\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b',str(url)):
        try:
            if datetime(int(year),int(month),int(day)).date()<cutoff: return True
        except ValueError: pass
    return False

def _publication_within_window(value,window,now=None):
    try:
        published=_parse_publication_date(value)
        now=now or datetime.now().astimezone()
        if now.tzinfo is None: now=now.replace(tzinfo=datetime.now().astimezone().tzinfo)
        days={'1d':1,'7d':7,'30d':30}.get(window,30)
        age=now.astimezone()-published.astimezone()
        return timedelta(0) <= age <= timedelta(days=days)
    except Exception: return False

def _parse_publication_date(value):
    """Parse machine and localized publication dates emitted by common feeds."""
    raw=' '.join(str(value or '').strip().split())
    for parser in (parsedate_to_datetime,datetime.fromisoformat):
        try:
            parsed=parser(raw.replace('Z','+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        except Exception: pass
    for fmt in ('%d/%m/%Y %H:%M:%S','%d/%m/%Y %H:%M','%d/%m/%Y'):
        try: return datetime.strptime(raw,fmt).replace(tzinfo=datetime.now().astimezone().tzinfo)
        except Exception: pass
    plain=normalize_words(raw)
    months={'jan':1,'janeiro':1,'fev':2,'fevereiro':2,'mar':3,'marco':3,'abr':4,'abril':4,'mai':5,'maio':5,'jun':6,'junho':6,'jul':7,'julho':7,'ago':8,'agosto':8,'set':9,'setembro':9,'out':10,'outubro':10,'nov':11,'novembro':11,'dez':12,'dezembro':12}
    match=re.search(r'\b(\d{1,2})\s+([a-z]+)\.?\s+(20\d{2})\b',plain)
    if match and match.group(2) in months:
        return datetime(int(match.group(3)),months[match.group(2)],int(match.group(1)),tzinfo=datetime.now().astimezone().tzinfo)
    for fmt in ('%B %d, %Y','%b %d, %Y','%Y-%m-%d'):
        try: return datetime.strptime(raw,fmt).replace(tzinfo=datetime.now().astimezone().tzinfo)
        except Exception: pass
    raise ValueError('Formato de data de publicação desconhecido')

def _independent_recent_source_count(items,window,now=None):
    sources=set(); headlines=[]
    for item in items:
        host=str(item.get('host') or '').lower().removeprefix('www.')
        source=(item.get('publisher') if host=='news.google.com' and item.get('publisher') else host)
        if not source or not _publication_within_window(item.get('published',''),window,now): continue
        title_terms=set(_fresh_query_terms(item.get('title','')))
        if title_terms and any(len(title_terms & prior)/max(1,len(title_terms | prior))>=0.8 for prior in headlines): continue
        if title_terms: headlines.append(title_terms)
        sources.add(source.casefold())
    return len(sources)
