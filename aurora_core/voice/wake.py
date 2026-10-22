from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from array import array
import json, queue, re, sys, threading, time
import math
from ..config import VOSK_PATH
from ..system.files import normalize_words
from ..system.text import strip_wake_word

class LocalVoice(QThread):
    transcript=Signal(str); status=Signal(str); unavailable=Signal(str); wake=Signal()
    def __init__(self,cfg):
        super().__init__(); self.cfg=cfg; self.running=True; self.one_shot=threading.Event(); self.request_active=threading.Event(); self.speaking=False; self.recognizer=None
    def request_once(self): self.one_shot.set()
    def begin_request(self): self.request_active.set()
    def end_request(self): self.request_active.clear(); self.one_shot.clear()
    def defer_wake_detection(self):
        """Do not accept another wake phrase until the active request ends."""
        return self.request_active.is_set() and not self.one_shot.is_set()
    @staticmethod
    def pcm_level(block):
        samples=array('h'); samples.frombytes(block)
        if sys.byteorder!='little': samples.byteswap()
        if not samples: return 0.0
        return math.sqrt(sum(sample*sample for sample in samples)/len(samples))
    @staticmethod
    def strip_wake_word(text):
        return strip_wake_word(text)
    @staticmethod
    def is_final_wake_phrase(text,finalized):
        """Accept only a completed Vosk result containing the wake phrase alone."""
        if not finalized: return False
        return bool(re.fullmatch(r'(?:ei\s+|ola\s+)?aurora',normalize_words(text)))
    def cloud_transcribe(self,sr,pcm,fallback):
        try: command=self.recognizer.recognize_google(sr.AudioData(pcm,16000,2),language='pt-BR')
        except Exception: command=fallback
        command=self.strip_wake_word(command)
        if not command: command=self.strip_wake_word(fallback)
        return command
    def run(self):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
            import speech_recognition as sr
            if not VOSK_PATH.exists(): raise RuntimeError(f'Modelo Vosk local não encontrado em {VOSK_PATH}')
            model=Model(str(VOSK_PATH)); rec=KaldiRecognizer(model,16000); rec.SetWords(False)
            wake_rec=KaldiRecognizer(model,16000,'["aurora", "ei aurora", "olá aurora"]'); wake_rec.SetWords(False)
            self.recognizer=sr.Recognizer(); self.recognizer.operation_timeout=2.0
            q=queue.Queue(maxsize=12)
            def callback(data,frames,time_info,status):
                try: q.put_nowait(bytes(data))
                except queue.Full: pass
            with sd.RawInputStream(samplerate=16000,blocksize=3200,dtype='int16',channels=1,callback=callback):
                self.status.emit('hidden')
                active=False; started=0.0; buffer=[]; wake_audio=[]
                while self.running:
                    try: block=q.get(timeout=.25)
                    except queue.Empty: continue
                    if not self.request_active.is_set() and active:
                        active=False; buffer=[]; wake_audio=[]; rec.Reset(); wake_rec.Reset(); self.status.emit('hidden')
                    if not active and self.defer_wake_detection(): continue
                    if self.speaking: continue
                    if not active:
                        wake_audio.append(block)
                        if len(wake_audio)>88: wake_audio=wake_audio[-88:]
                        if self.one_shot.is_set():
                            self.one_shot.clear(); active=True; buffer=[]; wake_audio=[]; started=time.monotonic(); self.status.emit('listening'); rec.Reset(); wake_rec.Reset(); continue
                    else:
                        buffer.append(block)
                        if len(buffer)>120: buffer=buffer[-120:]
                    active_rec=rec if active else wake_rec
                    finalized=active_rec.AcceptWaveform(block)
                    if not finalized:
                        if active and time.monotonic()-started>22:
                            active=False; buffer=[]; wake_audio=[]; rec.Reset(); wake_rec.Reset(); self.end_request(); self.status.emit('hidden')
                        continue
                    text=json.loads(active_rec.Result()).get('text','').strip()
                    if active:
                        if text:
                            pcm=b''.join(buffer[-40:]); active=False; buffer=[]; wake_audio=[]; started=time.monotonic(); self.speaking=True; self.status.emit('thinking')
                            command=self.cloud_transcribe(sr,pcm,text)
                            if command and self.request_active.is_set(): self.transcript.emit(command)
                            else:
                                active=self.request_active.is_set(); started=time.monotonic(); rec.Reset(); wake_rec.Reset(); self.speaking=False
                                if active: self.status.emit('listening')
                        elif time.monotonic()-started>22:
                            active=False; buffer=[]; wake_audio=[]; rec.Reset(); wake_rec.Reset(); self.end_request(); self.status.emit('hidden')
                    elif text:
                        if self.is_final_wake_phrase(text,finalized):
                            self.begin_request()
                            self.wake.emit(); self.status.emit('listening')
                            active=True; buffer=list(wake_audio); wake_audio=[]; started=time.monotonic(); rec.Reset(); wake_rec.Reset()
                        else:
                            wake_audio=[]
        except Exception as e:
            self.unavailable.emit(str(e)); self.status.emit('error')
    def stop(self): self.running=False
