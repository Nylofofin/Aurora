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
    if not query and ((freshness and not needs_context_search) or ((factual_web_intent(prompt) or research_request_intent(prompt)) and not is_followup)):
        query=LocalVoice.strip_wake_word(prompt).strip(' \t,.:;!?')
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
    refers_to_source=bool(self.context_history and re.search(r'\b(fonte|link|noticia|artigo|resultado)\b',normalized))
    agent_intent=source_followup or refers_to_source or needs_context_search or bool(re.search(r'\b(abra|abrir|abre|aberto|aberta|inicie|iniciar|execute|executar|rode|rodar|clique|clicar|digite|digitar|escreva|escrever|controle o computador|controle o pc|crie|criar|faca|gere|gerar|lembre|lembrar|esqueca|esquecer|salve|salvar|salve como|salvar como|leia|ler|acesse|acessar|lance|lancar|bote|coloque|minimize|minimizar|maximize|maximizar|feche|fechar|fecha|encerre|encerrar|encerra|aumente|aumentar|diminua|diminuir|baixe|baixar|silencie|mute|pesquise|pesquisar|busque|buscar|procure|procurar|investigue|investigar)\b',normalized))
    model=self.cfg.get('agent_model','gemma4:e2b-it-q4_K_M') if agent_intent else self.cfg['model']
    inference=Inference(self.cfg,prompt,model=model,use_tools=agent_intent,history=self.context_history[-6:],response_language=self.response_language)
    generation=self.request_generation
    inference.sentence.connect(lambda text,g=generation:self.queue_sentence(text,g)); inference.search.connect(lambda q,out,g=generation:self.search_update(q,out) if g==self.request_generation else None); inference.progress.connect(lambda event,g=generation:self.research_progress(event,g),Qt.ConnectionType.QueuedConnection); inference.approval.connect(lambda name,detail,g=generation:self.request_approval(name,detail) if g==self.request_generation else None); inference.error.connect(lambda message,g=generation:self.answer_error(message,g)); inference.result.connect(lambda text,g=generation:self.answer_done(text,g)); self.start_inference(inference,generation)
