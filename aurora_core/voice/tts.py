# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import gc, queue, re, shutil, time, sys
import subprocess
import importlib.util

from .catalog import voice_files

def local_piper_available():
    """Whether Piper's runtime is installed (individual voices are separate)."""
    try:
        return importlib.util.find_spec('piper') is not None
    except (ImportError, ValueError, OSError):
        return False

class Speaker(QThread):
    speaking=Signal(bool); audio_started=Signal(); drained=Signal(); speech_level=Signal(float); speech_error=Signal(str); preview_error=Signal(str,str)
    def __init__(self,cfg): super().__init__(); self.cfg=cfg; self.q=queue.Queue(); self.running=True; self.active=False; self.playing=False; self.current_player=None; self.cancel_generation=0; self.engine=shutil.which('ffplay'); self._deferred_item=None
    def prepare(self):
        """Warm the selected local voice while the user is speaking/LLM is working."""
        if self.running:
            self.q.put(("",time.perf_counter(),None,None,False,True))
    def say(self,text):
        text=self.clean(text)
        # Keep the complete spoken answer; do not silently truncate what the
        # interface displays and the user expects to hear.
        if text: self.q.put((text,time.perf_counter(),None,None))
    def say_with_voice(self,text,voice,pitch=None,speed=None):
        """Queue a Faber preview without changing the saved voice settings."""
        text=self.clean(text); voice=str(voice or '').strip()
        if text: self.q.put((text[:500],time.perf_counter(),voice or None,'piper',True,pitch,speed))
    @staticmethod
    def clean(text):
        text=str(text)
        text=re.sub(r'[\U0001F000-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF\u200d\ufe0f\u20e3]', ' ',text)
        text=re.sub(r'\b(?:(?:um|uma)\s+)?(?:emoji\s+(?:de\s+)?)?(?:rosto\s+sorridente(?:\s+com\s+olhos\s+sorridentes)?|rosto\s+sorrindo(?:\s+com\s+olhos\s+sorridentes)?|carinha\s+sorridente)\b',' ',text,flags=re.I)
        text=re.sub(r'\b(?:slightly smiling face|smiling face(?:\s+(?:with|and)\s+smiling eyes)?|smiling eyes|grinning face|face with tears of joy|rosto sorridente(?:\s+com olhos sorridentes)?)(?:\s*,\s*(?:smiling eyes|eyes smiling))?\s*(?:emoji)?\b',' ',text,flags=re.I)
        # Convert DD/MM/YYYY and DD/MM into natural spoken Portuguese (e.g. 26 de outubro de 2026 / 27 de outubro)
        months={'01':'janeiro','02':'fevereiro','03':'março','04':'abril','05':'maio','06':'junho',
                '07':'julho','08':'agosto','09':'setembro','10':'outubro','11':'novembro','12':'dezembro'}
        def _replace_date(m):
            d, mon, y = m.group(1), m.group(2), m.group(3)
            return f'{int(d)} de {months.get(mon, mon)} de {y}'
        text=re.sub(r'\b(0?[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/((?:19|20)\d{2})\b', _replace_date, text)
        def _replace_day_month(m):
            d, mon = m.group(1), m.group(2)
            return f'{int(d)} de {months.get(mon, mon)}'
        text=re.sub(r'\b(0?[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])\b', _replace_day_month, text)
        # Convert HH:MM into natural spoken Portuguese
        def _replace_time(m):
            h, mn = int(m.group(1)), int(m.group(2))
            h_str = f'{h} hora' if h == 1 else f'{h} horas'
            return h_str if mn == 0 else f'{h_str} e {mn} minutos'
        text=re.sub(r'\b([01]?\d|2[0-3]):([0-5]\d)\b', _replace_time, text)
        text=re.sub(r'\s+([,.;:!?])',r'\1',text)
        text=re.sub(r'[,;:]+([.!?])',r'\1',text).strip(' ,;:')
        text=re.sub(r'([.!?])(?:\s*[.!?])+',r'\1',text)
        return ' '.join(text.split())
    @staticmethod
    def word_boundary_pulse(text):
        letters=sum(char.isalnum() for char in str(text))
        return min(.88,.28+min(letters,12)*.045) if letters else .18
    def _load_piper_voice(self,voice_id=None):
        voice_id = str(voice_id or self.cfg.get('tts_voice', 'pt_BR-faber-medium'))
        loaded_id = getattr(self, '_piper_voice_id', None)
        voice = getattr(self,'_piper_voice',None)
        if voice is not None and loaded_id == voice_id: return voice
        # Keep exactly one neural TTS model resident in memory.
        self._piper_voice = None
        self._piper_voice_id = None
        gc.collect()
        model_path, config_path = voice_files(voice_id)
        if not model_path.is_file() or not config_path.is_file():
            raise FileNotFoundError(f'A voz {voice_id} ainda não foi baixada pelo seletor de vozes.')
        from piper import PiperVoice
        started=time.perf_counter()
        voice=PiperVoice.load(str(model_path), config_path=str(config_path), use_cuda=False)
        self._piper_voice=voice
        self._piper_voice_id=voice_id
        print(f'[voice-timing] stage=tts_model_load elapsed_ms={int((time.perf_counter()-started)*1000)} outcome=ok',flush=True)
        return voice
    def _stream_piper(self,text,generation,voice_id=None,pitch=None,speed=None):
        """Generate and play sentence chunks locally; no text leaves this machine."""
        from .telemetry import elapsed_ms, log_voice_timing
        started=time.perf_counter(); first_audio=False; player=None
        voice=self._load_piper_voice(voice_id)
        current_pitch = float(pitch if pitch is not None else self.cfg.get('tts_pitch', 1.25))
        current_speed = float(speed if speed is not None else self.cfg.get('tts_speed', 1.0))
        sr = voice.config.sample_rate
        ffplay_cmd = [self.engine,'-nodisp','-autoexit','-loglevel','quiet',
                      '-probesize','32','-analyzeduration','0',
                      '-f','s16le','-ar',str(sr),'-ch_layout','mono','-i','pipe:0']
        # Apply pitch shifting & speed tuning cleanly via audio filters if requested
        filters = []
        if abs(current_pitch - 1.0) > 0.01:
            shifted_rate = int(sr * current_pitch)
            tempo_comp = 1.0 / current_pitch
            filters.append(f'asetrate={shifted_rate},aresample={sr},atempo={tempo_comp:.4f}')
        if abs(current_speed - 1.0) > 0.01:
            filters.append(f'atempo={current_speed:.4f}')
        if filters:
            ffplay_cmd.extend(['-af', ','.join(filters)])
        try:
            player=subprocess.Popen(ffplay_cmd,
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.current_player=player
            for chunk in voice.synthesize(text):
                if generation!=self.cancel_generation: raise RuntimeError('speech interrupted')
                if not chunk.audio_int16_bytes: continue
                player.stdin.write(chunk.audio_int16_bytes); player.stdin.flush()
                if not first_audio:
                    first_audio=True
                    log_voice_timing('tts_first_audio',elapsed_ms(started))
                    self.playing=True; self.audio_started.emit()
                self.speech_level.emit(.42)
            # Send 180ms of silence padding to prevent ffplay from clipping the final syllables on pipe close
            silence_samples = int(sr * 0.18)
            player.stdin.write(b'\x00\x00' * silence_samples)
            player.stdin.flush()
            if player.stdin and not player.stdin.closed: player.stdin.close()
            if player.wait(timeout=15)!=0: raise RuntimeError('ffplay failed')
        except BaseException:
            if player is not None and player.poll() is None: player.kill(); player.wait()
            raise
        finally:
            self.speech_level.emit(0.0)
            if player is not None and self.current_player is player: self.current_player=None
    def run(self):
        while self.running:
            if self._deferred_item is not None:
                item=self._deferred_item; self._deferred_item=None
            else:
                try: item=self.q.get(timeout=.3)
                except queue.Empty: continue
            voice=None; engine='piper'; is_preview=False; is_warmup=False; pitch=None; speed=None
            if isinstance(item,tuple) and len(item)==7:
                text,queued_at,voice,engine,is_preview,pitch,speed=item
            elif isinstance(item,tuple) and len(item)==6:
                text,queued_at,voice,engine,is_preview,is_warmup=item
            elif isinstance(item,tuple) and len(item)==4:
                text,queued_at,voice,engine=item
            else:
                continue
            # Stream the first phrase immediately, then collapse phrases that
            # accumulated while Piper was speaking into one synthesis/player
            # session. This preserves every word while avoiding an ffplay
            # process and model warm-up for every queued sentence.
            if not (is_preview or is_warmup) and hasattr(self.q,'get_nowait'):
                while True:
                    try: pending=self.q.get_nowait()
                    except queue.Empty: break
                    if (isinstance(pending,tuple) and len(pending)==4
                            and pending[2]==voice and pending[3]==engine):
                        text=f'{text.rstrip()} {pending[0].lstrip()}'.strip()
                    else:
                        self._deferred_item=pending
                        break
            from .telemetry import elapsed_ms, log_voice_timing
            generation=self.cancel_generation
            log_voice_timing('tts_queue',elapsed_ms(queued_at))
            if is_warmup:
                try:
                    self._load_piper_voice(self.cfg.get('tts_voice'))
                except Exception as exc:
                    print(f'[voice] warmup_failed engine={self.cfg.get("tts_engine", "piper")} error={type(exc).__name__}',file=sys.stderr,flush=True)
                continue
            playback_started=time.perf_counter()
            if not self.engine:
                log_voice_timing('tts_complete',elapsed_ms(playback_started),'unavailable')
                if is_preview:
                    self.preview_error.emit(str(voice or ''),'PlayerAusente')
                else:
                    self.speech_error.emit('O ffplay é necessário para reproduzir a voz da Aurora.')
                self.speaking.emit(False); self.drained.emit(); continue
            outcome='ok'
            self.active=True; self.speaking.emit(True)
            try:
                selected_engine=engine or self.cfg.get('tts_engine','piper')
                selected_voice = voice or self.cfg.get('tts_voice')
                if selected_engine != 'piper':
                    raise ValueError('Motor de voz local desconhecido.')
                self._stream_piper(text,generation,selected_voice,
                                   pitch=pitch if is_preview else None,
                                   speed=speed if is_preview else None)
            except Exception as exc:
                outcome='error'
                if self.running and generation==self.cancel_generation and is_preview:
                    kind=type(exc).__name__
                    print(f'[voice] preview_failed engine={engine or self.cfg.get("tts_engine", "piper")} voice={voice or self.cfg.get("tts_voice", "")} error={kind}',file=sys.stderr,flush=True)
                    self.preview_error.emit(str(voice or ''),kind)
                elif self.running and generation==self.cancel_generation:
                    kind=type(exc).__name__
                    print(f'[voice] synthesis_failed engine={engine or self.cfg.get("tts_engine", "piper")} error={kind}',file=sys.stderr,flush=True)
                    self.speech_error.emit('Não consegui gerar a voz local selecionada. Confira se o modelo está instalado.')
            finally:
                self.current_player=None
                log_voice_timing('tts_complete',elapsed_ms(playback_started),outcome)
            self.playing=False; self.active=False; self.speaking.emit(False)
            if self.q.empty() and self._deferred_item is None: self.drained.emit()
    def stop(self):
        self.running=False
        self.interrupt()
    def interrupt(self):
        self.cancel_generation+=1
        while True:
            try: self.q.get_nowait()
            except queue.Empty: break
        self._deferred_item=None
        player=self.current_player
        if player:
            try:
                if player.returncode is None: player.kill()
            except Exception: pass
