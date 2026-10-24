# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import Qt
import re, aurora_fx
from .llm.inference import Inference
from .system.commands import parse_local_command
from .system.calculator import calculate_local_expression
from .system.files import normalize_words
from .voice.wake import LocalVoice
from .web.intent import (
    contextual_followup, contextual_source_request, current_search_window,
    factual_web_intent, local_datetime_answer, news_search_intent,
    requested_response_language, research_request_intent, search_intent,
)
from .web.requests import FXRequest, SearchRequest, WeatherRequest

_AGENT_ACTION = re.compile(
    r'\b(abr(?:a|e|em|o|imos|ir|iu|iram)|inici(?:a|e|am|o|amos|ar|ou|aram)|'
    r'execut(?:a|e|am|o|amos|ar|ou|aram)|rod(?:a|e|am|o|amos|ar|ou|aram)|'
    r'clic(?:a|e|am|o|amos|ar|ou|aram)|digit(?:a|e|am|o|amos|ar|ou|aram)|'
    r'escrev(?:a|e|em|o|emos|er|eu|eram)|control(?:a|e|am|o|amos|ar|ou|aram)|'
    r'cri(?:a|e|am|o|amos|ar|ou|aram)|faca|faco|faz|fazer|fiz|'
    r'ger(?:a|e|am|o|amos|ar|ou|aram)|lembr(?:a|e|am|o|amos|ar|ou|aram)|'
    r'esquec(?:e|a|em|o|emos|er|eu|eram)|salv(?:a|e|am|o|amos|ar|ou|aram)|'
    r'leia|leio|ler|aces(?:sa|se|sam|so|samos|sar|sou|saram)|'
    r'lanc(?:a|e|am|o|amos|ar|ou|aram)|coloc(?:a|e|am|o|amos|ar|ou|aram)|'
    r'minimiz(?:a|e|am|o|amos|ar|ou|aram)|maximiz(?:a|e|am|o|amos|ar|ou|aram)|'
    r'fech(?:a|e|am|o|amos|ar|ou|aram)|encerr(?:a|e|am|o|amos|ar|ou|aram)|'
    r'aument(?:a|e|am|o|amos|ar|ou|aram)|diminu(?:a|e|em|o|imos|ir|iu|iram)|'
    r'baix(?:a|e|am|o|amos|ar|ou|aram)|silenci(?:a|e|am|o|amos|ar|ou|aram)|'
    r'mut(?:a|e|am|o|amos|ar|ou|aram)|pesquis\w*|busc\w*|procur\w*|'
    r'investig\w*|agend(?:a|e|am|o|amos|ar|ou|aram)|marc(?:a|e|am|o|amos|ar|ou|aram))\b'
)

_LOCAL_CONTEXT = re.compile(
    r'\b(?:meu|minha|neste|nesse|nesta|nessa|no meu|na minha|aqui no|aqui na)\s+'
    r'(?:computador|pc|desktop|laptop|notebook|sistema|tela|monitor|janela|janelas|'
    r'aplicativo|aplicativos|app|apps|programa|programas|arquivo|arquivos|pasta|'
    r'pastas|documento|documentos|downloads)\b|'
    r'\b(?:nesta|nessa) m[aá]quina\b|\b(?:instalado|instalada|instalados|instaladas)\b'
)


def _agent_action_intent(normalized_prompt):
    """Recognize broad action language so local requests beat generic web routing."""
    match=_AGENT_ACTION.search(normalized_prompt)
    if not match: return False
    prefix=normalized_prompt[:match.start()].strip()
    if not prefix: return True
    if re.fullmatch(r'como(?: eu)?',prefix): return True
    if (re.match(r'^(?:(?:por favor|aurora)\s*,?\s*)?(?:(?:eu\s+)?(?:quero|preciso|pode|poderia|consegue)|me ajuda|eu gostaria de|faz|faca)\b',prefix)
            and not re.search(r'\b(saber|entender|aprender|explicar|explicacao|informacao|noticia|valor|preco)\b',prefix)):
        return True
    return False


def _local_context_intent(normalized_prompt):
    """Prefer local tools when the request is explicitly scoped to this PC."""
    return bool(_LOCAL_CONTEXT.search(normalized_prompt))


