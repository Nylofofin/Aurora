from __future__ import annotations

import asyncio, base64, concurrent.futures, configparser, html, json, os, platform, queue, re, shlex, shutil, signal, subprocess, sys, threading, time, urllib.error, urllib.request, unicodedata
import aurora_integrations

from .apps import find_desktop_app
from .files import normalize_words
from .text import strip_wake_word
from .volume import spoken_percentage

def parse_local_command(prompt):
    website=aurora_integrations.site_url_from_request(strip_wake_word(prompt))
    if website: return ('open_url',{'url':website})
    text=normalize_words(strip_wake_word(prompt))
    if re.search(r'\b(?:e(?: depois| tambem| entao)?|depois|em seguida|entao)\s+(?:abra|abrir|abre|feche|fechar|fecha|maximize|maximizar|minimize|minimizar|aumente|aumentar|diminua|diminuir|crie|criar|salve|salvar|mude|coloque|ajuste)\b',text): return None
    if re.search(r'\b(hardware|especificacoes? (?:do|deste) (?:meu )?(?:pc|computador)|configuracoes? do sistema|componentes? do (?:meu )?(?:pc|computador)|quanto de ram|qual (?:e )?(?:meu )?(?:processador|placa de video|gpu))\b',text):
        return ('system_info',{})
    if re.search(r'\b(?:conectar|conecte|conecta|autorizar|autorize|vincular|vincule)\s+(?:o\s+)?spotify\b',text):
        return ('spotify_authorize',{})
    music=re.search(r'^\s*(?:por favor\s+)?(?:toque|toca|tocar|quero ouvir|coloque para tocar|coloca pra tocar|bote para tocar|bota pra tocar)\s+(?:a musica\s+)?(.+?)\s*$',text)
    if music:
        track=music.group(1).strip(' .,!?:;')
        if track and track not in ('uma musica','musica'):
            return ('spotify_play',{'query':track})
    if re.search(r'\b(?:tire|tira|faca|faca um|faca uma|captura|capture|print|screenshot)\b',text) and re.search(r'\b(?:print|screenshot|captura|captura de tela|tela)\b',text):
        return ('take_screenshot',{})
    if re.search(r'\b(?:pare|parar|para|encerre|encerrar|finalize|finalizar)\b.*\b(?:gravacao|gravar|gravando|registro)\b',text):
        return ('obs_record',{'action':'stop'})
    if re.search(r'\b(?:grave|grava|gravar|gravacao|inicie|iniciar|comece|comecar)\b.*\b(?:tela|screen|gravacao|gravando|video)\b',text):
        return ('obs_record',{'action':'start'})
    if re.match(r'^\s*(?:por favor\s+)?(?:abra|abrir|abre|acesse|acessar)\s+(?:(?:o|a)\s+)?(?:site|pagina|link|url|endereco)\b',text):
        target=text.split(maxsplit=1)[-1]
        target=re.sub(r'^(?:o|a)\s+','',target)
        return ('clarify_open_target',{'target':target})
    if 'volume' in text or re.search(r'\b(mudo|sem som|mute)\b',text) or ('som' in text and re.search(r'\b(silencie|silencia|ative|reative|aumente|aumentar|diminua|diminuir|baixe|baixar|volume)\b',text)):
        if re.search(r'\b(qual|quanto|mostre|verifique|consulta|consultar)\b',text) and not re.search(r'\b(aument|diminu|baix|sub|defin|coloc|ajust|silenci|mudo|reativ)',text): return ('volume_control',{'action':'status','value':0})
        if re.search(r'\b(silencie|silenciar|silencia|mudo|sem som|mute)\b',text) and ('volume' in text or 'som' in text or re.search(r'\b(mudo|sem som|mute)\b',text)): return ('volume_control',{'action':'mute','value':0})
        if re.search(r'\b(reative|reativar|ative o som|tire do mudo|desmute)\b',text): return ('volume_control',{'action':'unmute','value':0})
        value=spoken_percentage(text); amount=value is not None
        value=value if amount else 5
        if re.search(r'\b(maximo|maxima|no maximo|no talo)\b',text): return ('volume_control',{'action':'set','value':100})
        if re.search(r'\b(minimo|minima|zerado|zerada)\b',text): return ('volume_control',{'action':'set','value':0})
        if amount and re.search(r'\b(para|pra|em|ate)\b',text): return ('volume_control',{'action':'set','value':value})
        if re.search(r'\b(aument|sub|mais alto|mais forte|suba)\w*\b',text): return ('volume_control',{'action':'up','value':value})
        if re.search(r'\b(diminu|baix|mais baixo|mais fraco|reduz)\w*\b',text): return ('volume_control',{'action':'down','value':value})
        if amount or re.search(r'\b(defina|coloque|ajuste|mude|deixe)\w*\b',text): return ('volume_control',{'action':'set','value':value})
    match=re.search(r'^\s*(?:por favor\s+)?(?P<verb>maximizar|maximiza|maximize|minimizar|minimiza|minimize|restaure|restaurar|feche a janela|fechar a janela|fecha a janela|feche a|fechar a|fecha a)\b\s*(?P<target>.*)$',text)
    if match:
        verb=match.group('verb'); target=(match.group('target') or '').strip()
        action='maximize' if verb.startswith('maxim') else 'minimize' if verb.startswith('minim') else 'restore' if verb.startswith('restaur') else 'close'
        target=re.sub(r'^(?:(?:a|o)\s+)?janela\s+(?:(?:do|da|de)\s+)?','',target)
        target=re.sub(r'^(?:do|da|de|the)\s+','',target)
        target='' if target in ('atual','atual agora','atual por favor','atual agora por favor','janela atual','a janela atual','app atual') else target
        return ('manage_window',{'action':action,'target':target})
    match=re.search(r'^\s*(?:por favor\s+)?(?:feche|fecha|fechar|encerre|encerrar|termine|terminar|saia de|sair de)\s+(?:o |a |do |da |meu |minha |aplicativo |app |programa )?(.+?)\s*$',text)
    if match and match.group(1) not in ('a janela','janela atual'):
        target=re.sub(r'^(?:(?:app|aplicativo|programa)\s+)+','',match.group(1).strip())
        target=re.sub(r'\s+(?:por favor|pra mim|para mim)$','',target)
        return ('close_application',{'application':target})
    match=re.search(r'^\s*(?:por favor\s+)?(?:abra|abrir|abre|inicie|iniciar|inicia|execute|executar)\s+(?:(?:o|a|meu|minha)\s+)?(?:(?:app|aplicativo|programa)\s+)?(.+?)\s*$',text)
    if match:
        target=match.group(1).strip(' .,!?:;')
        target=re.sub(r'^(?:por favor|pra mim|para mim)\s+','',target)
        target=re.sub(r'^(?:de|do|da)\s+','',target)
        target=re.sub(r'\s+(?:por favor|pra mim|para mim)$','',target)
        if target and not re.search(r'\b(site|link|url|endereco)\b',target):
            explicit_app=bool(re.search(r'\b(?:app|aplicativo|programa)\b',text))
            if not explicit_app and not find_desktop_app(target):
                return ('clarify_open_target',{'target':target})
            return ('open_application',{'command':target})
    return None
