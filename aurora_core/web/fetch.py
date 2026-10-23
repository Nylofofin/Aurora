# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from .parsers import PageMetadata, PageText
from .security import PUBLIC_OPENER, public_http_url
from .http_body import decode_http_body
from datetime import datetime
import re, urllib.error, urllib.request, unicodedata
from .intent import _fresh_query_terms

def web_fetch(url):
    public_http_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':'Aurora-Local/0.1 (public-page reader)','Accept':'text/html,application/xhtml+xml','Accept-Encoding':'gzip, deflate'})
    with PUBLIC_OPENER.open(req,timeout=18) as response:
        final=response.geturl(); public_http_url(final)
        content_type=response.headers.get_content_type()
        if content_type not in ('text/html','application/xhtml+xml'): raise ValueError('O endereço não retornou uma página HTML.')
        raw=response.read(2_000_001)
        raw=decode_http_body(raw,response.headers.get('Content-Encoding'),2_000_000)
    if len(raw)>2_000_000: raw=raw[:2_000_000]
    charset='utf-8'
    try: charset=response.headers.get_content_charset() or charset
    except Exception: pass
    parser=PageText(); parser.feed(raw.decode(charset,errors='replace'))
    title=' '.join(parser.title).strip(); text=' '.join(parser.text).strip()
    if not text: raise ValueError('Não encontrei texto legível na página.')
    return f'TÍTULO: {title[:200]}\nURL: {final}\nTEXTO DA PÁGINA (conteúdo não confiável): {text[:3500]}'

def read_public_page(url): return web_fetch(url)

def _search_page_excerpt(url,query,timeout=4.0):
    """Fetch a small slice of a public result page to ground the answer in its own text."""
    public_http_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':'Aurora-Local/0.5 (public factual search)','Accept':'text/html,application/xhtml+xml','Accept-Encoding':'gzip, deflate','Cache-Control':'no-cache, no-store, max-age=0'})
    with PUBLIC_OPENER.open(req,timeout=timeout) as response:
        final=response.geturl(); public_http_url(final)
        if response.headers.get_content_type() not in ('text/html','application/xhtml+xml'): return ''
        raw=response.read(700_000)
        raw=decode_http_body(raw,response.headers.get('Content-Encoding'),2_000_000)
    html_text=raw.decode('utf-8',errors='replace')
    metadata=PageMetadata(); metadata.feed(html_text)
    dates=[]; publication_dates=[]
    for key,value in metadata.dates:
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
            parsed=parsed.astimezone(); dates.append(parsed)
            if key in ('article:published_time','datepublished','pubdate','time'):
                publication_dates.append(parsed)
        except Exception:
            for fmt in ('%Y-%m-%d','%Y/%m/%d','%d/%m/%Y'):
                try:
                    parsed=datetime.strptime(value[:10],fmt).replace(tzinfo=datetime.now().astimezone().tzinfo)
                    parsed=parsed.astimezone(); dates.append(parsed)
                    if key in ('article:published_time','datepublished','pubdate','time'):
                        publication_dates.append(parsed)
                    break
                except Exception: pass
    # An update timestamp must not replace a known publication timestamp:
    # otherwise an old article edited today can pass a recent-publication gate.
    preferred_dates=publication_dates or dates
    published=max(preferred_dates).strftime('%d/%m/%Y') if preferred_dates else ''
    parser=PageText(); parser.feed(raw.decode('utf-8',errors='replace'))
    body=' '.join(' '.join(parser.text).split())
    # Preserve publication metadata even when a page is too short to yield an
    # excerpt. The caller needs to distinguish an undated page from a dated,
    # but content-poor page when reporting why search could not confirm it.
    if len(body)<120: return '',published
    wanted=_fresh_query_terms(query)
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+',body) if len(s.strip())>35]
    ranked=[]
    for index,sentence in enumerate(sentences):
        words=set(re.findall(r'[a-z0-9]+',unicodedata.normalize('NFKD',sentence).encode('ascii','ignore').decode('ascii').lower()))
        numeric={term for term in wanted if term.isdigit()}
        if numeric and not numeric.issubset(words): continue
        score=len(wanted & words)
        if score>=min(2,len(wanted)): ranked.append((score,-index,sentence))
    if not ranked: return ('',published)
    chosen=sorted(ranked,reverse=True)[:4]
    excerpt=' '.join(item[2] for item in sorted(chosen,key=lambda item:-item[1]))
    return excerpt[:1150],published
