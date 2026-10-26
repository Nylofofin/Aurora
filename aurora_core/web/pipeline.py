# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse, urlencode, urljoin, parse_qs
import base64, concurrent.futures, os, re, threading, time, unicodedata, urllib.request
import xml.etree.ElementTree as ET
from ..system.files import normalize_words
from .intent import _fresh_query_terms, _search_query_variants, _search_relevance, _search_term_forms, asks_latest_version, current_search_window, international_news_only, news_search_intent
from .freshness import _has_expired_deadline, _has_stale_source_date, _has_stale_url_date, _publication_within_window, _parse_publication_date, _independent_recent_source_count
from .providers import search_google_news, search_bing_news, _google_news_pipeline_items
from .fetch import _search_page_excerpt
from .parsers import DuckDuckGoLiteResults
from .security import PUBLIC_OPENER, public_http_url
from .http_body import decode_http_body
from .orchestra import plan_research_subagents, resource_worker_limit

def _candidate_rank(item, freshness, news_only=False, today=None, window_days=None, query=''):
    today=today or datetime.now().astimezone().date()
    if window_days is None: window_days={'1d':1,'7d':7,'30d':30}.get(freshness,30)
    try: age=max(0,(today-datetime.strptime(item.get('published','').split()[0],'%d/%m/%Y').date()).days)
    except Exception: age=window_days
    direct_publisher=0.5 if item.get('host')!='news.google.com' else 0
    # A news-feed date is useful for a news roundup. For arbitrary current
    # facts it must not outrank a publisher's own result just because it came
    # from the news feed; that had made tutorials crowd out release pages.
    news_feed_priority=1.5 if freshness and news_only and item.get('provider')=='Bing Notícias' else 0
    release_priority=0
    if asks_latest_version(query):
        path=urlparse(item.get('url','')).path.rstrip('/').casefold()
        title=str(item.get('title','')).casefold()
        if any(part in path.split('/') for part in ('release','releases','download','downloads','version','versions','tags')):
            release_priority+=1.2
        if any(word in title for word in ('release','releases','download','downloads','version','versions')):
            release_priority+=0.5
        if re.search(r'\b\d+\.\d+(?:\.\d+){0,2}\b',title):
            release_priority+=0.3
    return news_feed_priority+direct_publisher+release_priority+item.get('score',0)+0.2*max(0,1-age/window_days)


def _version_source_consensus(items):
    """Return a version shared by page text from at least two distinct hosts."""
    versions={}
    for item in items:
        text=str(item.get('page_excerpt',''))
        matches=set(re.findall(r'(?<![\w.])v?(\d+\.\d+(?:\.\d+){0,2})(?!\w|\.\d)',text,flags=re.I))
        for version in matches:
            versions.setdefault(version,set()).add(item.get('host',''))
    corroborated={version:hosts for version,hosts in versions.items() if len(hosts)>=2 and '' not in hosts}
    return max(corroborated.items(),key=lambda pair:(len(pair[1]),tuple(map(int,pair[0].split('.'))))) if corroborated else None

