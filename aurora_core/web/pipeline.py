from __future__ import annotations

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, urlencode, parse_qs, urljoin
import base64, concurrent.futures, html, re, threading, time, urllib.error, urllib.request, unicodedata
import math
import xml.etree.ElementTree as ET
from ..system.files import normalize_words
from .parsers import DuckDuckGoLiteResults, PageMetadata, PageText
from .security import PUBLIC_OPENER, public_http_url

def search_intent(prompt):
    plain=normalize_words(prompt)
    if re.search(r'\b(arquivo|arquivos|pasta|pastas|documento local)\b',plain): return ''
    verbs=r'(?:pesquis(?:ar|a|e|ada|ado)|busc(?:ar|a|e)|procur(?:ar|a|e)|consult(?:ar|a|e)|encontr(?:ar|a|e)|ach(?:ar|e)|descobr(?:ir|a|e)|verifi(?:car|que|ca)|investig(?:ar|ue|uem|a)|chequ(?:ar|e)|research)'
    if not re.search(r'\b'+verbs+r'\b',plain): return ''
    query=str(prompt).strip()
    query=re.sub(r'^\s*(?:ei[, ]+)?aurora[, ]*','',query,flags=re.I)
    preamble=r'(?:voce pode|você pode|pode|consegue|quero que|eu queria que|tem como|da para|dá para|por favor|por gentileza|faz|faca|faça|fazer|realize|realiza|me traga|me de|me dê)'
    query=re.sub(r'^\s*(?:(?:'+preamble+r')\s+)*(?:(?:uma|um)\s+)?(?:'+verbs+r')\s*','',query,flags=re.I)
    query=re.sub(r'^(?:aí|ai|pra mim|para mim)\s+','',query,flags=re.I)
    query=re.sub(r'^(?:(?:na web|na internet|no google|sobre|a respeito de|por|para|acerca de)\s+)+','',query,flags=re.I)
    query=re.sub(r'^(?:os|as|o|a|um|uma)\s+','',query,flags=re.I)
    query=re.sub(r'\s+(?:na web|na internet|no google|por favor)\s*[.!?]*$','',query,flags=re.I).strip(' \t,.:;!?')
    return query[:180]

def _is_historical_query(text):
    plain=unicodedata.normalize('NFKD',str(text)).encode('ascii','ignore').decode('ascii').lower()
    if re.search(r'\b(hoje|agora|neste momento|ao vivo|tempo real|today|now|right now)\b',plain): return False
    this_year=datetime.now().astimezone().year
    if any(int(value)<this_year for value in re.findall(r'\b(?:19|20)\d{2}\b',plain)): return True
    currentish=bool(re.search(r'\b(atual|atualmente|atualizada|atualizado|latest|current|mais recente|ultima versao|versao atual|current price)\b',plain))
    past_tense=bool(re.search(r'\b(foi|foram|era|eram|was|were|did|used to|custava|custavam|valia|valiam|historico|historical|na epoca|at the time|antes|previously)\b',plain))
    return past_tense and not currentish

def current_search_window(text):
    """Map explicit time-sensitivity language to a short freshness window."""
    plain=unicodedata.normalize('NFKD',str(text)).encode('ascii','ignore').decode('ascii').lower()
    if _is_historical_query(plain): return ''
    if re.search(r'\b(hoje|agora|neste momento|neste instante|ao vivo|tempo real|ultimas 24 horas|right now|today|live)\b',plain): return '1d'
    if re.search(r'\b(ultima hora|ultimas noticias|noticias recentes|noticia recente|esta semana|nesta semana|ultimos dias|ultima semana|breaking news|news about)\b',plain): return '7d'
    if re.search(r'\b(atual|atualmente|atualizado|atualizada|mais recente|recentemente|recente|ultimo|ultima|latest|current|newest|updated|how much|quanto custa|quanto custam|quanto sai|quanto vale|cost|price|custo|preco atual|valor atual)\b',plain): return '30d'
    return ''

def news_search_intent(text):
    plain=normalize_words(text)
    return bool(re.search(r'\b(noticia|noticias|news|manchetes|o que aconteceu|ultimos acontecimentos|breaking news)\b',plain))

def international_news_only(text):
    plain=normalize_words(text)
    asks_international=bool(re.search(r'\b(internacional|internacionais|global|globais|mundial|mundo)\b',plain))
    asks_national=bool(re.search(r'\b(nacional|nacionais|brasil|brasileiras|brasileiros)\b',plain))
    return asks_international and not asks_national

