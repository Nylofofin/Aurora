# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json, os, threading, unicodedata
from .config import APP_DIR

MEMORY_FILE=APP_DIR/'aurora-memory.json'

MEMORY_LOCK=threading.Lock()

def user_memory_load():
    try:
        os.chmod(MEMORY_FILE,0o600)
        data=json.loads(MEMORY_FILE.read_text(encoding='utf-8'))
        return [str(x)[:240] for x in data.get('preferences',[]) if str(x).strip()][:24]
    except Exception: return []

def user_memory_update(preference,forget=False):
    clean=' '.join(str(preference).split()).strip()[:240]
    if not clean: return 'Não encontrei uma preferência para salvar.'
    with MEMORY_LOCK:
        try:
            os.chmod(MEMORY_FILE,0o600)
            data=json.loads(MEMORY_FILE.read_text(encoding='utf-8'))
        except FileNotFoundError:
            data={'preferences':[]}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError('Não consegui ler a memória local; o arquivo foi preservado.') from exc
        if not isinstance(data,dict) or not isinstance(data.get('preferences',[]),list):
            raise ValueError('A memória local está inválida; o arquivo foi preservado.')
        values=[str(x) for x in data.get('preferences',[]) if str(x).strip()]
        if forget:
            remaining=[x for x in values if unicodedata.normalize('NFKD',x).casefold()!=unicodedata.normalize('NFKD',clean).casefold()]
            if len(remaining)==len(values): return 'Não encontrei essa preferência salva.'
            values=remaining; message='Apaguei essa preferência da memória local.'
        else:
            key=unicodedata.normalize('NFKD',clean).casefold()
            if any(unicodedata.normalize('NFKD',x).casefold()==key for x in values): return 'Essa preferência já está salva.'
            values=(values+[clean])[-24:]; message='Salvei essa preferência localmente para as próximas conversas.'
        MEMORY_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        temporary=MEMORY_FILE.with_suffix('.tmp')
        try: os.chmod(temporary,0o600)
        except FileNotFoundError: pass
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as output:
                json.dump({'preferences':values},output,ensure_ascii=False,indent=2)
                output.flush(); os.fsync(output.fileno())
        except Exception:
            try: os.close(fd)
            except OSError: pass
            raise
        os.replace(temporary,MEMORY_FILE)
        os.chmod(MEMORY_FILE,0o600)
        return message
