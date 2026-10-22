from __future__ import annotations

import json, os, threading, unicodedata
from .config import APP_DIR

MEMORY_FILE=APP_DIR/'aurora-memory.json'

MEMORY_LOCK=threading.Lock()

def user_memory_load():
    try:
        data=json.loads(MEMORY_FILE.read_text(encoding='utf-8'))
        return [str(x)[:240] for x in data.get('preferences',[]) if str(x).strip()][:24]
    except Exception: return []

def user_memory_update(preference,forget=False):
    clean=' '.join(str(preference).split()).strip()[:240]
    if not clean: return 'Não encontrei uma preferência para salvar.'
    with MEMORY_LOCK:
        try: data=json.loads(MEMORY_FILE.read_text(encoding='utf-8'))
        except Exception: data={'preferences':[]}
        values=[str(x) for x in data.get('preferences',[]) if str(x).strip()]
        if forget:
            remaining=[x for x in values if unicodedata.normalize('NFKD',x).casefold()!=unicodedata.normalize('NFKD',clean).casefold()]
            if len(remaining)==len(values): return 'Não encontrei essa preferência salva.'
            values=remaining; message='Apaguei essa preferência da memória local.'
        else:
            key=unicodedata.normalize('NFKD',clean).casefold()
            if any(unicodedata.normalize('NFKD',x).casefold()==key for x in values): return 'Essa preferência já está salva.'
            values=(values+[clean])[-24:]; message='Salvei essa preferência localmente para as próximas conversas.'
        temporary=MEMORY_FILE.with_suffix('.tmp')
        temporary.write_text(json.dumps({'preferences':values},ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,MEMORY_FILE)
        return message