def research_request_intent(text):
    """Recognize research formats even when they are phrased as a request, not a question."""
    plain=normalize_words(text)
    if news_search_intent(plain): return True
    return guided_learning_intent(plain)

def guided_learning_intent(text):
    plain=normalize_words(text)
    return bool(re.search(r'\b(tutorial|tutoriais|guia|guias|passo a passo|instrucoes|manual|dicas para|estrategia para|como jogar|como instalar|como configurar|como montar|me ensina|ensina a|quero aprender|aprenda a)\b',plain))

def requested_response_language(text):
    """Return a temporary response language from an explicit spoken preference."""
    plain=normalize_words(text)
    command=bool(re.search(r'\b(fale|fala|falar|responda|responde|converse|conversa|muda|mude|troca|troque|volta|volte|voltar|retorna|retorne|retornar|passe a falar)\b',plain))
    if not command: return None
    if re.search(r'\b(portugues|pt br|ptbr|brasileiro)\b',plain): return 'Português brasileiro'
    match=re.search(r'\b(?:fale|fala|falar|responda|responde|converse|conversa|muda|mude|troca|troque|volta|volte|voltar|retorna|retorne|retornar|passe a falar)\s+(?:comigo\s+)?(?:em\s+|para\s+|pra\s+|pro\s+|no idioma\s+|na lingua\s+)?([\wÀ-ÿ-]+)',str(text),re.I)
    if not match: return None
    language=match.group(1).strip('- ').lower()
    aliases={'ingles':'English','english':'English','espanhol':'Spanish','spanish':'Spanish','frances':'French','french':'French','italiano':'Italian','italian':'Italian','alemao':'German','german':'German','japones':'Japanese','japanese':'Japanese','mandarim':'Chinese','chines':'Chinese','chinese':'Chinese','coreano':'Korean','korean':'Korean','russo':'Russian','russian':'Russian','arabe':'Arabic','arabic':'Arabic'}
    key=unicodedata.normalize('NFKD',language).encode('ascii','ignore').decode('ascii')
    return aliases.get(key,match.group(1).strip().capitalize())

def current_web_query(query,window=''):
    """Add the live year to time-sensitive queries without changing their subject."""
    if not window: return query
    year=str(datetime.now().astimezone().year)
    temporal=r'\b(?:current(?:ly)?|latest|newest|recent(?:ly)?|updated|today|now|atual(?:mente)?|recentemente|atualizad[oa]s?|ultim[oa]s?|hoje|agora)\b|\bmais\s+recente\b'
    focused=' '.join(re.sub(temporal,' ',str(query),flags=re.I).split()) or str(query).strip()
    return focused if re.search(r'\b'+year+r'\b',focused) else f'{focused} {year}'[:220]

def factual_web_intent(prompt):
    """Recognize ordinary factual questions that need sourced web information."""
    if re.search(r'\b(arquivo|arquivos|pasta|pastas|documento local|lembra|lembro|minha opiniao|o que acha|o que voce acha|crie|escreva|invente|resuma este texto|calcule)\b',prompt,re.I):
        return False
    plain=unicodedata.normalize('NFKD',str(prompt)).encode('ascii','ignore').decode('ascii').lower()
    if re.search(r'\b(como voce esta|como voce ta|como voce se sente|como voce vai|como vai voce|como foi (?:o )?(?:seu|sua)|tudo bem|quem e voce|o que voce e|qual (?:e )?seu nome|qual sua opiniao|minha opiniao|na sua opiniao|o que acha|o que voce acha|o que voce faria|o que eu faco|o que devo fazer|me ajuda a pensar|me aconselha|me da um conselho|queria conversar|vamos conversar|conversa comigo|desabafar|me sinto)\b',plain):
        return False
    if research_request_intent(plain): return True
    return bool(re.search(r'^\s*(?:aurora[, ]*)?(?:qual\b|quais\b|quem\b|quando\b|onde\b|quanto\b|como\b|por que\b|porque\b|o que\b)',plain) or re.search(
        r'\b(me fale sobre|me explica|explique|compare|diferenca entre|informacoes sobre|tell me about|how much|what (?:was|were|is|are)|who (?:was|is)|when did|where is|how does)\b',plain))

