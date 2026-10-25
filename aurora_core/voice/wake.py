# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from array import array
import json, queue, re, sys, threading, time
import math
from concurrent.futures import Future, TimeoutError as FutureTimeout
from ..config import VOSK_PATH
from ..system.files import normalize_words
from ..system.text import strip_wake_word
from .profile import matches as profile_matches

SAMPLE_RATE=16000
MIC_BLOCK_FRAMES=1600  # 100 ms: lower orb feedback latency while preserving audio windows.

def wake_name_words(name):
    value=' '.join(str(name or '').split())
    if not re.fullmatch(r"[^\W\d_]+(?:\s+[^\W\d_]+){0,3}",value,flags=re.UNICODE):
        return ()
    words=re.findall(r"[^\W\d_]+",value,flags=re.UNICODE)
    if not 1<=len(words)<=4:
        return ()
    return tuple(word.casefold() for word in words)

def wake_name_supported(name,model):
    """Check a custom wake phrase against a Vosk small-model vocabulary."""
    words=wake_name_words(name)
    find_word=getattr(model,'vosk_model_find_word',None)
    if not words or not callable(find_word): return False
    # Vosk returns -1 for an unknown token.  ``bool(-1)`` is True in Python,
    # so a truthiness check silently accepted every custom wake name and
    # skipped the local enrollment screen.
    try:
        def present(word):
            value=find_word(word)
            # Keep compatibility with lightweight test doubles that return a
            # boolean, while treating Vosk's integer -1 as missing.
            if isinstance(value,bool): return value
            return int(value) >= 0
        return all(present(word) for word in words)
    except (TypeError, ValueError):
        return False

def wake_grammar_phrases(name):
    value=' '.join(str(name or 'Aurora').split()) or 'Aurora'
    return [value,f'ei {value}',f'olá {value}']