def _search_public_web_uncached(query,freshness=None,news_only=None,progress=None):
    def report(**event):
        if progress:
            try: progress(event)
            except Exception: pass
    query=' '.join(query.split())
    if not query or len(query)>180: raise ValueError('Consulta vazia ou longa demais.')
    search_window='' if freshness is False else (freshness or current_search_window(query))
    latest_version=asks_latest_version(query)
    # A release listing remains the current state even when its last release
    # was over 30 days ago. We verify it by reading two distinct live pages
    # which state the same version, rather than imposing an article-age window.
    freshness='' if latest_version else search_window
    query_variants=_search_query_variants(query,search_window)
    if news_only is None: news_only=news_search_intent(query)
    found=[]; seen=set(); failures=[]; provider_counts={}; rejected={'url':0,'atualidade':0,'relevancia':0,'duplicado':0}
    if news_only:
        freshness=freshness or '7d'
        try:
            news=search_google_news(query,freshness)
            found=_google_news_pipeline_items(news,query,freshness)
            seen={urlparse(item['url'])._replace(query='',fragment='').geturl().rstrip('/').casefold() for item in found}
            report(stage='searching',tasks=['Google Notícias','DuckDuckGo Lite','Bing RSS','Bing Notícias'],workers=1,completed=1,total=4,finished_task='Google Notícias',
                   sources=[{key:item.get(key,'') for key in ('provider','title','snippet','url','host','publisher','published')} for item in found[:4]])
        except Exception as exc:
            failures.append(f'Google Notícias: {type(exc).__name__}')
    # Use two genuinely different result interfaces. DDG's normal HTML endpoint
    # is frequently bot-challenged here, while Bing HTML often gives generic
    # navigational pages. DDG Lite and Bing RSS are lightweight alternatives.
    def fetch_provider(url,kind,timeout):
        headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36','Accept':'text/html,application/rss+xml,application/xml','Accept-Encoding':'gzip, deflate','Cache-Control':'no-cache, no-store, max-age=0','Pragma':'no-cache'}
        req=urllib.request.Request(url,headers=headers)
        with PUBLIC_OPENER.open(req,timeout=timeout) as response:
            public_http_url(response.geturl()); raw=response.read(1_500_001)
            if len(raw)>1_500_000: raise ValueError('Resposta do provedor excedeu o limite de tamanho.')
            raw=decode_http_body(raw,getattr(response,'headers',{}).get('Content-Encoding'),2_000_000)
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
    def collect_query(search_query,relevance_query,timeout,subagents=None):
        # Bing and Google News are fast, accurate, and do not trigger anti-bot 202 challenges.
        providers=(('Bing RSS','bing-rss'),)
        units=[]
        if subagents and len(subagents)>1:
            for agent in subagents:
                agent_search=_search_query_variants(agent.query,search_window)[0][0]
                units.append((agent.name,agent_search,agent.query))
        else:
            units=[('Pesquisa principal',search_query,relevance_query)]
        jobs_to_submit=[]
        for agent_name,agent_search,agent_relevance in units:
            jobs_to_submit.extend((agent_name,provider,kind,agent_search,agent_relevance)
                                  for provider,kind in providers)
            if news_only or latest_version:
                # Each explicit subtask searches the same topic in its own
                # right; only current news adds the regional companion query.
                topic_terms=_fresh_query_terms(agent_relevance)
                news_terms={min(_search_term_forms(term),key=len) for term in topic_terms}
                news_query=' '.join(sorted(news_terms)) or agent_search
                if latest_version:
                    news_query=f'{news_query} latest release'
                jobs_to_submit.append((agent_name,'Bing Notícias','bing-news',news_query,agent_relevance))
                if news_only and 'brasil' not in news_query.split() and not international_news_only(agent_relevance):
                    jobs_to_submit.append((agent_name+' · Brasil','Bing Notícias','bing-news',f'{news_query} Brasil',agent_relevance))
        tasks=len(jobs_to_submit)
        cpu_count=os.cpu_count() or 1
        try: load=os.getloadavg()[0]/cpu_count
        except (AttributeError,OSError): load=0
        try:
            with open('/proc/meminfo',encoding='ascii') as meminfo:
                available_ram=next(int(line.split()[1])*1024 for line in meminfo if line.startswith('MemAvailable:'))
        except (OSError,StopIteration,ValueError): available_ram=0
        workers=resource_worker_limit(tasks,load_per_cpu=load,available_ram=available_ram,cpu_count=cpu_count)
        multi_agent=bool(subagents and len(subagents)>1)
        agent_names=[agent.name for agent in subagents] if multi_agent else []
        task_names=agent_names or [provider if kind!='bing-news' else ('Bing Notícias · Brasil' if search_query_variant.endswith(' Brasil') else 'Bing Notícias')
                                   for _,provider,kind,search_query_variant,_ in jobs_to_submit]
        progress_total=len(agent_names) if multi_agent else tasks
        report(stage='searching',tasks=task_names,workers=workers,completed=0,total=progress_total)
        pending_by_agent={name:sum(1 for job in jobs_to_submit if job[0]==name or job[0].startswith(name+' ·')) for name in agent_names}
        finished_agents=set()
        started_at={name:time.monotonic() for name in agent_names}
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures={}
            for agent_name,provider,kind,query_for_provider,agent_relevance in jobs_to_submit:
                if kind=='ddg': url='https://lite.duckduckgo.com/lite/?'+urlencode({'q':query_for_provider,'kl':'br-pt'})
                elif kind=='bing-rss': url='https://www.bing.com/search?'+urlencode({'q':query_for_provider,'format':'rss','setlang':'pt-br'})
                if kind=='bing-news': future=pool.submit(search_bing_news,query_for_provider,timeout)
                else: future=pool.submit(fetch_provider,url,kind,timeout)
                futures[future]=(agent_name,provider,kind,agent_relevance)
            for completed,future in enumerate(concurrent.futures.as_completed(futures),1):
                agent_name,provider,kind,agent_relevance=futures[future]
                task_name=agent_name if multi_agent else (provider if kind!='bing-news' else ('Bing Notícias · Brasil' if agent_name.endswith(' · Brasil') else provider))
                stats=provider_counts.setdefault(provider,{'extraidos':0,'relevantes':0})
                try: rows=future.result()
                except Exception as exc:
                    failures.append(f'{provider}: {type(exc).__name__}')
                    rows=[]
                stats['extraidos']+=len(rows)
                provider_found=[]
                for row in rows:
                    href,title,snippet=row[:3]; published=row[3] if len(row)>3 else ''
                    publisher=row[4] if len(row)>4 else ''
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
                    # Bing News carries a full publication timestamp. Its
                    # precise elapsed-time check below supersedes the generic
                    # calendar-day detector, which would reject yesterday's
                    # still-within-24-hours stories.
                    # A Bing search RSS timestamp is a search-result field, not
                    # reliable evidence of the publisher's publication date.
                    # Only Bing News items expose a source publication date.
                    stale_feed_date=(published and kind=='bing-news' and _has_stale_source_date('published '+published,freshness))
                    if freshness and (_has_expired_deadline(title+' '+snippet) or
                            _has_stale_source_date(title+' '+snippet,freshness) or
                            _has_stale_url_date(href,freshness) or
                            stale_feed_date):
                        rejected['atualidade']+=1; continue
                    # The alternate query removes request phrasing, not subject terms.
                    relevance=_search_relevance(agent_relevance,title,snippet)
                    if relevance<=0: rejected['relevancia']+=1; continue
                    stats['relevantes']+=1
                    key=urlparse(href)._replace(query='',fragment='').geturl().rstrip('/').casefold()
                    if key in seen: rejected['duplicado']+=1; continue
                    seen.add(key)
                    host=(urlparse(href).hostname or '').removeprefix('www.')
                    accepted={'provider':provider,'title':title,'snippet':snippet,'url':href,'host':host,
                        'publisher':publisher,'published':published if kind=='bing-news' else '',
                        'search_result_published':published if kind=='bing-rss' else '',
                        'feed_published':kind=='bing-news','score':relevance}
                    found.append(accepted); provider_found.append(accepted)
                update={'stage':'searching','tasks':task_names,'workers':workers,
                        'completed':completed if not multi_agent else len(finished_agents),'total':progress_total,
                        'sources':[{key:item.get(key,'') for key in ('provider','title','snippet','url','host','publisher','published')} for item in provider_found[:4]]}
                if multi_agent:
                    if agent_name in pending_by_agent:
                        pending_by_agent[agent_name]-=1
                        if pending_by_agent[agent_name]<=0:
                            finished_agents.add(agent_name)
                            update.update(completed=len(finished_agents),total=len(agent_names),finished_task=agent_name,
                                          duration_ms=int((time.monotonic()-started_at[agent_name])*1000))
                    else:
                        parent=agent_name.removesuffix(' · Brasil')
                        if parent in pending_by_agent:
                            pending_by_agent[parent]-=1
                            if pending_by_agent[parent]<=0:
                                finished_agents.add(parent)
                                update.update(completed=len(finished_agents),total=len(agent_names),finished_task=parent,
                                              duration_ms=int((time.monotonic()-started_at[parent])*1000))
                else:
                    update.update(completed=completed,total=tasks,finished_task=task_name)
                report(**update)
    subagents=plan_research_subagents(query)
    for attempt,(search_query,relevance_query) in enumerate(query_variants):
        collect_query(search_query,relevance_query,3.5 if attempt==0 else 1.8,
                      subagents if attempt==0 and len(subagents)>1 else None)
        # Google News RSS links may remain Google wrapper pages that our safe
        # HTTP reader cannot extract. They must not suppress the compact-query
        # fallback before we have any directly readable publisher candidates.
        readable_candidates=[item for item in found if item.get('host')!='news.google.com']
        enough=(_independent_recent_source_count(readable_candidates,freshness)>=2) if freshness else bool(readable_candidates)
        if enough: break
    report(stage='validating',counts={name:dict(value) for name,value in provider_counts.items()},rejected=dict(rejected),accepted=len(found))
    if freshness and not news_only and _independent_recent_source_count(found,freshness)<2:
        # Current factual questions also benefit from dated publisher URLs in
        # the news feed, even when the user did not ask for a news roundup.
        compact=query_variants[-1][1]
        terms=_fresh_query_terms(compact)
        news_terms={min(_search_term_forms(term),key=len) for term in terms}
        news_query=' '.join(sorted(news_terms)) or compact
        news_queries=[news_query]
        if 'brasil' not in news_query.split() and not international_news_only(query):
            news_queries.append(f'{news_query} Brasil')
        task_names=['Bing Notícias · Brasil' if variant.endswith(' Brasil') else 'Bing Notícias' for variant in news_queries]
        workers=resource_worker_limit(len(news_queries))
        report(stage='searching',tasks=task_names,workers=workers,completed=0,total=len(news_queries))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(search_bing_news,variant,2.5):task_name for variant,task_name in zip(news_queries,task_names)}
            for completed,future in enumerate(concurrent.futures.as_completed(futures),1):
                task_name=futures[future]
                try: rows=future.result()
                except Exception as exc:
                    failures.append(f'Bing Notícias: {type(exc).__name__}')
                    report(stage='searching',tasks=task_names,workers=workers,completed=completed,total=len(news_queries),finished_task=task_name,error=type(exc).__name__)
                    continue
                provider_counts.setdefault('Bing Notícias',{'extraidos':0,'relevantes':0})['extraidos']+=len(rows)
                for href,title,snippet,published,publisher in rows:
                    try: public_http_url(href)
                    except Exception: rejected['url']+=1; continue
                    if not _publication_within_window(published,freshness):
                        rejected['atualidade']+=1; continue
                    relevance=_search_relevance(query,title,snippet)
                    if relevance<=0:
                        rejected['relevancia']+=1; continue
                    key=urlparse(href)._replace(query='',fragment='').geturl().rstrip('/').casefold()
                    if key in seen:
                        rejected['duplicado']+=1; continue
                    seen.add(key)
                    provider_counts['Bing Notícias']['relevantes']+=1
                    host=(urlparse(href).hostname or '').removeprefix('www.')
                    found.append({'provider':'Bing Notícias','title':title,'snippet':snippet,'url':href,'host':host,
                        'publisher':publisher,'published':published,'feed_published':True,'score':relevance})
                report(stage='searching',tasks=task_names,workers=workers,completed=completed,total=len(news_queries),finished_task=task_name,
                       sources=[{key:item.get(key,'') for key in ('provider','title','snippet','url','host','publisher','published')} for item in found if item.get('provider')=='Bing Notícias'][:4])
    window_days={'1d':1,'7d':7,'30d':30}.get(freshness,30)
    if freshness and not news_only and (not found or _independent_recent_source_count(found,freshness)<2):
        try:
            recent=search_google_news(query,freshness)
            for item in _google_news_pipeline_items(recent,query,freshness):
                key=urlparse(item['url'])._replace(query='',fragment='').geturl().rstrip('/').casefold()
                if key not in seen:
                    seen.add(key); found.append(item)
            report(stage='validating',counts={name:dict(value) for name,value in provider_counts.items()},rejected=dict(rejected),accepted=len(found),
                   sources=[{key:item.get(key,'') for key in ('provider','title','snippet','url','host','publisher','published')} for item in found[:4]])
        except Exception: pass
    today=datetime.now().astimezone().date()
    found.sort(key=lambda item:_candidate_rank(item,freshness,news_only,today,window_days,query),reverse=True)
    if not found:
        counts='; '.join(f'{name}: {stats["extraidos"]} extraídos, {stats["relevantes"]} relacionados' for name,stats in provider_counts.items()) or 'nenhum resultado extraído'
        drops=', '.join(f'{name} {count}' for name,count in rejected.items() if count)
        reason=(' provedores indisponíveis: '+'; '.join(dict.fromkeys(failures))+'.') if failures else ''
        filtered=(' descartes por '+drops+'.') if drops else ''
        return f'Não confirmei fontes para essa pergunta. Resultados de busca ({counts}).{filtered}{reason} Não vou completar por memória.'
    # Keep a small reserve of independent candidates. Some publishers block the
    # reader or expose no text; a failed first choice must not hide the next
    # current source. At most two page requests run concurrently.
    candidates=[]; selected_sources=set()
    for item in found:
        if freshness and item['published'] and not _publication_within_window(item['published'],freshness): continue
        if freshness or latest_version:
            source=(item.get('publisher') if item.get('feed_published') else item.get('host')) or item.get('url')
            source=source.casefold()
            if source in selected_sources: continue
            selected_sources.add(source)
        candidates.append(item)
        if len(candidates)>=(6 if freshness or latest_version else 2): break
    if not candidates:
        if freshness: return 'Não encontrei páginas com data recente verificável para confirmar esse fato. Não vou apresentar um resultado sem data como atual.'
        candidates=found[:2]
    report(stage='reading',tasks=[item.get('title','Fonte')[:72] for item in candidates[:6]],workers=2,completed=0,total=min(6,len(candidates)),sources=[{key:item.get(key,'') for key in ('provider','title','snippet','url','host','publisher','published')} for item in candidates[:4]])
    attempted=[]
    page_rejected={'fora_da_janela':0,'data_nao_verificada':0,'sem_conteudo':0}
    def read_page_batch(batch):
        # Snappy reading with 1.2s timeout so the assistant responds immediately
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3,len(batch))) as pool:
            jobs=[(item,pool.submit(_search_page_excerpt,item['url'],query,1.2)) for item in batch]
            for item,future in jobs:
                try: excerpt,published=future.result(timeout=1.4)
                except Exception: excerpt,published='',''
                if published:
                    item['published']=published
                    item['page_date_verified']=True
                    if freshness and not _publication_within_window(published,freshness):
                        item['stale_page']=True
                        page_rejected['fora_da_janela']+=1
                        attempted.append(item)
                        continue
                elif item.get('feed_published'):
                    if excerpt: item['feed_date_accepted']=True
                    else:
                        item['unverified_page_date']=True
                        page_rejected['data_nao_verificada']+=1
                elif freshness:
                    item['unverified_page_date']=True
                    page_rejected['data_nao_verificada']+=1
                if item.get('provider')=='Google Notícias' and not excerpt:
                    item['page_unavailable']=True
                if excerpt:
                    item['page_excerpt']=excerpt
                    item['snippet']=((item['snippet']+' | Trecho da página aberta agora: ') if item['snippet'] else 'Trecho da página aberta agora: ')+excerpt
                    item['page_opened']=True
                elif not item.get('stale_page'):
                    page_rejected['sem_conteudo']+=1
                attempted.append(item)
    def usable_pages():
        return [item for item in attempted if item.get('page_opened') and not item.get('stale_page')
            and not item.get('unverified_page_date') and not item.get('page_unavailable')
            and (not item.get('feed_published') or item.get('page_date_verified') or item.get('feed_date_accepted'))]
    next_candidate=0
    # Process at most 1 fast batch of 3 candidate pages instead of chaining multiple slow batches
    while next_candidate<min(3,len(candidates)):
        batch=candidates[next_candidate:next_candidate+3]
        next_candidate+=len(batch)
        read_page_batch(batch)
        report(stage='reading',tasks=[item.get('title','Fonte')[:72] for item in candidates[:6]],workers=3,completed=len(attempted),total=min(3,len(candidates)),sources=[{key:item.get(key,'') for key in ('provider','title','snippet','url','host','publisher','published')} for item in attempted[:4]],page_rejected=dict(page_rejected))
        if latest_version:
            if _version_source_consensus(usable_pages()): break
        elif usable_pages():
            break
    # Fallback to candidates if usable_pages is empty because of overly strict freshness date parsing
    if (freshness or latest_version):
        found = usable_pages()
        if not found and attempted:
            # Use attempted pages that have excerpts regardless of date stamps
            found = [item for item in attempted if item.get('page_opened')]
        if not found and candidates:
            # If reading pages failed, fall back directly to search engine result snippets!
            found = candidates[:4]
    elif not found and candidates:
        found = candidates[:4]
    if not found:
        return 'Não encontrei resultados suficientes para responder a essa pergunta.'
    output=[]
    checked=datetime.now().astimezone().strftime('%d/%m/%Y %H:%M %Z')
    for item in found[:8]:
        label=item['title'][:180]
        if item['published']:
            publisher=item.get('publisher') or item.get('host') or item['provider']
            if item.get('feed_date_accepted'): publisher='Feed RSS: '+publisher
            label+=f' [{publisher} · {item["published"]}]'
        elif latest_version:
            label+=f' [{item.get("host") or item["provider"]} · página consultada em {checked}]'
        snippet_limit=1400 if latest_version else 350
        line=label+(f' :: {item["snippet"][:snippet_limit]}' if item['snippet'] else '')+f' — {item["url"]}'
        output.append(line)
    sources=', '.join(dict.fromkeys(item['provider'] for item in found))
    verification=' Versões iguais foram conferidas em páginas ao vivo de hosts distintos.' if latest_version else ' Relevância e atualidade da página precisam ser conferidas antes de afirmar fatos:'
    return f'Resultados combinados de {sources}; consulta executada em {checked}.{verification}\n'+'\n'.join(output)