def local_datetime_answer(prompt,now=None):
    """Answer unambiguous local clock/calendar questions without a web request."""
    plain=normalize_words(prompt)
    now=now or datetime.now().astimezone()
    time_intent=bool(re.search(r'\b(?:que horas sao|que hora e|qual e a hora|qual e o horario(?: atual)?|horario atual|hora atual|horas agora|que horas agora|sao que horas|me (?:diz|diga|fala|fale) (?:que horas sao|a hora|o horario(?: atual)?))(?: agora| aqui| ai| exatamente| por favor)?[?.!]*$',plain))
    date_intent=bool(re.search(r'\b(?:que dia e hoje|que dia estamos(?: hoje)?|qual (?:e )?a data(?: de hoje)?|data de hoje|que data e hoje|me (?:diz|diga|fala|fale) (?:a data|que dia e hoje))(?: por favor)?[?.!]*$',plain))
    # A named place means the user asked for another timezone; let the assistant
    # resolve that explicitly instead of silently substituting this computer's time.
    if (time_intent or date_intent) and re.search(r'\b(?:em|na|no)\s+[a-z]{3,}',plain):
        return None
    if time_intent:
        hour,minute=now.hour,now.minute
        if hour==0 and minute==0: return 'Agora é meia-noite.'
        if hour==12 and minute==0: return 'Agora é meio-dia.'
        if minute==0: return f'Agora são {hour} horas.'
        if hour==1: return f'Agora é 1 hora e {minute:02d} minutos.'
        return f'Agora são {hour} horas e {minute:02d} minutos.'
    if date_intent:
        weekdays=('segunda-feira','terça-feira','quarta-feira','quinta-feira','sexta-feira','sábado','domingo')
        months=('janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro')
        return f'Hoje é {weekdays[now.weekday()]}, {now.day} de {months[now.month-1]}.'
    return None

def contextual_followup(prompt):
    plain=normalize_words(prompt)
    return bool(re.search(r'\b(isso|disso|nisso|esse|essa|esses|essas|ele|ela|eles|elas|dele|dela|a primeira fonte|o primeiro resultado|a segunda fonte|o segundo resultado|a terceira fonte|o terceiro resultado|a fonte|essa fonte|esse resultado|essa noticia|essa resposta|como assim|mais detalhes|mais informacoes|mais sobre isso|explica melhor|continua|por que ele|e sobre isso|e a primeira|e o primeiro)\b',plain))

def contextual_source_request(prompt):
    plain=normalize_words(prompt)
    return bool(re.search(r'\b(abre|abrir|mostra|mostrar|leia|ler|acesse|acessar)\b.*\b(primeira|primeiro|segunda|segundo|terceira|terceiro|fonte|link|resultado|noticia|artigo)\b',plain))

def _fresh_query_terms(query):
    plain=unicodedata.normalize('NFKD',str(query)).encode('ascii','ignore').decode('ascii').lower()
    ignored={'a','as','o','os','um','uma','uns','umas','de','do','da','dos','das','em','no','na','nos','nas','com','por','para','pra','e','ou','que','qual','quais','quem','como','onde','quando','quanto','esta','porque','sobre','pesquise','pesquisar','busque','buscar','procure','procurar','me','diga','mostre','informe','hoje','agora','atual','atualmente','atualizada','atualizado','recente','recentes','ultima','ultimas','ultimos','ultimo','ao','vivo','news','latest','current','breaking','today','now','recent','search','find','about','what','whats','the','for','and','with','from','is','are','was','were','be','been','being','do','does','did','have','has','had','can','could','would','should','will','who','when','where','why','how','much','many','please','tell','explain','explanation','describe','compare','comparison','difference','between','mean','means','meaning','work','works','working','function','of'}
    terms={word for word in re.findall(r'[a-z0-9]+',plain) if (len(word)>2 or word.isdigit()) and word not in ignored}
    format_words={'noticia','noticias','novidades','ultimas'}
    subject_terms=terms-format_words
    return subject_terms or terms

def _search_relevance(query,title,snippet=''):
    """Reject generic engine pages that only share one incidental query word."""
    wanted=_fresh_query_terms(query)
    if not wanted: return 1.0
    raw_unicode=(str(title)+' '+str(snippet)).lower()
    raw=unicodedata.normalize('NFKD',raw_unicode).encode('ascii','ignore').decode('ascii').lower()
    text=raw
    found=set(re.findall(r'[a-z0-9]+',text))
    # Exact requested numbers, version components, and years are hard anchors.
    numeric={term for term in wanted if term.isdigit()}
    if numeric and not numeric.issubset(found): return 0.0
    overlap=wanted & found
    required=max(1,math.ceil(len(wanted)*0.75))
    if len(overlap)<required: return 0.0
    return len(overlap)/max(1,len(wanted))