class LocalVoice(QThread):
    transcript=Signal(str); status=Signal(str); unavailable=Signal(str); wake=Signal(); cancel_control=Signal(); barge_in=Signal(); audio_level=Signal(float)
    def __init__(self,cfg):
        super().__init__(); self.cfg=cfg; self.running=True; self.one_shot=threading.Event(); self.request_active=threading.Event(); self.interrupt_active=threading.Event(); self.cancel_control_active=threading.Event(); self.mobile_owned=threading.Event(); self.speaking=False; self.recognizer=None; self.mobile_audio_queue=queue.Queue(maxsize=12)
    def request_once(self): self.one_shot.set()
    def begin_request(self): self.request_active.set(); self.interrupt_active.clear()
    def end_request(self): self.request_active.clear(); self.one_shot.clear(); self.interrupt_active.clear()
    def enable_control_cancel(self): self.cancel_control_active.set()
    def disable_control_cancel(self): self.cancel_control_active.clear()
    def defer_wake_detection(self):
        """Do not accept another wake phrase until the active request ends."""
        return self.request_active.is_set() and not self.one_shot.is_set()
    @staticmethod
    def pcm_level(block):
        samples=array('h'); samples.frombytes(block)
        if sys.byteorder!='little': samples.byteswap()
        if not samples: return 0.0
        return math.sqrt(sum(sample*sample for sample in samples)/len(samples))
    @classmethod
    def normalized_audio_level(cls,block):
        """Map 16-bit microphone RMS to a quiet-safe 0..1 orb signal."""
        return min(1.0,max(0.0,(cls.pcm_level(block)-180.0)/7600.0))
    @staticmethod
    def strip_wake_word(text,assistant_name='Aurora'):
        return strip_wake_word(text,assistant_name)
    @staticmethod
    def is_final_wake_phrase(text,finalized,assistant_name='Aurora'):
        """Accept only a completed Vosk result containing the wake phrase alone."""
        if not finalized: return False
        name=normalize_words(assistant_name or 'Aurora') or 'aurora'
        return bool(re.fullmatch(r'(?:ei\s+|ola\s+)?'+re.escape(name),normalize_words(text)))
    @staticmethod
    def is_final_cancel_phrase(text,finalized):
        return finalized and normalize_words(text) in {
            'para','pare','parar','cancele','cancela','cancelar','interrompa',
            'interrompe','interromper','chega','calma para',
            'nao para','nao calma para','nao espera','pera ai','deixa pra la',
            'para agora','para com isso','corta'
        }
    def cloud_transcribe(self,sr,pcm,fallback):
        from .telemetry import elapsed_ms, log_voice_timing
        started=time.perf_counter(); outcome='google'
        try: command=self.recognizer.recognize_google(sr.AudioData(pcm,16000,2),language='pt-BR')
        except Exception:
            command=fallback; outcome='local_fallback'
        log_voice_timing('stt',elapsed_ms(started),outcome)
        command=self.strip_wake_word(command,self.cfg.get('assistant_name','Aurora'))
        if not command: command=self.strip_wake_word(fallback,self.cfg.get('assistant_name','Aurora'))
        return command
    def feed_mobile_audio(self,block,timeout=1.5):
        """Feed a short PCM frame from the paired phone to the existing local wake model."""
        if not self.mobile_owned.is_set() or not isinstance(block,bytes) or len(block)%2 or not 0<len(block)<=32000:
            return False
        result=Future()
        try: self.mobile_audio_queue.put((block,result),timeout=.2)
        except queue.Full: return False
        try: return bool(result.result(timeout=timeout))
        except FutureTimeout: return False
    def _drain_mobile_audio(self,wake_rec):
        """Vosk stays on its owning QThread; HTTP workers only enqueue PCM frames."""
        while self.running and self.mobile_owned.is_set():
            try: block,result=self.mobile_audio_queue.get(timeout=.12)
            except queue.Empty: continue
            try:
                finalized=wake_rec.AcceptWaveform(block)
                detected=False
                if finalized:
                    text=json.loads(wake_rec.Result()).get('text','').strip()
                    wake_rec.Reset()
                    detected=self.is_final_wake_phrase(text,True,self.cfg.get('assistant_name','Aurora'))
                result.set_result(detected)
                if detected:
                    self.status.emit('listening')
            except Exception as exc:
                if not result.done(): result.set_exception(exc)
        while True:
            try: _block,result=self.mobile_audio_queue.get_nowait()
            except queue.Empty: break
            if not result.done(): result.set_result(False)
    def run(self):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
            import speech_recognition as sr
            if not VOSK_PATH.exists(): raise RuntimeError(f'Modelo Vosk local não encontrado em {VOSK_PATH}')
            model=Model(str(VOSK_PATH)); rec=KaldiRecognizer(model,16000); rec.SetWords(False)
            assistant_name=' '.join(str(self.cfg.get('assistant_name','Aurora') or 'Aurora').split()) or 'Aurora'
            wake_phrases=wake_grammar_phrases(assistant_name)
            wake_rec=KaldiRecognizer(model,16000,json.dumps(wake_phrases,ensure_ascii=False)); wake_rec.SetWords(False)
            # A constrained grammar can fail for a valid custom name when a
            # small model's grammar graph is stale or under-pronounces it.
            # For custom names only, keep an unconstrained recognizer as a
            # fallback and still require an exact final phrase below.
            # Keep an unconstrained recognizer alongside the short grammar.
            # Some Vosk builds fail to finalize a one-word grammar after a
            # reconfiguration even though the same audio is recognized by the
            # normal decoder.  The exact phrase gate below still prevents
            # arbitrary speech from waking Aurora.
            wake_fallback_rec = KaldiRecognizer(model,16000)
            wake_fallback_rec.SetWords(False)
            wake_profile = self.cfg.get('wake_profile') if normalize_words(assistant_name) != 'aurora' else None
            cancel_rec=KaldiRecognizer(model,16000,'["para", "pare", "parar", "cancele", "cancela", "cancelar", "interrompa", "interrompe", "interromper", "chega", "espera", "calma", "calma para", "pera", "pera aí", "deixa", "deixa pra lá", "para agora", "para com isso", "não", "não para", "não calma para", "não espera", "corta"]'); cancel_rec.SetWords(False)
            self.recognizer=sr.Recognizer(); self.recognizer.operation_timeout=2.0
            while self.running:
                while self.running and self.mobile_owned.is_set():
                    self.status.emit('hidden')
                    self._drain_mobile_audio(wake_rec)
                wake_rec.Reset()
                if wake_fallback_rec is not None: wake_fallback_rec.Reset()
                q=queue.Queue(maxsize=8)
                def callback(data,frames,time_info,status):
                    try: q.put_nowait(bytes(data))
                    except queue.Full:
                        # Prefer fresh mic feedback over processing stale visual levels.
                        try: q.get_nowait(); q.put_nowait(bytes(data))
                        except (queue.Empty,queue.Full): pass
                with sd.RawInputStream(samplerate=SAMPLE_RATE,blocksize=MIC_BLOCK_FRAMES,dtype='int16',channels=1,callback=callback):
                    self.status.emit('hidden')
                    active=False; started=0.0; buffer=[]; wake_audio=[]; profile_checked_at=0.0; profile_cooldown_until=0.0; barge_frames=0
                    while self.running and not self.mobile_owned.is_set():
                        try: block=q.get(timeout=.25)
                        except queue.Empty: continue
                        if self.mobile_owned.is_set():
                            if active:
                                active=False; buffer=[]; wake_audio=[]; rec.Reset(); wake_rec.Reset(); self.status.emit('hidden')
                            continue
                        if not self.request_active.is_set() and active:
                            active=False; buffer=[]; wake_audio=[]; rec.Reset(); wake_rec.Reset(); self.status.emit('hidden')
                        if self.speaking:
                            # Barge-in: two consecutive energetic 100 ms blocks
                            # interrupt Edge playback and arm a fresh command.
                            # The exact wake word is not required while the
                            # current response is being interrupted.
                            if self.normalized_audio_level(block) >= .24:
                                barge_frames += 1
                            else:
                                barge_frames = 0
                            if barge_frames >= 2:
                                barge_frames = 0; self.speaking=False
                                self.one_shot.set(); self.barge_in.emit(); self.status.emit('listening')
                            if self.speaking: continue
                        else:
                            barge_frames = 0
                        if self.interrupt_active.is_set() or self.cancel_control_active.is_set():
                            finalized_cancel=cancel_rec.AcceptWaveform(block)
                            if finalized_cancel:
                                cancel_text=json.loads(cancel_rec.Result()).get('text','').strip()
                                cancel_rec.Reset()
                                if self.is_final_cancel_phrase(cancel_text,True):
                                    self.cancel_control_active.clear(); self.interrupt_active.clear(); self.cancel_control.emit()
                            # The active request owns the microphone while Aurora is
                            # processing or speaking; only the short cancel grammar
                            # is listened to until the user interrupts or it ends.
                            if self.speaking or self.interrupt_active.is_set() or self.cancel_control_active.is_set(): continue
                        if self.speaking: continue
                        cancel_rec.Reset()
                        if not active and self.defer_wake_detection(): continue
                        if not active:
                            wake_audio.append(block)
                            if len(wake_audio)>176: wake_audio=wake_audio[-176:]
                            if (wake_profile and time.monotonic() >= profile_cooldown_until
                                    and len(wake_audio) >= 12
                                    and len(wake_audio) % 8 == 0
                                    and time.monotonic() - profile_checked_at >= .45):
                                profile_checked_at = time.monotonic()
                                try:
                                    profile_pcm = b''.join(wake_audio[-12:])
                                    profile_hit = profile_matches(wake_profile, profile_pcm)
                                except Exception:
                                    profile_hit = False
                                if profile_hit:
                                    # Let feedback/TTS and the tail of the
                                    # spoken wake name leave the microphone
                                    # before looking for another activation.
                                    profile_cooldown_until = time.monotonic() + 3.0
                                    self.begin_request()
                                    self.wake.emit(); self.status.emit('listening')
                                    active=True; buffer=list(wake_audio); wake_audio=[]
                                    started=time.monotonic(); rec.Reset(); wake_rec.Reset()
                                    continue
                            if self.one_shot.is_set():
                                self.one_shot.clear(); active=True; buffer=[]; wake_audio=[]; started=time.monotonic(); self.status.emit('listening'); rec.Reset(); wake_rec.Reset(); continue
                        else:
                            buffer.append(block)
                            if len(buffer)>240: buffer=buffer[-240:]
                            self.audio_level.emit(self.normalized_audio_level(block))
                        active_rec=rec if active else wake_rec
                        finalized=active_rec.AcceptWaveform(block)
                        fallback_finalized = bool(not active and wake_fallback_rec.AcceptWaveform(block))
                        wake_finalized = finalized or fallback_finalized
                        candidate_texts=[]
                        if finalized:
                            candidate_texts.append(json.loads(active_rec.Result()).get('text','').strip())
                        if fallback_finalized:
                            candidate_texts.append(json.loads(wake_fallback_rec.Result()).get('text','').strip())
                        if not finalized:
                            if fallback_finalized:
                                text=candidate_texts[-1]
                            else:
                                text=''
                            if active and time.monotonic()-started>22:
                                active=False; buffer=[]; wake_audio=[]; rec.Reset(); wake_rec.Reset(); self.end_request(); self.status.emit('hidden')
                            if not text:
                                continue
                        else:
                            text=candidate_texts[0] if candidate_texts else ''
                        if not active and wake_fallback_rec is not None:
                            wake_fallback_rec.Reset()
                        if active:
                            if text:
                                self.audio_level.emit(0.0)
                                pcm=b''.join(buffer[-80:]); active=False; buffer=[]; wake_audio=[]; started=time.monotonic(); self.speaking=True; self.status.emit('thinking')
                                command=self.cloud_transcribe(sr,pcm,text)
                                if command and self.request_active.is_set(): self.transcript.emit(command)
                                else:
                                    active=self.request_active.is_set(); started=time.monotonic(); rec.Reset(); wake_rec.Reset(); self.speaking=False
                                    if active: self.status.emit('listening')
                            elif time.monotonic()-started>22:
                                active=False; buffer=[]; wake_audio=[]; rec.Reset(); wake_rec.Reset(); self.end_request(); self.status.emit('hidden')
                        elif text or candidate_texts:
                            if any(self.is_final_wake_phrase(candidate,True,self.cfg.get('assistant_name','Aurora'))
                                   for candidate in candidate_texts):
                                self.begin_request()
                                self.wake.emit(); self.status.emit('listening')
                                active=True; buffer=list(wake_audio); wake_audio=[]; started=time.monotonic(); rec.Reset(); wake_rec.Reset()
                            else:
                                wake_audio=[]
                if self.mobile_owned.is_set():
                    self.status.emit('hidden')

        except Exception as e:
            self.unavailable.emit(str(e)); self.status.emit('error')
    def stop(self): self.running=False
