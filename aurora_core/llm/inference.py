# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json, re, threading, time, urllib.error, urllib.request
from ..config import local_endpoint
from .prompts import assistant_system_prompt, complete_spoken_response
from .tools import TOOLS, execute_local_tool
from ..system.files import normalize_words
from ..system.commands import parse_local_command
from ..web.language import likely_english, likely_portuguese, likely_spanish
from ..web.intent import _is_historical_query, current_search_window, guided_learning_intent
from ..web.fetch import read_public_page
from ..web.pipeline import search_public_web
from ..web.orchestra import local_parallel_tool_calls, local_worker_limit

ACTION_TOOL_NAMES = {
    'open_url', 'take_screenshot', 'obs_record',
    'open_application', 'close_application', 'manage_window',
    'inspect_accessible_windows', 'focus_accessible_window',
    'type_accessible_text', 'volume_control', 'get_system_info',
    'create_file', 'remember_preference', 'forget_preference',
    'agenda_add', 'agenda_cancel', 'agenda_clear', 'agenda_list', 'agenda_nearest',
}

# These inspections return deterministic local findings; a second model turn
# only adds latency and can distort an already verified system status.
DIRECT_RESULT_TOOL_NAMES = {'check_system_health'}


def _agenda_add_needs_followup(result):
    """Let the model clarify a failed agenda request instead of speaking a fixed prompt."""
    text = str(result).strip()
    return text.startswith(('Precisa de um título', 'A data ou hora do compromisso'))


def _tool_progress_label(name):
    """Use short, user-facing labels while a tool-backed request is running."""
    labels={
        'web_search':'Consultando a web','read_web_page':'Lendo página',
        'open_url':'Abrindo site','take_screenshot':'Capturando tela',
        'obs_record':'Controlando OBS',
        'open_application':'Abrindo aplicativo','close_application':'Encerrando aplicativo',
        'manage_window':'Ajustando janela','inspect_accessible_windows':'Lendo controles da janela',
        'focus_accessible_window':'Focando controle','type_accessible_text':'Digitando texto',
        'volume_control':'Ajustando volume','get_system_info':'Consultando o computador',
        'check_system_health':'Verificando o estado do sistema',
        'create_file':'Criando arquivo','remember_preference':'Salvando preferência',
        'forget_preference':'Removendo preferência','agenda_add':'Salvando compromisso',
        'agenda_cancel':'Atualizando agenda','agenda_clear':'Limpando agenda',
        'agenda_list':'Consultando agenda','agenda_nearest':'Consultando próximo compromisso',
    }
    return labels.get(name,'Executando etapa')