def _search_query_variants(query,freshness=''):
    """Keep the spoken query first, then try a compact subject-focused form."""
    original=' '.join(str(query).split())
    cleaned=re.sub(
        r'\b(?:por favor|poderia|gostaria de saber|quero saber|me diga|me fale|me mostra|mostra para mim|'
        r'pesquise|pesquisar|busque|buscar|procure|procurar|encontre|encontrar|'
        r'quais sao|qual e|quem e|quando foi|onde fica|o que e|o que voce sabe sobre|como funciona|'
        r'tutorial|tutoriais|guias?|passo a passo|instrucoes|manuais?|como|'
        r'jogar|jogue|play|playing|instalar|install|configurar|configure|fazer|make|montar|build|usar|use|'
        r'a|as|o|os|um|uma|uns|umas|de|do|da|dos|das|em|no|na|nos|nas|com|por|para|pra|e|ou|que)\b',
        ' ',original,flags=re.I)
    cleaned=' '.join(cleaned.split()).strip(' ,.:;!?')
    variants=[(current_web_query(original,freshness),original)]
    if cleaned and _fresh_query_terms(cleaned) and _fresh_query_terms(cleaned)!=_fresh_query_terms(original):
        variants.append((current_web_query(cleaned,freshness),cleaned))
    return variants

def search_failure_summary(output,query):
    """Preserve the search pipeline's concrete failure reason for the user."""
    first=next((line.strip() for line in str(output or '').splitlines() if line.strip()),'')
    known=('A busca não conseguiu consultar','Os provedores responderam','Não encontrei páginas',
           'Não encontrei publicações','As notícias encontradas','Os resultados que pareciam',
           'As fontes encontradas','Não encontrei resultados','Não confirmei fontes')
    if first.startswith(known): return first
    return news_unconfirmed_message() if news_search_intent(query) else 'Não consegui confirmar uma resposta relevante e atual nos resultados da busca.'

def _news_result_relevance(query,title,snippet=''):
    """Require a topical match; unqualified news requests need roundup headlines."""
    if not news_search_intent(query): return _search_relevance(query,title,snippet)
    wanted=_fresh_query_terms(query)-{'noticia','noticias','novidades','ultimas','nacional','nacionais','internacional','internacionais','global','globais','mundial','mundo'}
    if wanted: return _search_relevance(' '.join(sorted(wanted)),title,snippet)
    text=normalize_words(str(title)+' '+str(snippet))
    if international_news_only(query):
        return 1.0 if re.search(r'\b(international|global|world|worldwide|internacional|internacionais|global|globais|mundial|mundo)\b',text) else 0.0
    roundup=r'\b(principais noticias|resumo (?:das? )?(?:principais )?noticias|noticias (?:do mundo|do dia)|destaques (?:do dia|das noticias))\b'
    return 1.0 if re.search(roundup,text) else 0.0

def _result_query_relevance(query,title,snippet=''):
    """Apply the same subject-focused relevance check after search parsing."""
    if news_search_intent(query): return _news_result_relevance(query,title,snippet)
    return _search_relevance(_search_query_variants(query)[-1][1],title,snippet)

def news_unconfirmed_message():
    return 'Não consegui confirmar notícias recentes sobre esse assunto.'

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
        published=_parse_publication_date(value).date()
        now=(now or datetime.now().astimezone()).date()
        days={'1d':1,'7d':7,'30d':30}.get(window,30)
        return 0 <= (now-published).days <= days
    except Exception: return False

