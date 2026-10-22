from __future__ import annotations

import asyncio, base64, concurrent.futures, configparser, html, json, os, platform, queue, re, shlex, shutil, signal, subprocess, sys, threading, time, urllib.error, urllib.request, unicodedata

def control_volume(action,value=5):
    wpctl=shutil.which('wpctl')
    if not wpctl: return 'Não encontrei o wpctl do PipeWire para ajustar o volume.'
    action=str(action).casefold(); value=max(0,min(100,int(value or 0)))
    if action=='status':
        result=subprocess.run([wpctl,'get-volume','@DEFAULT_AUDIO_SINK@'],capture_output=True,text=True,timeout=3)
        return 'Volume do PC: '+result.stdout.strip().replace('Volume: ','')+(f' {result.stderr.strip()}' if result.returncode else '')
    if action in ('mute','unmute'):
        result=subprocess.run([wpctl,'set-mute','@DEFAULT_AUDIO_SINK@','1' if action=='mute' else '0'],capture_output=True,text=True,timeout=3)
        if result.returncode: return 'Não consegui mudar o mudo: '+result.stderr.strip()
        return 'Som do PC silenciado.' if action=='mute' else 'Som do PC reativado.'
    if action=='set': level=f'{value}%'
    elif action=='up':
        try:
            current=subprocess.run([wpctl,'get-volume','@DEFAULT_AUDIO_SINK@'],capture_output=True,text=True,timeout=3,check=True).stdout
            if float(re.search(r'Volume:\s*([0-9.]+)',current).group(1))>=1.0: return 'O volume já está em 100% ou acima; não vou aumentá-lo mais.'
        except Exception: pass
        level=f'{max(1,value)}%+'
    elif action=='down': level=f'{max(1,value)}%-'
    else: return 'Ação de volume desconhecida.'
    result=subprocess.run([wpctl,'set-volume','@DEFAULT_AUDIO_SINK@',level],capture_output=True,text=True,timeout=3)
    return f'Volume ajustado para {value}%.' if action=='set' and result.returncode==0 else f'Volume aumentado em {value}%.' if action=='up' and result.returncode==0 else f'Volume reduzido em {value}%.' if action=='down' and result.returncode==0 else 'Não consegui ajustar o volume: '+result.stderr.strip()

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
