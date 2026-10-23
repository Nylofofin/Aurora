from __future__ import annotations

from PySide6.QtCore import QThread, Signal
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

ACTION_TOOL_NAMES = {
    'open_url', 'take_screenshot', 'spotify_play', 'obs_record',
    'open_application', 'close_application', 'manage_window',
    'inspect_accessible_windows', 'focus_accessible_window',
    'type_accessible_text', 'volume_control', 'get_system_info',
    'create_file', 'remember_preference', 'forget_preference',
}

class Inference(QThread):
    phrase=Signal(str); sentence=Signal(str); state=Signal(str); approval=Signal(str,object); result=Signal(str); error=Signal(str); search=Signal(str,str)
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
                        if self.cancelled: return 'Ação cancelada.'
                        try: parts.append(json.loads(raw.decode()).get('message',{}).get('content',''))
                        except Exception: continue
                finally: self.active_response=None
            translated=''.join(parts).strip()
            return translated or text
        except Exception: return text
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
        if self.response_language=='Português brasileiro' and likely_spanish(translated):
            return 'Não consegui responder em português agora. Pode repetir, por favor?'
        return translated
    def run(self):
        ep=self.cfg['endpoint'].rstrip('/')
        if not local_endpoint(ep): self.error.emit('O endpoint precisa ser localhost.'); return
        system=self.system_prompt or assistant_system_prompt(self.use_tools,self.response_language)
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
                action_only_turn=bool(call_names) and all(name in ACTION_TOOL_NAMES for name in call_names)
                final_action_turn=not calls and bool(action_results) and not other_tool_used
                if not action_only_turn and not final_action_turn:
                    for item,needs_translation in deferred_sentences:
                        if needs_translation: item=self._translate_before_speaking(item)
                        spoken_parts.append(item); self.sentence.emit(item)
                if not calls: break
                msgs.append({'role':'assistant','content':content,'tool_calls':calls})
                for call in calls:
                    # A cancellation may arrive after the model stream closes but
                    # before the next tool call. Never start a local side effect
                    # once the user has cancelled the request.
                    if self.cancelled: return
                    fn=call.get('function',{}); name=fn.get('name',''); args=fn.get('arguments',{})
                    if isinstance(args,str):
                        try: args=json.loads(args)
                        except Exception: args={}
                    output=self.execute_tool(name,args)
                    if name in ACTION_TOOL_NAMES:
                        action_results.append(str(output))
                    else:
                        other_tool_used=True
                    msgs.append({'role':'tool','tool_name':name,'content':output})
                    if self.cancelled: return
                if self.cancelled: return
                # A local action already has an authoritative result. Do not
                # spend another (potentially slow) Gemma turn paraphrasing it:
                # that second request can leave the orb in "thinking" after
                # the screenshot or other action has completed.
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
    def execute_tool(self,name,args):
        local_result=execute_local_tool(name,args,self.cfg)
        if local_result is not None: return local_result
        if name=='read_web_page':
            try: return read_public_page(str(args.get('url','')))
            except Exception as exc: return f'Página não lida: {exc}'
        if name=='web_search':
            query=str(args.get('query','')).strip()
            self.search.emit(query,'')
            freshness=current_search_window(self.prompt) or current_search_window(query)
            if not freshness and _is_historical_query(self.prompt): freshness=False
            try: output=search_public_web(query,freshness)
            except Exception as exc: output=f'Busca não concluída: {exc}'
            self.search.emit(query,output)
            return output
        if name not in ('close_application','manage_window','open_url','take_screenshot','spotify_play','obs_record','focus_accessible_window','type_accessible_text'): return 'Ferramenta indisponível.'
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
