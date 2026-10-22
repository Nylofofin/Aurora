from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import asyncio, queue, re, shutil, subprocess

class Speaker(QThread):
    speaking=Signal(bool); audio_started=Signal(); drained=Signal()
    def __init__(self,cfg): super().__init__(); self.cfg=cfg; self.q=queue.Queue(); self.running=True; self.active=False; self.playing=False; self.current_player=None; self.stream_loop=None; self.stream_task=None; self.cancel_generation=0; self.engine=shutil.which('ffplay'); self.fallback=shutil.which('espeak-ng') or shutil.which('espeak')
    def say(self,text):
        text=self.clean(text)
        if text: self.q.put(text[:1800])
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
    async def _stream_edge(self,text,generation):
        import asyncio
        import edge_tts
        task=asyncio.current_task(); self.stream_loop=asyncio.get_running_loop(); self.stream_task=task
        player=await asyncio.create_subprocess_exec(self.engine,'-nodisp','-autoexit','-loglevel','quiet','-f','mp3','-i','pipe:0',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        self.current_player=player
        started=False
        try:
            async for packet in edge_tts.Communicate(text,self.cfg.get('tts_voice','pt-BR-ThalitaMultilingualNeural'),rate='+8%').stream():
                if generation!=self.cancel_generation: raise RuntimeError('speech interrupted')
                if packet.get('type')=='audio' and packet.get('data'):
                    player.stdin.write(packet['data']); await player.stdin.drain()
                    if not started: started=True; self.playing=True; self.audio_started.emit()
            player.stdin.close()
            try: await player.stdin.wait_closed()
            except Exception: pass
            await asyncio.wait_for(player.wait(),timeout=55)
        except BaseException:
            if player.returncode is None:
                player.kill(); await player.wait()
            raise
        finally:
            if self.current_player is player: self.current_player=None
            if self.stream_task is task: self.stream_task=None; self.stream_loop=None
    def run(self):
        while self.running:
            try: text=self.q.get(timeout=.3)
            except queue.Empty: continue
            if not self.engine and not self.fallback:
                self.speaking.emit(False); self.drained.emit(); continue
            generation=self.cancel_generation
            self.active=True; self.speaking.emit(True)
            try:
                if self.engine:
                    import asyncio
                    asyncio.run(self._stream_edge(text,generation))
                elif self.fallback:
                    self.playing=True; self.audio_started.emit()
                    self.current_player=subprocess.Popen([self.fallback,'-v','pt-br',text],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    self.current_player.wait(timeout=35)
            except asyncio.CancelledError:
                pass
            except Exception:
                if self.fallback and self.running and generation==self.cancel_generation:
                    try:
                        self.playing=True; self.audio_started.emit(); self.current_player=subprocess.Popen([self.fallback,'-v','pt-br',text],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); self.current_player.wait(timeout=35)
                    except Exception: pass
            finally:
                self.current_player=None
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
