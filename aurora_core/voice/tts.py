# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import asyncio, queue, re, shutil, subprocess, time

class Speaker(QThread):
    speaking=Signal(bool); audio_started=Signal(); drained=Signal(); speech_level=Signal(float)
    def __init__(self,cfg): super().__init__(); self.cfg=cfg; self.q=queue.Queue(); self.running=True; self.active=False; self.playing=False; self.current_player=None; self.stream_loop=None; self.stream_task=None; self.cancel_generation=0; self.engine=shutil.which('ffplay'); self.fallback=shutil.which('espeak-ng') or shutil.which('espeak')
    def say(self,text):
        text=self.clean(text)
        if text: self.q.put((text[:1800],time.perf_counter()))
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
    async def _stream_edge(self,text,generation):
        import asyncio
        import edge_tts
        from .telemetry import elapsed_ms, log_voice_timing
        started=time.perf_counter(); first_audio=False
        task=asyncio.current_task(); self.stream_loop=asyncio.get_running_loop(); self.stream_task=task
        player=None; pulse_release=None
        try:
            player=await asyncio.create_subprocess_exec(self.engine,'-nodisp','-autoexit','-loglevel','quiet','-f','mp3','-i','pipe:0',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
            self.current_player=player; started=time.perf_counter()
            async for packet in edge_tts.Communicate(text,self.cfg.get('tts_voice','pt-BR-ThalitaMultilingualNeural'),rate='+8%',boundary='WordBoundary').stream():
                if generation!=self.cancel_generation: raise RuntimeError('speech interrupted')
                if packet.get('type')=='audio' and packet.get('data'):
                    player.stdin.write(packet['data']); await player.stdin.drain()
                    if not first_audio:
                        first_audio=True
                        log_voice_timing('tts_first_audio',elapsed_ms(started))
                        self.playing=True; self.audio_started.emit()
                elif packet.get('type')=='WordBoundary':
                    # Edge can deliver text timing just ahead of the first
                    # playable audio packet. Drop those markers so the orb does
                    # not pulse before speech is actually audible.
                    if not first_audio: continue
                    self.speech_level.emit(self.word_boundary_pulse(packet.get('text','')))
                    if pulse_release and not pulse_release.done(): pulse_release.cancel()
                    duration=max(.06,min(float(packet.get('duration',0))/10_000_000*.72,.42))
                    async def release_after_word(delay):
                        try:
                            await asyncio.sleep(delay)
                            if generation==self.cancel_generation: self.speech_level.emit(.08)
                        except asyncio.CancelledError: pass
                    pulse_release=asyncio.create_task(release_after_word(duration))
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
    def run(self):
        while self.running:
            try: item=self.q.get(timeout=.3)
            except queue.Empty: continue
            if isinstance(item,tuple) and len(item)==2: text,queued_at=item
            else: text,queued_at=item,time.perf_counter()
            from .telemetry import elapsed_ms, log_voice_timing
            generation=self.cancel_generation
            log_voice_timing('tts_queue',elapsed_ms(queued_at))
            playback_started=time.perf_counter()
            if not self.engine and not self.fallback:
                log_voice_timing('tts_complete',elapsed_ms(playback_started),'unavailable')
                self.speaking.emit(False); self.drained.emit(); continue
            outcome='ok'
            self.active=True; self.speaking.emit(True)
            try:
                if self.engine:
                    import asyncio
                    asyncio.run(self._stream_edge(text,generation))
                elif self.fallback:
                    outcome='fallback'
                    self.playing=True; self.audio_started.emit()
                    self.current_player=subprocess.Popen([self.fallback,'-v','pt-br',text],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    self.current_player.wait(timeout=35)
            except asyncio.CancelledError:
                outcome='interrupted'
            except Exception:
                outcome='fallback' if self.fallback and self.running and generation==self.cancel_generation else 'error'
                if self.fallback and self.running and generation==self.cancel_generation:
                    try:
                        self.playing=True; self.audio_started.emit(); self.current_player=subprocess.Popen([self.fallback,'-v','pt-br',text],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); self.current_player.wait(timeout=35)
                    except Exception: outcome='error'
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