def route_request(self,prompt):
    if not self.voice.request_active.is_set() and not getattr(self,'companion_request',None): return
    prompt=prompt.strip()
    if not prompt:
        self.voice.speaking=False; self.orb.set_mode('listening'); return
    if self.inf and self.inf.isRunning() and not self.inf.cancelled: return
    self.activity_generation+=1; self.request_generation+=1
    requested_language=requested_response_language(prompt)
    if requested_language: self.response_language=requested_language
    if self.orb.isVisible(): self.orb.set_mode('thinking')
    else: self.orb.reveal('thinking')
    self.response_finished=False; self.current_prompt=prompt; self.active_search_context=''
    self.voice.speaking=True
    source_followup=bool(self.context_history and contextual_source_request(prompt))
    direct=None if source_followup else parse_local_command(prompt)
    if direct:
        self.run_local_action(*direct); return
    local_answer=local_datetime_answer(prompt)
    if local_answer:
        self.quick_summary_done(local_answer,self.request_generation); return
    calculation=calculate_local_expression(prompt)
    if calculation:
        self.quick_summary_done(calculation,self.request_generation); return
    lower_prompt = prompt.lower().strip()
    if re.search(r'\b(mostre|mostrar|abrir|ver|espelhar)\s+(meu\s+)?(computador|pc|desktop|tela)\b', lower_prompt):
        if getattr(self, 'screen_stream', None):
            self.screen_stream.start()
        self.quick_summary_done("Abrindo o desktop remoto. Você já pode visualizar e controlar a tela do computador com toque pelo celular.", self.request_generation)
        return
    if re.search(r'\b(sair\s+do\s+desktop|fechar\s+(o\s+)?desktop|encerrar\s+(o\s+)?desktop|fechar\s+tela)\b', lower_prompt):
        if getattr(self, 'screen_stream', None):
            self.screen_stream.stop()
        self.quick_summary_done("Encerrando a transmissão do desktop e voltando ao modo live normal.", self.request_generation)
        return
    normalized=normalize_words(prompt)
    asks_hardware_temperature=bool(re.search(r'\b(cpu|gpu|processador|placa de video|computador|pc|hardware|placa grafica)\b',normalized))
    if not asks_hardware_temperature and re.search(r'\b(tempo|clima|previs[aã]o|temperatura|vai chover|chove)\b',prompt,re.I):
        self.orb.set_mode('weather')
        generation=self.request_generation
        if not self._mobile_audio_owned():
            self.research_card.begin(generation,prompt,self.orb.frameGeometry())
            self.research_card.update_progress(generation,{"stage":"searching","tasks":[prompt],"workers":1,"completed":0,"total":1})
        self.weather=WeatherRequest(self.cfg,prompt)
        self.weather.result.connect(lambda text,g=generation: self.weather_done(text,g))
        self.weather.error.connect(lambda message,g=generation: self.weather_error(message,g))
        self.start_background_request(self.weather); return
    fx_intent=aurora_fx.detect_fx_intent(prompt)
    if fx_intent:
        self.orb.set_mode('searching')
        generation=self.request_generation
        self.fx_request=FXRequest(fx_intent,prompt)
        self.fx_request.result.connect(lambda lookup,g=generation: self.fx_lookup_done(lookup,g),Qt.ConnectionType.QueuedConnection)
        self.fx_request.error.connect(lambda message,g=generation: self.quick_search_error(prompt,message,g),Qt.ConnectionType.QueuedConnection)
        self.start_background_request(self.fx_request); return
    freshness=current_search_window(prompt)
    query=search_intent(prompt)
    is_followup=bool(self.context_history and contextual_followup(prompt))
    relative_reference=bool(re.search(r'\b(isso|disso|nisso|desse|dessa|dele|dela|essa fonte|esse resultado|essa noticia|essa resposta|a primeira fonte|o primeiro resultado|a segunda fonte|o segundo resultado|a terceira fonte|o terceiro resultado)\b',normalized))
    needs_context_search=bool(is_followup and relative_reference and (query or freshness))
    if needs_context_search: query=''
    refers_to_source=bool(self.context_history and re.search(r'\b(fonte|link|noticia|artigo|resultado)\b',normalized))
    agent_intent=(source_followup or refers_to_source or needs_context_search
                  or _agent_action_intent(normalized)
                  or (not query and _local_context_intent(normalized)))
    # Explicit research wording always remains web research. Inferred freshness
    # and generic factual-question routes yield to action language so a local
    # request such as "Como abro o terminal?" is not sent to search first.
    if not query and not agent_intent and ((freshness and not needs_context_search) or ((factual_web_intent(prompt) or research_request_intent(prompt)) and not is_followup)):
        query=LocalVoice.strip_wake_word(prompt,self.cfg.get('assistant_name','Aurora')).strip(' \t,.:;!?')
    if query:
        generation=self.request_generation
        request=SearchRequest(query,freshness,news_search_intent(prompt))
        self.quick_search=request
        self.orb.set_mode('searching')
        if not self._mobile_audio_owned():
            self.research_card.begin(generation,prompt,self.orb.frameGeometry())
        request.progress.connect(lambda event,g=generation:self.research_progress(event,g),Qt.ConnectionType.QueuedConnection)
        request.result.connect(lambda q,out,g=generation:self.quick_search_done(q,out,g),Qt.ConnectionType.QueuedConnection)
        request.error.connect(lambda q,message,g=generation:self.quick_search_error(q,message,g),Qt.ConnectionType.QueuedConnection)
        self.start_background_request(self.quick_search); return
    if agent_intent and not getattr(self, '_mobile_audio_owned', lambda: False)():
        card=getattr(self,'research_card',None)
        if card:
            generation=self.request_generation
            card.begin(generation,prompt,self.orb.frameGeometry(),mode='local')
            card.update_progress(generation,{'stage':'understanding','tasks':['Entendendo o pedido'],
                                             'workers':1,'completed':0,'total':1})
    model=self.cfg.get('agent_model','gemma4:e2b-it-q4_K_M') if agent_intent else self.cfg['model']
    inference=Inference(self.cfg,prompt,model=model,use_tools=agent_intent,history=self.context_history[-6:],response_language=self.response_language)
    generation=self.request_generation
    inference.sentence.connect(lambda text,g=generation:self.queue_sentence(text,g)); inference.search.connect(lambda q,out,g=generation:self.search_update(q,out) if g==self.request_generation else None,Qt.ConnectionType.QueuedConnection); inference.progress.connect(lambda event,g=generation:self.research_progress(event,g),Qt.ConnectionType.QueuedConnection); inference.approval.connect(lambda name,detail,g=generation:self.request_approval(name,detail) if g==self.request_generation else None); inference.error.connect(lambda message,g=generation:self.answer_error(message,g)); inference.result.connect(lambda text,g=generation:self.answer_done(text,g)); self.start_inference(inference,generation)
