# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re, shutil, subprocess

def _run_wpctl(wpctl,*args):
    try:
        return subprocess.run([wpctl,*args],capture_output=True,text=True,timeout=3)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess([wpctl,*args],124,stdout='',stderr='tempo esgotado')
    except OSError as exc:
        return subprocess.CompletedProcess([wpctl,*args],127,stdout='',stderr=str(exc))

def control_volume(action,value=5):
    wpctl=shutil.which('wpctl')
    if not wpctl: return 'Não encontrei o wpctl do PipeWire para ajustar o volume.'
    action=str(action).casefold()
    if action not in ('status','mute','unmute','set','up','down'): return 'Ação de volume desconhecida.'
    if action=='status':
        result=_run_wpctl(wpctl,'get-volume','@DEFAULT_AUDIO_SINK@')
        if result.returncode: return 'Não consegui consultar o volume: '+result.stderr.strip()
        match=re.search(r'Volume:\s*([0-9.]+)',result.stdout)
        if not match: return 'Não consegui interpretar o volume informado pelo PipeWire.'
        percent=round(float(match.group(1))*100)
        state='; som silenciado' if '[MUTED]' in result.stdout else ''
        amplified='; acima de 100%' if percent>100 else ''
        return f'Volume do PC: {percent}%{amplified}{state}.'
    if action in ('mute','unmute'):
        result=_run_wpctl(wpctl,'set-mute','@DEFAULT_AUDIO_SINK@','1' if action=='mute' else '0')
        if result.returncode: return 'Não consegui mudar o mudo: '+result.stderr.strip()
        return 'Som do PC silenciado.' if action=='mute' else 'Som do PC reativado.'
    try: value=max(0,min(100,int(value or 0)))
    except (TypeError,ValueError): return 'Diga um percentual inteiro para ajustar o volume.'
    if action=='set': level=f'{value}%'
    elif action=='up':
        try:
            result=_run_wpctl(wpctl,'get-volume','@DEFAULT_AUDIO_SINK@')
            if result.returncode:
                return 'Não consegui ler o volume atual; não vou aumentá-lo: '+result.stderr.strip()
            match=re.search(r'Volume:\s*([0-9.]+)',result.stdout)
            if not match: return 'Não consegui ler o volume atual; não vou aumentá-lo sem essa confirmação.'
            current=float(match.group(1))
        except (subprocess.SubprocessError, ValueError) as exc:
            detail=getattr(exc,'stderr','') or str(exc)
            return 'Não consegui ler o volume atual; não vou aumentá-lo: '+detail.strip()
        if current>=1.0: return 'O volume já está em 100% ou acima; não vou aumentá-lo mais.'
        target=min(1.0,current+max(1,value)/100)
        level=f'{target:.3f}'
    elif action=='down': level=f'{max(1,value)}%-'
    result=_run_wpctl(wpctl,'set-volume','@DEFAULT_AUDIO_SINK@',level)
    return f'Volume ajustado para {value}%.' if action=='set' and result.returncode==0 else f'Volume aumentado para {round(target*100)}%.' if action=='up' and result.returncode==0 else f'Volume reduzido em {value}%.' if action=='down' and result.returncode==0 else 'Não consegui ajustar o volume: '+result.stderr.strip()

def spoken_percentage(text):
    digits=re.search(r'\b(\d{1,3})(?:\s*%|\s+por cento)',text)
    if not digits: digits=re.search(r'\b(?:para|pra|em|ate)\s+(\d{1,3})\b',text)
    if digits: return min(100,int(digits.group(1)))
    units={'zero':0,'um':1,'uma':1,'dois':2,'duas':2,'tres':3,'quatro':4,'cinco':5,'seis':6,'sete':7,'oito':8,'nove':9,'dez':10,'onze':11,'doze':12,'treze':13,'quatorze':14,'catorze':14,'quinze':15,'dezesseis':16,'dezessete':17,'dezoito':18,'dezenove':19}
    tens={'vinte':20,'trinta':30,'quarenta':40,'cinquenta':50,'sessenta':60,'setenta':70,'oitenta':80,'noventa':90}
    words='|'.join(sorted([*units,*tens],key=len,reverse=True))
    match=re.search(r'\b('+words+r')(?:\s+e\s+('+ '|'.join(sorted((word for word,value in units.items() if 0<value<10),key=len,reverse=True))+r'))?\s+por cento\b',text)
    if not match: return None
    first=match.group(1); value=tens.get(first,units.get(first,0))
    if match.group(2): value+=units[match.group(2)]
    return min(100,value)
