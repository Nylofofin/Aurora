from __future__ import annotations

from .security import public_http_url
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
import concurrent.futures, html, re, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from .fetch import _search_page_excerpt
from .freshness import _publication_within_window
from .intent import _fresh_query_terms, _news_result_relevance, _search_relevance, current_search_window, international_news_only

def search_google_news(query,window):
    seconds={'1d':86400,'7d':7*86400,'30d':30*86400}.get(window,7*86400)
    label={'1d':'24 horas','7d':'7 dias','30d':'30 dias'}.get(window,'7 dias')
    now=datetime.now().astimezone(); cutoff=now-timedelta(seconds=seconds)
    international=international_news_only(query)
    locale={'hl':'pt-BR','gl':'US','ceid':'US:pt-419'} if international else {'hl':'pt-BR','gl':'BR','ceid':'BR:pt-419'}
    url='https://news.google.com/rss/search?'+urlencode({'q':f'{query} when:{window}',**locale})
    req=urllib.request.Request(url,headers={'User-Agent':'Aurora-Local/0.4','Accept':'application/rss+xml,application/xml,text/xml','Cache-Control':'no-cache, no-store, max-age=0','Pragma':'no-cache'})
    with urllib.request.urlopen(req,timeout=8) as response:
        public_http_url(response.geturl()); raw=response.read(1_500_000)
    root=ET.fromstring(raw); rows=[]; seen=set(); query_terms=_fresh_query_terms(query)
    for item in root.findall('./channel/item'):
        title=' '.join((item.findtext('title') or '').split())
        link=(item.findtext('link') or '').strip()
        publisher=' '.join((item.findtext('source') or '').split())
        description=re.sub(r'<[^>]+>',' ',html.unescape(item.findtext('description') or ''))
        if query_terms and _news_result_relevance(query,title,description)<=0: continue
        published=''
        try:
            published_at=parsedate_to_datetime(item.findtext('pubDate')).astimezone()
            if published_at<cutoff: continue
            published=published_at.strftime('%d/%m/%Y %H:%M')
        except Exception: continue
        key=title.casefold()
        if not title or not link or key in seen: continue
        try: public_http_url(link)
        except Exception: continue
        seen.add(key)
        summary=' '.join(description.split())[:350]
        rows.append(f'{title[:180]} [{publisher or "Google Notícias"} · {published}]'+(f' :: {summary}' if summary else '')+f' — {link}')
        if len(rows)>=6: break
    checked=now.strftime('%d/%m/%Y %H:%M %Z')
    if not rows: return f'Não encontrei publicações recentes relevantes sobre “{query}” nos últimos {label}. Busca atualizada em {checked}; não vou preencher com páginas antigas ou sem relação.'
    return f'Google Notícias, publicações dos últimos {label}; consulta atualizada em {checked}:\n'+'\n'.join(rows)

def _google_news_pipeline_items(results,query,window):
    """Translate RSS rows into common candidates; feed dates remain separate metadata."""
    rows=[]
    for line in results.splitlines()[1:]:
        if ' — ' not in line: continue
        label,url=line.rsplit(' — ',1); snippet=''
        if ' :: ' in label: label,snippet=label.split(' :: ',1)
        match=re.search(r'\s*\[([^\]]+?)\s*[·|]\s*(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}))?\]$',label)
        if not match: continue
        publisher,published_date,published_time=match.groups()
        published=' '.join(part for part in (published_date,published_time or '') if part)
        title=label[:match.start()].strip()
        try: public_http_url(url)
        except Exception: continue
        score=_search_relevance(query,title,snippet)
        if score<=0 or not _publication_within_window(published,window): continue
        rows.append({'provider':'Google Notícias','title':title,'snippet':snippet,'url':url,
            'host':'news.google.com','publisher':publisher,'published':published,
            'feed_published':True,'score':score})
    return rows

def _enrich_news_results(results,query,window):
    """Open current news articles and retain their publisher summary if blocked."""
    lines=results.splitlines(); header=lines[0] if lines else ''
    current_news_window=bool(current_search_window(query))
    parsed=[]
    for line in lines[1:]:
        if ' — ' not in line: continue
        label,url=line.rsplit(' — ',1); snippet=''
        if ' :: ' in label: label,snippet=label.split(' :: ',1)
        parsed.append([label,url,snippet])
    selected=parsed[:4]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3,len(selected) or 1)) as pool:
        jobs=[(row,pool.submit(_search_page_excerpt,row[1],query,2.5)) for row in selected]
        for row,future in jobs:
            try: excerpt,published=future.result(timeout=3.0)
            except Exception: excerpt,published='',''
            if published and not _publication_within_window(published,window):
                row[2]=''; row.append('stale')
            elif excerpt:
                row[2]=(row[2]+' | '+excerpt).strip(' |')[:1200]
            if current_news_window and not published:
                match=re.search(r'\[([^\]]+?)\s*[·|]\s*([^\]]+)\]$',row[0])
                if match:
                    row[0]=row[0][:match.start()]+f' [Feed RSS: {match.group(1)} · {match.group(2)}]'
    usable=[row for row in parsed if 'stale' not in row]
    if not usable: return 'As notícias encontradas apontam para páginas antigas ou indisponíveis; não consegui confirmar o conteúdo atual.'
    return header+'\n'+'\n'.join(f'{row[0]}'+(f' :: {row[2]}' if row[2] else '')+f' — {row[1]}' for row in usable)