_SEARCH_CACHE={}

_SEARCH_CACHE_LOCK=threading.Lock()

_SEARCH_CACHE_TTL=90

def search_public_web(query,freshness=None,news_only=None,progress=None):
    """Short cache for repeated queries; volatile evidence expires after 90 seconds."""
    key=(normalize_words(query),freshness,news_only)
    now=time.monotonic()
    with _SEARCH_CACHE_LOCK:
        cached=_SEARCH_CACHE.get(key)
        if cached and now-cached[0]<_SEARCH_CACHE_TTL:
            if progress:
                try: progress({'stage':'searching','tasks':['Cache local'], 'workers':0,'completed':1,'total':1,'cache_hit':True})
                except Exception: pass
            return cached[1]
        for old_key,(created,_) in list(_SEARCH_CACHE.items()):
            if now-created>=_SEARCH_CACHE_TTL: _SEARCH_CACHE.pop(old_key,None)
    result=(_search_public_web_uncached(query,freshness,news_only) if progress is None else
            _search_public_web_uncached(query,freshness,news_only,progress))
    if not result.startswith(('Não encontrei','Não consegui','As fontes encontradas','Os resultados que pareciam')):
        with _SEARCH_CACHE_LOCK:
            if len(_SEARCH_CACHE)>=48: _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
            _SEARCH_CACHE[key]=(time.monotonic(),result)
    return result
