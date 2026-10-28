# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import Qt
import re, aurora_fx
from .llm.inference import Inference
from .system.commands import parse_local_command
from .system.calculator import calculate_local_expression
from .system.files import normalize_words
from .web.intent import (
    contextual_followup, contextual_source_request, conversational_intent,
    current_search_window, local_datetime_answer,
    requested_response_language, search_intent,
)

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
    if not self.voice.request_active.is_set(): return
    prompt=prompt.strip()
    self.current_turn_kind='action'
    if not prompt:
        self.voice.speaking=False; self.orb.set_mode('listening'); return
    if self.inf and self.inf.isRunning() and not self.inf.cancelled: return
    self.activity_generation+=1; self.request_generation+=1
    requested_language=requested_response_language(prompt)
    if requested_language: self.response_language=requested_language
    if self.orb.isVisible(): self.orb.set_mode('thinking')
    else: self.orb.reveal('thinking')
    self.response_finished=False; self.current_prompt=prompt; self.active_search_context=''
    # ``voice.speaking`` is reserved for active TTS playback because the
    # microphone worker uses it to enable barge-in. Thinking must not arm it.
    source_followup=bool(self.context_history and contextual_source_request(prompt))
    direct=None if source_followup else parse_local_command(prompt)
    if direct:
        if direct[0]=='open_url':
            self.current_turn_kind='research'
            self.quick_summary_done(
                'Para manter tudo local, não abro sites nem acesso serviços externos.',
                self.request_generation,
            )
            return
        self.run_local_action(*direct); return
    local_answer=local_datetime_answer(prompt)
    if local_answer:
        self.quick_summary_done(local_answer,self.request_generation); return
    calculation=calculate_local_expression(prompt)
    if calculation:
        self.quick_summary_done(calculation,self.request_generation); return
    normalized=normalize_words(prompt)
    asks_hardware_temperature=bool(re.search(r'\b(cpu|gpu|processador|placa de video|computador|pc|hardware|placa grafica)\b',normalized))
    asks_weather=not asks_hardware_temperature and bool(
        re.search(r'\b(tempo|clima|previs[aã]o|temperatura|vai chover|chove)\b',normalized)
    )
    fx_intent=aurora_fx.detect_fx_intent(prompt)
    freshness=current_search_window(prompt)
    query=search_intent(prompt)
    external_search = bool(query or (freshness and not conversational_intent(prompt)))
    if asks_weather or fx_intent or (external_search and not _local_context_intent(normalized)):
        self.current_turn_kind='research'
        self.quick_summary_done(
            'Para manter tudo local, não consulto a internet nem serviços externos. '
            'Posso ajudar com informações já salvas no computador ou com o conhecimento do modelo local.',
            self.request_generation,
        )
        return
    is_followup=bool(self.context_history and contextual_followup(prompt))
    refers_to_source=bool(self.context_history and re.search(
        r'\b(fonte|link|noticia|artigo|resultado)\b',normalized
    ))
    agent_intent=(source_followup or refers_to_source or is_followup
                  or _agent_action_intent(normalized)
                  or _local_context_intent(normalized))
    if agent_intent:
        card=getattr(self,'research_card',None)
        if card:
            generation=self.request_generation
            card.begin(generation,prompt,self.orb.frameGeometry(),mode='local')
            card.update_progress(generation,{'stage':'understanding','tasks':['Entendendo o pedido'],
                                             'workers':1,'completed':0,'total':1})
    self.current_turn_kind='action' if agent_intent else 'conversation'
    model=self.cfg.get('agent_model','qwen2.5:1.5b') if agent_intent else self.cfg['model']
    inference=Inference(
        self.cfg,prompt,model=model,use_tools=agent_intent,history=self.context_history[-6:],
        response_language=self.response_language,
        session_context=getattr(self,'session_prompt_context',''),
    )
    generation=self.request_generation
    inference.sentence.connect(lambda text,g=generation:self.queue_sentence(text,g)); inference.search.connect(lambda q,out,g=generation:self.search_update(q,out) if g==self.request_generation else None,Qt.ConnectionType.QueuedConnection); inference.progress.connect(lambda event,g=generation:self.research_progress(event,g),Qt.ConnectionType.QueuedConnection); inference.approval.connect(lambda name,detail,g=generation:self.request_approval(name,detail) if g==self.request_generation else None); inference.error.connect(lambda message,g=generation:self.answer_error(message,g)); inference.result.connect(lambda text,g=generation:self.answer_done(text,g)); self.start_inference(inference,generation)
