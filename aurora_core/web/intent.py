# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from ..system.files import normalize_words
from ..system.calculator import calculate_local_expression
from datetime import datetime
import re, unicodedata
import math

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
    currentish=bool(re.search(r'\b(atual|atualmente|atualizada|atualizado|latest|current|mais recentes?|ultima versao|versao atual|current price)\b',plain))
    past_tense=bool(re.search(r'\b(foi|foram|era|eram|was|were|did|used to|custava|custavam|valia|valiam|historico|historical|na epoca|at the time|antes|previously)\b',plain))
    return past_tense and not currentish

def current_search_window(text):
    """Map explicit time-sensitivity language to a short freshness window."""
    plain=unicodedata.normalize('NFKD',str(text)).encode('ascii','ignore').decode('ascii').lower()
    if _is_historical_query(plain): return ''
    # Present-tense identity questions with a definite role/entity ask for the
    # current state even when the speaker omits "atual" or "current".
    if re.search(r'^\s*(?:aurora[, ]*)?(?:quem e (?:o|a)|who is (?:the|a|an))\b',plain) and not re.search(r'\b(?:quem e voce|who are you)\b',plain): return '30d'
    if re.search(r'\b(hoje|agora|neste momento|neste instante|ao vivo|tempo real|ultimas 24 horas|right now|today|live)\b',plain): return '1d'
    if re.search(r'\b(ultima hora|ultimas noticias|noticias recentes|noticia recente|esta semana|nesta semana|ultimos dias|ultima semana|breaking news|news about)\b',plain): return '7d'
    if re.search(r'\b(atual|atualmente|atualizado|atualizada|mais recentes?|recentemente|recentes?|ultimo|ultima|latest|current|newest|updated|how much|quanto custa|quanto custam|quanto sai|quanto vale|cost|price|custo|preco atual|valor atual)\b',plain): return '30d'
    return ''

def asks_latest_version(text):
    """Recognize a generic request for the newest software/product version."""
    plain=normalize_words(text)
    return bool(re.search(r'\b(?:ultima|ultimas|ultimo|ultimos|mais recente|mais novos?|latest|newest|current)\b.{0,32}\b(?:versao|version|release|lancamento|build)\b|\b(?:versao|version|release|lancamento|build)\b.{0,32}\b(?:atual|atualmente|ultima|ultimo|mais recente|latest|newest|current)\b',plain))

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
    if calculate_local_expression(prompt): return False
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
    ignored={'a','as','o','os','um','uma','uns','umas','de','do','da','dos','das','em','no','na','nos','nas','com','por','para','pra','e','ou','que','qual','quais','quem','como','onde','quando','quanto','esta','sao','porque','sobre','versao','version','pesquise','pesquisar','busque','buscar','procure','procurar','me','diga','mostre','informe','hoje','agora','atual','atualmente','atualizada','atualizado','recente','recentes','ultima','ultimas','ultimos','ultimo','mais','ao','vivo','news','latest','current','breaking','today','now','recent','search','find','about','what','whats','the','for','and','with','from','is','are','was','were','be','been','being','do','does','did','have','has','had','can','could','would','should','will','who','when','where','why','how','much','many','please','tell','explain','explanation','describe','compare','comparison','difference','between','mean','means','meaning','work','works','working','function','of'}
    terms={word for word in re.findall(r'[a-z0-9]+',plain) if (len(word)>2 or word.isdigit()) and word not in ignored}
    format_words={'noticia','noticias','novidades','ultimas'}
    subject_terms=terms-format_words
    return subject_terms or terms

def _search_term_forms(term):
    """Return conservative Portuguese singular forms for relevance matching."""
    term=str(term)
    forms={term}
    if len(term)>5 and term.endswith('res'):
        forms.add(term[:-2])
    if len(term)>4 and term.endswith('s'):
        forms.add(term[:-1])
    return forms

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
    overlap={term for term in wanted if _search_term_forms(term) & found}
    # Two-term queries still require both anchors. Longer natural-language
    # queries tolerate omitted modifiers while requiring at least two matches.
    required=len(wanted) if len(wanted)<=2 else max(2,math.ceil(len(wanted)*0.60))
    if len(overlap)<required: return 0.0
    return len(overlap)/max(1,len(wanted))

def _search_query_variants(query,freshness=''):
    """Keep the spoken query first, then try a compact subject-focused form."""
    original=' '.join(str(query).split())
    normalized=unicodedata.normalize('NFKD',original).encode('ascii','ignore').decode('ascii')
    cleaned=re.sub(
        r'\b(?:por favor|poderia|gostaria de saber|quero saber|me diga|me fale|me mostra|mostra para mim|'
        r'pesquise|pesquisar|busque|buscar|procure|procurar|encontre|encontrar|'
        r'quais s(?:ã|a)o|qual e|quem e|quando foi|onde fica|o que e|o que voce sabe sobre|como funciona|'
        r'novidades?|versao|version|'
        r'tutorial|tutoriais|guias?|passo a passo|instrucoes|manuais?|como|'
        r'jogar|jogue|play|playing|instalar|install|configurar|configure|fazer|make|montar|build|usar|use|'
        r'hoje|agora|atual|atualmente|recente|recentes|ultima|ultimas|ultimos|ultimo|mais|'
        r'a|as|o|os|um|uma|uns|umas|de|do|da|dos|das|em|no|na|nos|nas|com|por|para|pra|sobre|qual|quais|e|ou|que)\b',
        ' ',normalized,flags=re.I)
    cleaned=' '.join(cleaned.split()).strip(' ,.:;!?')
    variants=[(current_web_query(original,freshness),original)]
    if cleaned and _fresh_query_terms(cleaned) and cleaned.casefold()!=normalized.casefold():
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
