# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import gc, queue, re, shutil, time, sys
import subprocess
import importlib.util

from .catalog import voice_files

# Three steps deliver crisp, natural voice on CPU without the heavy 15-second
# latency penalty of 5 steps.
SUPERTONIC_QUALITY_STEPS = 3


def local_piper_available():
    """Whether Piper's runtime is installed (individual voices are separate)."""
    try:
        return importlib.util.find_spec('piper') is not None
    except (ImportError, ValueError, OSError):
        return False

class Speaker(QThread):
    speaking=Signal(bool); audio_started=Signal(); drained=Signal(); speech_level=Signal(float); speech_error=Signal(str); preview_error=Signal(str,str)
    def __init__(self,cfg): super().__init__(); self.cfg=cfg; self.q=queue.Queue(); self.running=True; self.active=False; self.playing=False; self.current_player=None; self.cancel_generation=0; self.engine=shutil.which('ffplay')
    def prepare(self):
        """Warm the selected local voice while the user is speaking/LLM is working."""
        if self.running:
            self.q.put(("",time.perf_counter(),None,None,False,True))
    def say(self,text):
        text=self.clean(text)
        # Keep the complete spoken answer. Piper streams synthesized audio and
        # Supertonic splits long replies into sentence-sized chunks below; the
        # old silent 1,800-character slice made the UI show words the voice
        # could never finish.
        if text: self.q.put((text,time.perf_counter(),None,None))
    def say_with_voice(self,text,voice,engine='piper',pitch=None,speed=None):
        """Queue a short preview without changing the saved voice or engine."""
        text=self.clean(text); voice=str(voice or '').strip()
        self.preview_pitch = pitch
        self.preview_speed = speed
        if text: self.q.put((text[:500],time.perf_counter(),voice or None,engine,True))
    @staticmethod
    def clean(text):
        text=str(text)
        text=re.sub(r'[\U0001F000-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF\u200d\ufe0f\u20e3]', ' ',text)
        text=re.sub(r'\b(?:(?:um|uma)\s+)?(?:emoji\s+(?:de\s+)?)?(?:rosto\s+sorridente(?:\s+com\s+olhos\s+sorridentes)?|rosto\s+sorrindo(?:\s+com\s+olhos\s+sorridentes)?|carinha\s+sorridente)\b',' ',text,flags=re.I)
        text=re.sub(r'\b(?:slightly smiling face|smiling face(?:\s+(?:with|and)\s+smiling eyes)?|smiling eyes|grinning face|face with tears of joy|rosto sorridente(?:\s+com olhos sorridentes)?)(?:\s*,\s*(?:smiling eyes|eyes smiling))?\s*(?:emoji)?\b',' ',text,flags=re.I)
        # Convert DD/MM/YYYY into natural spoken Portuguese (e.g. 26 de outubro de 2026)
        months={'01':'janeiro','02':'fevereiro','03':'março','04':'abril','05':'maio','06':'junho',
                '07':'julho','08':'agosto','09':'setembro','10':'outubro','11':'novembro','12':'dezembro'}
        def _replace_date(m):
            d, mon, y = m.group(1), m.group(2), m.group(3)
            return f'{int(d)} de {months.get(mon, mon)} de {y}'
        text=re.sub(r'\b(0?[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/((?:19|20)\d{2})\b', _replace_date, text)
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
    @staticmethod
    def _speech_chunks(text,limit=280):
        """Split near sentence boundaries using Supertonic's native chunk scale.

        The model supports chunks up to 300 characters. The previous 48-char
        limit multiplied inference calls (and denoising overhead) for ordinary
        answers without making audio start sooner: playback starts after the
        first complete chunk either way.
        """
        clauses=re.split(r'(?<=[.!?])\s+',str(text).strip())
        chunks=[]; current=''
        for clause in clauses:
            words=clause.split()
            part=''
            for word in words:
                candidate=f'{part} {word}'.strip()
                if part and len(candidate)>limit:
                    if current and len(current)+1+len(part)<=limit:
                        current=f'{current} {part}'
                    else:
                        if current: chunks.append(current)
                        current=part
                    part=word
                else:
                    part=candidate
            if not part: continue
            candidate=f'{current} {part}'.strip()
            if current and len(candidate)>limit:
                chunks.append(current); current=part
            else:
                current=candidate
        if current: chunks.append(current)
        return chunks or [str(text).strip()]
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
    def _load_supertonic_voice(self,voice_id=None):
        voice_id = str(voice_id or self.cfg.get('tts_voice', ''))
        loaded_id = getattr(self, '_supertonic_voice_id', None)
        voice = getattr(self, '_supertonic_voice', None)
        if voice is not None and loaded_id == voice_id: return voice
        from .catalog import VOICE_BY_KEY
        item = VOICE_BY_KEY.get(voice_id)
        if item is None or item.engine != 'supertonic':
            raise ValueError('Voz Supertonic local desconhecida.')
        from .telemetry import elapsed_ms
        started = time.perf_counter()
        from supertonic import TTS
        synthesizer = getattr(self, '_supertonic_tts', None)
        if synthesizer is None:
            # Three intra-op workers measured faster than two or four on the
            # reference low-end CPU, without creating parallel TTS sessions.
            synthesizer = TTS(auto_download=True,intra_op_num_threads=3,inter_op_num_threads=1)
            self._supertonic_tts = synthesizer
        style = synthesizer.get_voice_style(voice_name=item.model_voice)
        self._supertonic_voice_id = voice_id
        self._supertonic_voice = (synthesizer, style)
        from .telemetry import log_voice_timing
        log_voice_timing('tts_model_load',elapsed_ms(started))
        return synthesizer, style

    def _stream_piper(self,text,generation,voice_id=None,pitch=None,speed=None):
        """Generate and play sentence chunks locally; no text leaves this machine."""
        from .telemetry import elapsed_ms, log_voice_timing
        started=time.perf_counter(); first_audio=False; player=None
        voice=self._load_piper_voice(voice_id)
        current_pitch = float(pitch if pitch is not None else self.cfg.get('tts_pitch', 1.0))
        current_speed = float(speed if speed is not None else self.cfg.get('tts_speed', 1.0))
        sr = voice.config.sample_rate
        ffplay_cmd = [self.engine,'-nodisp','-autoexit','-loglevel','quiet',
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
            if player.wait(timeout=60)!=0: raise RuntimeError('ffplay failed')
        except BaseException:
            if player is not None and player.poll() is None: player.kill(); player.wait()
            raise
        finally:
            self.speech_level.emit(0.0)
            if player is not None and self.current_player is player: self.current_player=None
    def _stream_supertonic(self,text,generation,voice_id=None):
        """Synthesize in short local chunks so playback starts before the full reply."""
        from .telemetry import elapsed_ms, log_voice_timing
        started = time.perf_counter(); first_audio = False; player = None
        synthesizer, style = self._load_supertonic_voice(voice_id)
        import numpy as np
        try:
            player = subprocess.Popen([self.engine,'-nodisp','-autoexit','-loglevel','quiet',
                '-f','f32le','-ar',str(synthesizer.sample_rate),'-ch_layout','mono','-i','pipe:0'],
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.current_player = player
            total_synthesis_ms=0
            for chunk in self._speech_chunks(text):
                synthesis_started=time.perf_counter()
                # Five denoising steps balance voice quality and response time.
                wav, _duration = synthesizer.synthesize(
                    chunk, voice_style=style,
                    total_steps=SUPERTONIC_QUALITY_STEPS, lang='pt')
                total_synthesis_ms+=elapsed_ms(synthesis_started)
                if generation != self.cancel_generation: raise RuntimeError('speech interrupted')
                pcm = np.asarray(wav, dtype=np.float32).reshape(-1)
                if pcm.size == 0: continue
                player.stdin.write(pcm.tobytes()); player.stdin.flush()
                if not first_audio:
                    first_audio=True
                    log_voice_timing('tts_first_audio',elapsed_ms(started))
                    self.playing = True; self.audio_started.emit()
                self.speech_level.emit(.42)
            log_voice_timing('tts_synthesis',total_synthesis_ms)
            if not first_audio: raise RuntimeError('Supertonic retornou áudio vazio.')
            if player.stdin and not player.stdin.closed: player.stdin.close()
            if player.wait(timeout=60) != 0: raise RuntimeError('ffplay failed')
        except BaseException:
            if player is not None and player.poll() is None: player.kill(); player.wait()
            raise
        finally:
            self.speech_level.emit(0.0)
            if player is not None and self.current_player is player: self.current_player=None
    def run(self):
        while self.running:
            try: item=self.q.get(timeout=.3)
            except queue.Empty: continue
            voice=None; engine=None; is_preview=False; is_warmup=False; pitch=None; speed=None
            if isinstance(item,tuple) and len(item)>=8: text,queued_at,voice,engine,is_preview,is_warmup,pitch,speed=item[:8]
            elif isinstance(item,tuple) and len(item)==6: text,queued_at,voice,engine,is_preview,is_warmup=item
            elif isinstance(item,tuple) and len(item)==5: text,queued_at,voice,engine,is_preview=item
            elif isinstance(item,tuple) and len(item)==4: text,queued_at,voice,engine=item
            elif isinstance(item,tuple) and len(item)==3: text,queued_at,voice=item
            elif isinstance(item,tuple) and len(item)==2: text,queued_at=item
            else: text,queued_at=item,time.perf_counter()
            from .telemetry import elapsed_ms, log_voice_timing
            generation=self.cancel_generation
            log_voice_timing('tts_queue',elapsed_ms(queued_at))
            if is_warmup:
                try:
                    if self.cfg.get('tts_engine','piper')=='supertonic':
                        self._load_supertonic_voice(self.cfg.get('tts_voice'))
                    else:
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
                effective_pitch = getattr(self, 'preview_pitch', None) if is_preview else None
                effective_speed = getattr(self, 'preview_speed', None) if is_preview else None
                if selected_engine == 'piper':
                    try:
                        self._stream_piper(text,generation,selected_voice,pitch=effective_pitch,speed=effective_speed)
                    except TypeError:
                        self._stream_piper(text,generation,selected_voice)
                elif selected_engine == 'supertonic':
                    self._stream_supertonic(text,generation,selected_voice)
                else:
                    raise ValueError('Motor de voz local desconhecido.')
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
            if self.q.empty(): self.drained.emit()
    def stop(self):
        self.running=False
        self.interrupt()
    def interrupt(self):
        self.cancel_generation+=1
        while True:
            try: self.q.get_nowait()
            except queue.Empty: break
        player=self.current_player
        if player:
            try:
                if player.returncode is None: player.kill()
            except Exception: pass