def _parse_publication_date(value):
    """Parse machine and localized publication dates emitted by common feeds."""
    raw=' '.join(str(value or '').strip().split())
    for parser in (parsedate_to_datetime,datetime.fromisoformat):
        try:
            parsed=parser(raw.replace('Z','+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        except Exception: pass
    try: return datetime.strptime(raw.split()[0],'%d/%m/%Y').replace(tzinfo=datetime.now().astimezone().tzinfo)
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
        match=re.search(r'\s*\[([^\]]+?)\s*[·|]\s*(\d{2}/\d{2}/\d{4})(?:\s+\d{2}:\d{2})?\]$',label)
        if not match: continue
        publisher,published=match.groups(); title=label[:match.start()].strip()
        try: public_http_url(url)
        except Exception: continue
        score=_search_relevance(query,title,snippet)
        if score<=0 or not _publication_within_window(published,window): continue
        rows.append({'provider':'Google Notícias','title':title,'snippet':snippet,'url':url,
            'host':'news.google.com','publisher':publisher,'published':published,
            'feed_published':True,'score':score})
    return rows

def web_fetch(url):
    public_http_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':'Aurora-Local/0.1 (public-page reader)','Accept':'text/html,application/xhtml+xml'})
    with PUBLIC_OPENER.open(req,timeout=18) as response:
        final=response.geturl(); public_http_url(final)
        content_type=response.headers.get_content_type()
        if content_type not in ('text/html','application/xhtml+xml'): raise ValueError('O endereço não retornou uma página HTML.')
        raw=response.read(2_000_001)
    if len(raw)>2_000_000: raw=raw[:2_000_000]
    charset='utf-8'
    try: charset=response.headers.get_content_charset() or charset
    except Exception: pass
    parser=PageText(); parser.feed(raw.decode(charset,errors='replace'))
    title=' '.join(parser.title).strip(); text=' '.join(parser.text).strip()
    if not text: raise ValueError('Não encontrei texto legível na página.')
    return f'TÍTULO: {title[:200]}\nURL: {final}\nTEXTO DA PÁGINA (conteúdo não confiável): {text[:3500]}'

def read_public_page(url): return web_fetch(url)

def _search_page_excerpt(url,query,timeout=2.0):
    """Fetch a small slice of a public result page to ground the answer in its own text."""
    public_http_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':'Aurora-Local/0.5 (public factual search)','Accept':'text/html,application/xhtml+xml','Cache-Control':'no-cache, no-store, max-age=0'})
    with PUBLIC_OPENER.open(req,timeout=timeout) as response:
        final=response.geturl(); public_http_url(final)
        if response.headers.get_content_type() not in ('text/html','application/xhtml+xml'): return ''
        raw=response.read(700_000)
    html_text=raw.decode('utf-8',errors='replace')
    metadata=PageMetadata(); metadata.feed(html_text)
    dates=[]
    for _,value in metadata.dates:
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
            dates.append(parsed.astimezone())
        except Exception:
            for fmt in ('%Y-%m-%d','%Y/%m/%d','%d/%m/%Y'):
                try:
                    parsed=datetime.strptime(value[:10],fmt).replace(tzinfo=datetime.now().astimezone().tzinfo)
                    dates.append(parsed.astimezone()); break
                except Exception: pass
    published=max(dates).strftime('%d/%m/%Y') if dates else ''
    parser=PageText(); parser.feed(raw.decode('utf-8',errors='replace'))
    body=' '.join(' '.join(parser.text).split())
    if len(body)<120: return ''
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

def _search_public_web_uncached(query,freshness=None,news_only=None):
    query=' '.join(query.split())
    if not query or len(query)>180: raise ValueError('Consulta vazia ou longa demais.')
    freshness='' if freshness is False else (freshness or current_search_window(query))
    if news_only is None: news_only=news_search_intent(query)
    if news_only:
        news=search_google_news(query,freshness or '7d')
        return _enrich_news_results(news,query,freshness or '7d')
    found=[]; seen=set(); failures=[]; provider_counts={}; rejected={'url':0,'atualidade':0,'relevancia':0,'duplicado':0}
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as pool:
            jobs=[(provider,kind,pool.submit(fetch_provider,url,kind,timeout)) for provider,url,kind in providers]
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
    if freshness and (not found or _independent_recent_source_count(found,freshness)<2):
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
    selected=[]
    for item in found:
        if freshness and not _publication_within_window(item['published'],freshness): continue
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
                item['unverified_page_date']=True
            if item.get('provider')=='Google Notícias' and not excerpt:
                item['page_unavailable']=True
            if excerpt:
                item['snippet']=((item['snippet']+' | Trecho da página aberta agora: ') if item['snippet'] else 'Trecho da página aberta agora: ')+excerpt
                item['page_opened']=True
    if freshness: found=[item for item in found if not item.get('stale_page') and not item.get('unverified_page_date') and not item.get('page_unavailable') and (not item.get('feed_published') or item.get('page_date_verified'))]
    if not found:
        return 'Os resultados que pareciam atuais apontam para páginas antigas. Não consegui confirmar o dado em uma página atual, então não vou repetir esse conteúdo como fato de agora.'
    if freshness:
        if _independent_recent_source_count(found,freshness)<2:
            return 'As fontes encontradas não bastam para confirmar esse fato atual: preciso de duas publicações independentes, recentes e datadas. Não vou completar a resposta por memória.'
    output=[]
    for item in found[:8]:
        label=item['title'][:180]
        if item['published']: label+=f' [{item["provider"]} · {item["published"]}]'
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
