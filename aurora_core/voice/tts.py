# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import asyncio, queue, re, shutil, time
import subprocess
import importlib.util

from ..config import PIPER_MODEL_PATH


def local_piper_available():
    """Whether the local runtime and the pinned Brazilian voice are present."""
    try:
        return (importlib.util.find_spec('piper') is not None and
                PIPER_MODEL_PATH.is_file() and
                PIPER_MODEL_PATH.with_suffix('.onnx.json').is_file())
    except (ImportError, ValueError, OSError):
        return False

class Speaker(QThread):
    speaking=Signal(bool); audio_started=Signal(); drained=Signal(); speech_level=Signal(float); speech_error=Signal(str)
    def __init__(self,cfg): super().__init__(); self.cfg=cfg; self.q=queue.Queue(); self.running=True; self.active=False; self.playing=False; self.current_player=None; self.stream_loop=None; self.stream_task=None; self.cancel_generation=0; self.engine=shutil.which('ffplay')
    def say(self,text):
        text=self.clean(text)
        if text: self.q.put((text[:1800],time.perf_counter(),None,None))
    def say_with_voice(self,text,voice,engine='edge'):
        """Queue a short preview without changing the saved voice or engine."""
        text=self.clean(text); voice=str(voice or '').strip()
        if text: self.q.put((text[:500],time.perf_counter(),voice or None,engine))
    @staticmethod
    def clean(text):
        text=str(text)
        text=re.sub(r'[\U0001F000-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF\u200d\ufe0f\u20e3]', ' ',text)
        text=re.sub(r'\b(?:(?:um|uma)\s+)?(?:emoji\s+(?:de\s+)?)?(?:rosto\s+sorridente(?:\s+com\s+olhos\s+sorridentes)?|rosto\s+sorrindo(?:\s+com\s+olhos\s+sorridentes)?|carinha\s+sorridente)\b',' ',text,flags=re.I)
        text=re.sub(r'\b(?:slightly smiling face|smiling face(?:\s+(?:with|and)\s+smiling eyes)?|smiling eyes|grinning face|face with tears of joy|rosto sorridente(?:\s+com olhos sorridentes)?)(?:\s*,\s*(?:smiling eyes|eyes smiling))?\s*(?:emoji)?\b',' ',text,flags=re.I)
        text=re.sub(r'\s+([,.;:!?])',r'\1',text)
        text=re.sub(r'[,;:]+([.!?])',r'\1',text).strip(' ,;:')
        text=re.sub(r'([.!?])(?:\s*[.!?])+',r'\1',text)
        return ' '.join(text.split())
    @staticmethod
    def word_boundary_pulse(text):
        letters=sum(char.isalnum() for char in str(text))
        return min(.88,.28+min(letters,12)*.045) if letters else .18
    async def _stream_edge(self,text,generation,voice=None):
        import asyncio
        import edge_tts
        from .telemetry import elapsed_ms, log_voice_timing
        started=time.perf_counter(); first_audio=False
        task=asyncio.current_task(); self.stream_loop=asyncio.get_running_loop(); self.stream_task=task
        player=None; pulse_release=None
        try:
            player=await asyncio.create_subprocess_exec(self.engine,'-nodisp','-autoexit','-loglevel','quiet','-f','mp3','-i','pipe:0',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
            self.current_player=player; started=time.perf_counter()
            selected_voice=voice or self.cfg.get('tts_voice','pt-BR-ThalitaMultilingualNeural')
            async for packet in edge_tts.Communicate(text,selected_voice,rate='+8%',connect_timeout=20,receive_timeout=120).stream():
                if generation!=self.cancel_generation: raise RuntimeError('speech interrupted')
                if packet.get('type')=='audio' and packet.get('data'):
                    player.stdin.write(packet['data']); await player.stdin.drain()
                    if not first_audio:
                        first_audio=True
                        log_voice_timing('tts_first_audio',elapsed_ms(started))
                        self.playing=True; self.audio_started.emit()
                    self.speech_level.emit(.42)
                    if pulse_release and not pulse_release.done(): pulse_release.cancel()
                    async def release_audio_pulse():
                        try:
                            await asyncio.sleep(.24)
                            if generation==self.cancel_generation: self.speech_level.emit(.08)
                        except asyncio.CancelledError: pass
                    pulse_release=asyncio.create_task(release_audio_pulse())
            player.stdin.close()
            try: await player.stdin.wait_closed()
            except Exception: pass
            await asyncio.wait_for(player.wait(),timeout=55)
        except BaseException:
            if player is not None and player.returncode is None:
                player.kill(); await player.wait()
            raise
        finally:
            if pulse_release and not pulse_release.done(): pulse_release.cancel()
            self.speech_level.emit(0.0)
            if player is not None and self.current_player is player: self.current_player=None
            if self.stream_task is task: self.stream_task=None; self.stream_loop=None
    async def _stream_edge_retry(self,text,generation,voice=None):
        """Retry a transient Edge failure; never silently switch to another voice."""
        try:
            await self._stream_edge(text,generation,voice)
        except Exception as first_error:
            if generation!=self.cancel_generation or not self.running:
                raise
            # Edge occasionally opens a stream but returns no audio. A short
            # retry avoids dropping a transient Edge outage.
            print(f'[voice] Edge TTS attempt failed ({type(first_error).__name__}); retrying once', flush=True)
            await asyncio.sleep(.2)
            try:
                await self._stream_edge(text,generation,voice)
            except Exception as retry_error:
                print(f'[voice] Edge TTS retry failed ({type(retry_error).__name__}); no alternate voice will be used', flush=True)
                raise
    def _load_piper_voice(self):
        voice=getattr(self,'_piper_voice',None)
        if voice is not None: return voice
        if not PIPER_MODEL_PATH.is_file() or not PIPER_MODEL_PATH.with_suffix('.onnx.json').is_file():
            raise FileNotFoundError('O modelo local Faber não está instalado; execute setup-voice.sh.')
        from piper import PiperVoice
        started=time.perf_counter()
        voice=PiperVoice.load(str(PIPER_MODEL_PATH),use_cuda=False)
        self._piper_voice=voice
        print(f'[voice-timing] stage=tts_model_load elapsed_ms={int((time.perf_counter()-started)*1000)} outcome=ok',flush=True)
        return voice
    def _stream_piper(self,text,generation):
        """Generate and play sentence chunks locally; no text leaves this machine."""
        from .telemetry import elapsed_ms, log_voice_timing
        started=time.perf_counter(); first_audio=False; player=None
        voice=self._load_piper_voice()
        try:
            player=subprocess.Popen([self.engine,'-nodisp','-autoexit','-loglevel','quiet',
                '-f','s16le','-ar',str(voice.config.sample_rate),'-ch_layout','mono','-i','pipe:0'],
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
            if player.stdin and not player.stdin.closed: player.stdin.close()
            if player.wait(timeout=60)!=0: raise RuntimeError('ffplay failed')
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
            voice=None; engine=None
            if isinstance(item,tuple) and len(item)==4: text,queued_at,voice,engine=item
            elif isinstance(item,tuple) and len(item)==3: text,queued_at,voice=item
            elif isinstance(item,tuple) and len(item)==2: text,queued_at=item
            else: text,queued_at=item,time.perf_counter()
            from .telemetry import elapsed_ms, log_voice_timing
            generation=self.cancel_generation
            log_voice_timing('tts_queue',elapsed_ms(queued_at))
            playback_started=time.perf_counter()
            if not self.engine:
                log_voice_timing('tts_complete',elapsed_ms(playback_started),'unavailable')
                self.speech_error.emit('O ffplay é necessário para reproduzir a voz da Aurora.')
                self.speaking.emit(False); self.drained.emit(); continue
            outcome='ok'
            self.active=True; self.speaking.emit(True)
            try:
                selected_engine=engine or self.cfg.get('tts_engine','edge')
                if selected_engine=='piper':
                    self._stream_piper(text,generation)
                elif selected_engine=='edge':
                    asyncio.run(self._stream_edge_retry(text,generation,voice))
                else:
                    raise ValueError('Mecanismo de voz desconhecido')
            except asyncio.CancelledError:
                outcome='interrupted'
            except Exception:
                outcome='error'
                if self.running and generation==self.cancel_generation:
                    selected_engine=engine or self.cfg.get('tts_engine','edge')
                    message=('Não consegui gerar a voz local Faber.' if selected_engine=='piper'
                             else 'Não consegui gerar a voz pelo Edge TTS.')
                    self.speech_error.emit(message)
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
        loop=self.stream_loop; task=self.stream_task
        if loop and task and not task.done():
            try: loop.call_soon_threadsafe(task.cancel)
            except RuntimeError: pass
