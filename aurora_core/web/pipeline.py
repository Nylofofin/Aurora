from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse, urlencode, urljoin, parse_qs
import base64, concurrent.futures, threading, time, urllib.request
import xml.etree.ElementTree as ET
from ..system.files import normalize_words
from .intent import _search_query_variants, _search_relevance, current_search_window, news_search_intent
from .freshness import _has_expired_deadline, _has_stale_source_date, _has_stale_url_date, _publication_within_window, _parse_publication_date, _independent_recent_source_count
from .providers import search_google_news, search_searxng, _google_news_pipeline_items
from .fetch import _search_page_excerpt
from .parsers import DuckDuckGoLiteResults
from .security import PUBLIC_OPENER, public_http_url

def _search_public_web_uncached(query,freshness=None,news_only=None):
    query=' '.join(query.split())
    if not query or len(query)>180: raise ValueError('Consulta vazia ou longa demais.')
    freshness='' if freshness is False else (freshness or current_search_window(query))
    if news_only is None: news_only=news_search_intent(query)
    found=[]; seen=set(); failures=[]; provider_counts={}; rejected={'url':0,'atualidade':0,'relevancia':0,'duplicado':0}
    if news_only:
        freshness=freshness or '7d'
        try:
            news=search_google_news(query,freshness)
            found=_google_news_pipeline_items(news,query,freshness)
            seen={urlparse(item['url'])._replace(query='',fragment='').geturl().rstrip('/').casefold() for item in found}
        except Exception as exc:
            failures.append(f'Google Notícias: {type(exc).__name__}')
    # Use two genuinely different result interfaces. DDG's normal HTML endpoint
    # is frequently bot-challenged here, while Bing HTML often gives generic
    # navigational pages. DDG Lite and Bing RSS are lightweight alternatives.
    def fetch_provider(url,kind,timeout):
        headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36','Accept':'text/html,application/rss+xml,application/xml','Cache-Control':'no-cache, no-store, max-age=0','Pragma':'no-cache'}
        req=urllib.request.Request(url,headers=headers)
        with PUBLIC_OPENER.open(req,timeout=timeout) as response:
            public_http_url(response.geturl()); raw=response.read(1_500_000)
        if kind=='ddg':
            parser=DuckDuckGoLiteResults(); parser.feed(raw.decode('utf-8',errors='replace')); rows=parser.results
        else:
            root=ET.fromstring(raw); rows=[]
            for item in root.findall('./channel/item'):
                title=' '.join((item.findtext('title') or '').split())
                snippet=' '.join((item.findtext('description') or '').split())
                href=(item.findtext('link') or '').strip()
                published=''
                try: published=_parse_publication_date(item.findtext('pubDate')).astimezone().strftime('%d/%m/%Y')
                except Exception: pass
                rows.append((href,title,snippet,published))
        return rows
    def collect_query(search_query,relevance_query,timeout):
        providers=(
            ('DuckDuckGo Lite','https://lite.duckduckgo.com/lite/?'+urlencode({'q':search_query,'kl':'br-pt'}),'ddg'),
            ('Bing RSS','https://www.bing.com/search?'+urlencode({'q':search_query,'format':'rss','setlang':'pt-br'}),'bing-rss'),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)+1) as pool:
            jobs=[(provider,kind,pool.submit(fetch_provider,url,kind,timeout)) for provider,url,kind in providers]
            jobs.append(('SearXNG','searxng',pool.submit(search_searxng,search_query,freshness,news_only,timeout)))
            for provider,kind,future in jobs:
                stats=provider_counts.setdefault(provider,{'extraidos':0,'relevantes':0})
                try: rows=future.result(timeout=timeout+0.5)
                except Exception as exc:
                    failures.append(f'{provider}: {type(exc).__name__}'); continue
                stats['extraidos']+=len(rows)
                for row in rows:
                    href,title,snippet=row[:3]; published=row[3] if len(row)>3 else ''
                    href=urljoin('https://duckduckgo.com',href) if kind=='ddg' else href
                    parsed=urlparse(href)
                    if parsed.hostname and parsed.hostname.lower().endswith('duckduckgo.com') and parsed.path=='/l/':
                        href=(parse_qs(parsed.query).get('uddg') or [''])[0]
                    if parsed.hostname and parsed.hostname.lower().endswith('bing.com') and parsed.path=='/ck/a':
                        encoded=(parse_qs(parsed.query).get('u') or [''])[0]
                        if encoded.startswith('a1'):
                            try: href=base64.urlsafe_b64decode(encoded[2:]+'='*((-len(encoded[2:]))%4)).decode('utf-8')
                            except Exception: continue
                    try: public_http_url(href)
                    except Exception: rejected['url']+=1; continue
                    if freshness and (_has_expired_deadline(title+' '+snippet) or
                            _has_stale_source_date(title+' '+snippet,freshness) or
                            _has_stale_url_date(href,freshness) or
                            (published and _has_stale_source_date('published '+published,freshness))):
                        rejected['atualidade']+=1; continue
                    # The alternate query removes request phrasing, not subject terms.
                    relevance=_search_relevance(relevance_query,title,snippet)
                    if relevance<=0: rejected['relevancia']+=1; continue
                    stats['relevantes']+=1
                    key=urlparse(href)._replace(query='',fragment='').geturl().rstrip('/').casefold()
                    if key in seen: rejected['duplicado']+=1; continue
                    seen.add(key)
                    host=(urlparse(href).hostname or '').removeprefix('www.')
                    found.append({'provider':provider,'title':title,'snippet':snippet,'url':href,'host':host,
                        'published':published,'score':relevance})
    for attempt,(search_query,relevance_query) in enumerate(_search_query_variants(query,freshness)):
        collect_query(search_query,relevance_query,3.5 if attempt==0 else 1.8)
        enough=(_independent_recent_source_count(found,freshness)>=2) if freshness else bool(found)
        if enough: break
    window_days={'1d':1,'7d':7,'30d':30}.get(freshness,30)
    if freshness and not news_only and (not found or _independent_recent_source_count(found,freshness)<2):
        try:
            recent=search_google_news(query,freshness)
            for item in _google_news_pipeline_items(recent,query,freshness):
                key=urlparse(item['url'])._replace(query='',fragment='').geturl().rstrip('/').casefold()
                if key not in seen:
                    seen.add(key); found.append(item)
        except Exception: pass
    today=datetime.now().astimezone().date()
    def rank(item):
        try: age=max(0,(today-datetime.strptime(item['published'].split()[0],'%d/%m/%Y').date()).days)
        except Exception: age=window_days
        return item['score']+0.2*max(0,1-age/window_days)
    found.sort(key=rank,reverse=True)
    if not found:
        counts='; '.join(f'{name}: {stats["extraidos"]} extraídos, {stats["relevantes"]} relacionados' for name,stats in provider_counts.items()) or 'nenhum resultado extraído'
        drops=', '.join(f'{name} {count}' for name,count in rejected.items() if count)
        reason=(' provedores indisponíveis: '+'; '.join(dict.fromkeys(failures))+'.') if failures else ''
        filtered=(' descartes por '+drops+'.') if drops else ''
        return f'Não confirmei fontes para essa pergunta. Resultados de busca ({counts}).{filtered}{reason} Não vou completar por memória.'
    # Snippets are often truncated or misleading. Open up to two relevant pages
    # in parallel so the model gets the page's own evidence without serial delay.
    selected=[]; selected_sources=set()
    for item in found:
        if freshness and not _publication_within_window(item['published'],freshness): continue
        if freshness:
            source=(item.get('publisher') if item.get('host')=='news.google.com' else item.get('host')) or item.get('url')
            source=source.casefold()
            if source in selected_sources: continue
            selected_sources.add(source)
        selected.append(item)
        if len(selected)>=2: break
    if not selected:
        if freshness: return 'Não encontrei páginas com data recente verificável para confirmar esse fato. Não vou apresentar um resultado sem data como atual.'
        selected=found[:3]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(2,len(selected))) as pool:
        jobs=[(item,pool.submit(_search_page_excerpt,item['url'],query)) for item in selected]
        for item,future in jobs:
            try: excerpt,published=future.result(timeout=3.0)
            except Exception: excerpt,published='',''
            if published:
                item['published']=published
                if item.get('feed_published'): item['page_date_verified']=True
                if freshness and not _publication_within_window(published,freshness):
                    item['stale_page']=True
                    continue
            elif item.get('feed_published'):
                if excerpt: item['feed_date_accepted']=True
                else: item['unverified_page_date']=True
            if item.get('provider')=='Google Notícias' and not excerpt:
                item['page_unavailable']=True
            if excerpt:
                item['snippet']=((item['snippet']+' | Trecho da página aberta agora: ') if item['snippet'] else 'Trecho da página aberta agora: ')+excerpt
                item['page_opened']=True
    if freshness: found=[item for item in found if item.get('page_opened') and not item.get('stale_page') and not item.get('unverified_page_date') and not item.get('page_unavailable') and (not item.get('feed_published') or item.get('page_date_verified') or item.get('feed_date_accepted'))]
    if not found:
        if any(item.get('stale_page') for item in selected):
            return 'As páginas abertas estavam fora da janela pedida. Não consegui confirmar esse dado como atual.'
        return 'Não consegui ler páginas com conteúdo verificável para confirmar esse dado atual; não vou completá-lo por memória.'
    if freshness:
        if _independent_recent_source_count(found,freshness)<2:
            return 'As fontes encontradas não bastam para confirmar esse fato atual: preciso de duas publicações independentes, recentes e datadas. Não vou completar a resposta por memória.'
    output=[]
    for item in found[:8]:
        label=item['title'][:180]
        if item['published']:
            publisher=item.get('publisher') or item['provider']
            if item.get('feed_date_accepted'): publisher='Feed RSS: '+publisher
            label+=f' [{publisher} · {item["published"]}]'
        line=label+(f' :: {item["snippet"][:350]}' if item['snippet'] else '')+f' — {item["url"]}'
        output.append(line)
    checked=datetime.now().astimezone().strftime('%d/%m/%Y %H:%M %Z')
    sources=', '.join(dict.fromkeys(item['provider'] for item in found))
    return f'Resultados combinados de {sources}; consulta executada em {checked}. Relevância e atualidade da página precisam ser conferidas antes de afirmar fatos:\n'+'\n'.join(output)

_SEARCH_CACHE={}

_SEARCH_CACHE_LOCK=threading.Lock()

_SEARCH_CACHE_TTL=90

def search_public_web(query,freshness=None,news_only=None):
    """Short cache for repeated queries; volatile evidence expires after 90 seconds."""
    key=(normalize_words(query),freshness,news_only)
    now=time.monotonic()
    with _SEARCH_CACHE_LOCK:
        cached=_SEARCH_CACHE.get(key)
        if cached and now-cached[0]<_SEARCH_CACHE_TTL: return cached[1]
        for old_key,(created,_) in list(_SEARCH_CACHE.items()):
            if now-created>=_SEARCH_CACHE_TTL: _SEARCH_CACHE.pop(old_key,None)
    result=_search_public_web_uncached(query,freshness,news_only)
    if not result.startswith(('Não encontrei','Não consegui','As fontes encontradas','Os resultados que pareciam')):
        with _SEARCH_CACHE_LOCK:
            if len(_SEARCH_CACHE)>=48: _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
            _SEARCH_CACHE[key]=(time.monotonic(),result)
    return result