class Inference(QThread):
    phrase=Signal(str); sentence=Signal(str); state=Signal(str); approval=Signal(str,object); result=Signal(str); error=Signal(str); search=Signal(str,str); progress=Signal(object)
    def __init__(self, cfg, prompt, model=None, use_tools=False, history=None, system_prompt=None,response_language='Português brasileiro'): super().__init__(); self.cfg=cfg; self.prompt=prompt; self.model=model or cfg['model']; self.use_tools=use_tools; self.history=(history or [])[-6:]; self.system_prompt=system_prompt; self.response_language=response_language; self.cancelled=False; self.active_response=None
    def cancel(self):
        self.cancelled=True
        response=self.active_response
        if response:
            try: response.close()
            except Exception: pass
    def translate_to_language(self,text,language='Português brasileiro'):
        ep=self.cfg['endpoint'].rstrip('/')
        system=f'Você é tradutor. Traduza para {language}. Preserve exatamente o sentido, nomes próprios, números, unidades e fontes. Responda somente com a tradução, sem comentários.'
        payload={'model':self.model,'messages':[
            {'role':'system','content':system},
            {'role':'user','content':f'Traduza esta resposta para {language}. Preserve o significado, números, unidades e fontes. Omita emojis e descrições de emojis. Retorne somente a tradução: '+text}],
            'stream':True,'keep_alive':self.cfg['keep_alive'],'think':False,
            'options':{'num_ctx':int(self.cfg['num_ctx']),'num_thread':int(self.cfg['num_thread']),'num_gpu':int(self.cfg['num_gpu']),'temperature':0.1,'num_predict':64}}
        req=urllib.request.Request(ep+'/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            parts=[]
            with urllib.request.urlopen(req,timeout=24) as response:
                self.active_response=response
                try:
                    for raw in response:
                        if self.cancelled: return ''
                        try: parts.append(json.loads(raw.decode()).get('message',{}).get('content',''))
                        except Exception: continue
                finally: self.active_response=None
            translated=''.join(parts).strip()
            return translated
        except Exception: return ''
    def _needs_translation(self,text):
        language=self.response_language
        if language=='Português brasileiro':
            return likely_english(text) or likely_spanish(text)
        if language=='English':
            return likely_portuguese(text) or likely_spanish(text)
        if language=='Spanish':
            return likely_english(text) or likely_portuguese(text)
        return likely_english(text) or likely_portuguese(text) or likely_spanish(text)
    def _translate_before_speaking(self,text):
        translated=self.translate_to_language(text,self.response_language)
        failed=not translated.strip()
        if self.response_language=='Português brasileiro':
            failed=failed or likely_english(translated) or likely_spanish(translated)
            if failed: return 'Não consegui responder em português agora. Pode repetir, por favor?'
        elif self.response_language=='English':
            failed=failed or likely_portuguese(translated) or likely_spanish(translated)
            if failed: return 'I could not prepare the answer in English just now. Please try again.'
        elif self.response_language=='Spanish':
            failed=failed or likely_english(translated) or likely_portuguese(translated)
            if failed: return 'No pude preparar la respuesta en español. Inténtalo de nuevo.'
        elif failed:
            return 'Não consegui preparar a resposta no idioma solicitado.'
        return translated
    def run(self):
        ep=self.cfg['endpoint'].rstrip('/')
        if not local_endpoint(ep): self.error.emit('O endpoint precisa ser localhost.'); return
        if self.use_tools:
            self.progress.emit({'mode':'local','stage':'planning','title':self.prompt,
                                'tasks':['Interpretando o pedido'],'workers':1,
                                'completed':0,'total':1})
        system=self.system_prompt or assistant_system_prompt(
            self.use_tools,self.response_language,self.cfg.get('assistant_name','Aurora'),
            self.cfg.get('user_name',''))
        msgs=[{'role':'system','content':system}]
        msgs.extend({'role':item['role'],'content':str(item['content'])[:900]} for item in self.history if item.get('role') in ('user','assistant'))
        msgs.append({'role':'user','content':self.prompt})
        complete=''; spoken=''; turns=0; spoken_parts=[]; action_results=[]; other_tool_used=False
        try:
            while turns<5 and not self.cancelled:
                turns+=1
                agent_ctx=max(int(self.cfg.get('num_ctx',1024)),int(self.cfg.get('agent_num_ctx',2048))) if self.use_tools else int(self.cfg['num_ctx'])
                budget=int(self.cfg.get('agent_num_predict',384)) if self.use_tools else (160 if guided_learning_intent(self.prompt) or re.search(r'\b(explique|detalhe|passo a passo|por que|como funciona|compare|lista)\b',normalize_words(self.prompt)) else 96)
                payload={'model':self.model,'messages':msgs,'stream':True,'keep_alive':self.cfg['keep_alive'],
                    'think':False,'options':{'num_ctx':agent_ctx,'num_thread':int(self.cfg['num_thread']),'num_gpu':int(self.cfg['num_gpu']),'temperature':0.25,'num_batch':128,'num_predict':budget}}
                if self.use_tools: payload['tools']=TOOLS
                req=urllib.request.Request(ep+'/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
                content=''; calls=[]; deferred_sentences=[]; defer_stream=self.use_tools
                from ..voice.telemetry import elapsed_ms, log_voice_timing
                turn_started=time.perf_counter(); first_response_logged=False
                with urllib.request.urlopen(req,timeout=240) as response:
                    self.active_response=response
                    try:
                        for raw in response:
                            if self.cancelled: return
                            try: m=json.loads(raw.decode()).get('message',{})
                            except Exception: continue
                            part=m.get('content','')
                            if (part or m.get('tool_calls')) and not first_response_logged:
                                log_voice_timing('llm_first_response',elapsed_ms(turn_started))
                                first_response_logged=True
                            if part:
                                content+=part; complete+=part; spoken+=part
                                pieces=re.split(r'(?<=[.!?])\s+',spoken)
                                if len(pieces)>1:
                                    for item in pieces[:-1]:
                                        item=item.strip()
                                        if item:
                                            needs_translation=self._needs_translation(item)
                                            if defer_stream or needs_translation:
                                                # Do not start a second Ollama request while this stream is still open.
                                                defer_stream=True; deferred_sentences.append((item,needs_translation))
                                            else:
                                                spoken_parts.append(item); self.sentence.emit(item)
                                    spoken=pieces[-1]
                            if m.get('tool_calls'): calls.extend(m['tool_calls'])
                    finally: self.active_response=None
                log_voice_timing('llm_turn',elapsed_ms(turn_started))
                call_names=[call.get('function',{}).get('name','') for call in calls]
                action_only_turn=bool(call_names) and all(
                    name in ACTION_TOOL_NAMES or name in DIRECT_RESULT_TOOL_NAMES
                    for name in call_names
                )
                final_action_turn=not calls and bool(action_results) and not other_tool_used
                if not action_only_turn and not final_action_turn:
                    for item,needs_translation in deferred_sentences:
                        if needs_translation: item=self._translate_before_speaking(item)
                        spoken_parts.append(item); self.sentence.emit(item)
                if not calls: break
                msgs.append({'role':'assistant','content':content,'tool_calls':calls})
                outputs=self._execute_tool_batch(calls)
                if outputs is None: return
                for call,name,output in outputs:
                    if name in ACTION_TOOL_NAMES or name in DIRECT_RESULT_TOOL_NAMES:
                        action_results.append(str(output))
                        # A failed agenda creation needs another model turn so
                        # it can ask for the missing/invalid date naturally.
                        if name == 'agenda_add' and _agenda_add_needs_followup(output):
                            other_tool_used=True
                    else:
                        other_tool_used=True
                    msgs.append({'role':'tool','tool_name':name,'content':output})
                    if self.cancelled: return
                if self.cancelled: return
                # Local actions and deterministic inspections already have an
                # authoritative result. Avoid a slow paraphrase turn that can
                # leave the orb thinking or alter a verified status.
                if action_only_turn and not other_tool_used:
                    break
            if not (action_results and not other_tool_used):
                tail=spoken.strip()
                if tail and re.search(r'[.!?][\"”’\')\]]*$',tail):
                    if self._needs_translation(tail): tail=self._translate_before_speaking(tail)
                    spoken_parts.append(tail); self.sentence.emit(tail)
            if action_results and not other_tool_used:
                complete_response=complete_spoken_response(' '.join(action_results))
                for item in re.split(r'(?<=[.!?])\s+',complete_response):
                    if item.strip(): self.sentence.emit(item.strip())
                self.result.emit(complete_response)
                return
            complete_response=complete_spoken_response(' '.join(spoken_parts))
            if not complete_response:
                complete_response=complete_spoken_response(complete) or 'Não consegui concluir a resposta.'
            self.result.emit(complete_response)
        except urllib.error.HTTPError as e:
            self.error.emit(f'Ollama local retornou {e.code}. Confira a tag {self.model}.')
        except Exception as e:
            self.error.emit('Não conectei ao Ollama local. Confira se ele está ativo e se o Gemma está instalado.')

    def _execute_tool_batch(self,calls):
        """Run only independent read-only local inspections concurrently."""
        if not local_parallel_tool_calls(calls):
            outputs=[]
            tasks=[_tool_progress_label(call.get('function',{}).get('name','')) for call in calls]
            tool_names={call.get('function',{}).get('name','') for call in calls}
            mode='web' if tool_names.intersection({'web_search','read_web_page'}) else 'local'
            if tasks:
                self.progress.emit({'mode':mode,'stage':'executing','title':self.prompt,
                                    'tasks':tasks,'workers':1,'completed':0,'total':len(calls)})
            for index,call in enumerate(calls):
                if self.cancelled: return None
                fn=call.get('function',{}); name=fn.get('name',''); args=fn.get('arguments',{})
                if isinstance(args,str):
                    try: args=json.loads(args)
                    except Exception: args={}
                outputs.append((call,name,self.execute_tool(name,args)))
                self.progress.emit({'mode':mode,'stage':'executing','title':self.prompt,
                                    'tasks':tasks,'workers':1,'completed':index+1,'total':len(calls),
                                    'finished_task':tasks[index]})
            return outputs

        worker_count=local_worker_limit(len(calls))
        def label(call):
            fn=call.get('function',{}); name=fn.get('name','')
            args=fn.get('arguments',{})
            if isinstance(args,str):
                try: args=json.loads(args)
                except Exception: args={}
            detail=args.get('application') if isinstance(args,dict) else None
            if name=='volume_control': return 'Consultar volume'
            if name=='get_system_info': return 'Consultar hardware'
            return f'Inspecionar {str(detail or "aplicativo")[:48]}'
        tasks=[label(call) for call in calls]
        self.progress.emit({'mode':'local','stage':'executing','title':self.prompt,
                            'tasks':tasks,'workers':worker_count,'completed':0,'total':len(calls)})
        if worker_count < 2:
            outputs=[]
            for index,call in enumerate(calls):
                if self.cancelled: return None
                fn=call.get('function',{}); name=fn.get('name',''); args=fn.get('arguments',{})
                if isinstance(args,str):
                    try: args=json.loads(args)
                    except Exception: args={}
                output=self.execute_tool(name,args)
                outputs.append((call,name,output))
                self.progress.emit({'mode':'local','stage':'executing','title':self.prompt,
                    'tasks':tasks,'workers':1,'completed':index+1,'total':len(calls),
                    'finished_task':tasks[index]})
            return outputs
        executor=ThreadPoolExecutor(max_workers=worker_count,thread_name_prefix='aurora-local-agent')
        pending={}; outputs=[None]*len(calls); completed=0
        try:
            for index,call in enumerate(calls):
                if self.cancelled:
                    for future in pending: future.cancel()
                    return None
                fn=call.get('function',{}); name=fn.get('name',''); args=fn.get('arguments',{})
                if isinstance(args,str):
                    try: args=json.loads(args)
                    except Exception: args={}
                pending[executor.submit(self.execute_tool,name,args)]=(index,call,name)
            while pending:
                if self.cancelled:
                    for future in pending: future.cancel()
                    return None
                done,_=wait(tuple(pending),timeout=0.1,return_when=FIRST_COMPLETED)
                for future in done:
                    index,call,name=pending.pop(future)
                    try: output=future.result()
                    except Exception as exc: output=f'Consulta local falhou: {type(exc).__name__}.'
                    outputs[index]=(call,name,output); completed+=1
                    self.progress.emit({'mode':'local','stage':'executing','title':self.prompt,
                        'tasks':tasks,'workers':worker_count,'completed':completed,'total':len(calls),
                        'finished_task':tasks[index]})
            return outputs
        finally:
            executor.shutdown(wait=not self.cancelled,cancel_futures=True)

    def execute_tool(self,name,args):
        local_result=execute_local_tool(name,args,self.cfg)
        if local_result is not None: return local_result
        if name=='read_web_page':
            self.progress.emit({'mode':'web','stage':'reading','tasks':['Abrindo página solicitada'],
                                'workers':1,'completed':0,'total':1})
            try: result=read_public_page(str(args.get('url','')))
            except Exception as exc: result=f'Página não lida: {exc}'
            self.progress.emit({'mode':'web','stage':'reading','tasks':['Abrindo página solicitada'],
                                'workers':1,'completed':1,'total':1})
            return result
        if name=='web_search':
            query=str(args.get('query','')).strip()
            self.search.emit(query,'')
            freshness=current_search_window(self.prompt) or current_search_window(query)
            if not freshness and _is_historical_query(self.prompt): freshness=False
            try:
                output=search_public_web(
                    query, freshness,
                    progress=lambda event: self.progress.emit({'mode':'web', **event}),
                )
            except Exception as exc: output=f'Busca não concluída: {exc}'
            self.search.emit(query,output)
            return output
        if name not in ('close_application','manage_window','open_url','take_screenshot','obs_record','focus_accessible_window','type_accessible_text','agenda_clear'): return 'Ferramenta indisponível.'
        parsed_request=parse_local_command(self.prompt)
        explicit_request=bool(parsed_request and parsed_request[0]==name)
        if name=='obs_record' and explicit_request:
            explicit_request=parsed_request[1].get('action')==args.get('action')
        detail={'name':name,'args':args,'event':threading.Event(),'result':'Ação recusada.',
                'explicit_user_request':explicit_request}
        self.approval.emit(name,detail)
        if not detail['event'].wait(90): return 'Autorização expirou; ação cancelada.'
        if self.cancelled: return 'Ação cancelada porque Aurora está encerrando.'
        return str(detail['result'])
