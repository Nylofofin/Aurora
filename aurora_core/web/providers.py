from __future__ import annotations

from .security import PUBLIC_OPENER, public_http_url
from ..config import local_endpoint
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit
import html, json, os, re, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from .freshness import _publication_within_window
from .intent import _fresh_query_terms, _news_result_relevance, _search_relevance, international_news_only

def search_searxng(query,window='',news_only=False,timeout=2.0):
    """Query an optional same-machine SearXNG metasearch instance.

    Search results are leads only: callers still validate source URLs, dates,
    page contents, relevance, and independent publishers. Never follow a
    redirect from the local endpoint because it could disclose the query.
    """
    base=os.environ.get('AURORA_SEARXNG_URL','http://127.0.0.1:8080').strip().rstrip('/')
    parsed=urlsplit(base)
    if not local_endpoint(base) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('SearXNG precisa estar configurado em um endereço local.')
    endpoint=base if parsed.path.rstrip('/').endswith('/search') else base+'/search'
    params={'q':query,'format':'json','language':'pt-BR','categories':'news' if news_only else 'general','safesearch':'0'}
    if window:
        # SearXNG only accepts day/month/year. For a seven-day window omit this
        # provider hint and let Aurora's own publication-date filter enforce it.
        time_range={'1d':'day','30d':'month'}.get(window)
        if time_range: params['time_range']=time_range
    request=urllib.request.Request(endpoint+'?'+urlencode(params),headers={
        'User-Agent':'Aurora-Local/0.4','Accept':'application/json','Cache-Control':'no-cache, no-store, max-age=0'})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*_args,**_kwargs): return None

    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
    # Keep this optional provider from stretching the live assistant's search
    # deadline, even if a caller accidentally supplies a larger timeout.
    timeout=min(max(float(timeout),0.2),2.0)
    with opener.open(request,timeout=timeout) as response:
        if response.getcode()!=200: raise urllib.error.HTTPError(endpoint,response.getcode(),'Unexpected status',response.headers,None)
        if 'application/json' not in response.headers.get('Content-Type','').lower():
            raise ValueError('SearXNG não retornou JSON.')
        raw=response.read(1_500_001)
    if len(raw)>1_500_000: raise ValueError('Resposta SearXNG excedeu o limite de tamanho.')
    payload=json.loads(raw)
    if not isinstance(payload,dict) or not isinstance(payload.get('results'),list):
        raise ValueError('Resposta SearXNG sem lista de resultados válida.')
    rows=[]
    for item in payload['results']:
        if not isinstance(item,dict): continue
        href=str(item.get('url') or '').strip()
        title=' '.join(str(item.get('title') or '').split())
        snippet=' '.join(str(item.get('content') or '').split())
        published=item.get('publishedDate')
        published=' '.join(str(published).split()) if isinstance(published,str) else ''
        if href and title: rows.append((href,title,snippet,published))
    return rows

def search_google_news(query,window):
    seconds={'1d':86400,'7d':7*86400,'30d':30*86400}.get(window,7*86400)
    label={'1d':'24 horas','7d':'7 dias','30d':'30 dias'}.get(window,'7 dias')
    now=datetime.now().astimezone(); cutoff=now-timedelta(seconds=seconds)
    international=international_news_only(query)
    locale={'hl':'pt-BR','gl':'US','ceid':'US:pt-419'} if international else {'hl':'pt-BR','gl':'BR','ceid':'BR:pt-419'}
    url='https://news.google.com/rss/search?'+urlencode({'q':f'{query} when:{window}',**locale})
    req=urllib.request.Request(url,headers={'User-Agent':'Aurora-Local/0.4','Accept':'application/rss+xml,application/xml,text/xml','Cache-Control':'no-cache, no-store, max-age=0','Pragma':'no-cache'})
    with PUBLIC_OPENER.open(req,timeout=8) as response:
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
