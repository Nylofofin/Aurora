# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re
import aurora_integrations
from .apps import find_desktop_app
from .files import normalize_words
from .text import strip_wake_word
from .timers import parse_timer_command
from .agenda import parse_datetime
from .volume import spoken_percentage

def _parse_agenda_command(text: str, original: str):
    """Try to parse an agenda command from normalised text.

    Returns an action tuple or None if the text is not an agenda request.
    """
    # "lista compromissos", "agenda de hoje", "quais são meus compromissos"
    if re.search(r'\b(agenda|compromisso(?:s)?|evento(?:s)?|reuniao(?:oes)?)\b', text):
        if re.search(r'\b(cancele|cancelar|cancela|remova|remover|apague|apagar|exclua|excluir)\b', text):
            m = re.search(r'\b(?:compromisso|evento|item)?\s*(?:numero\s*)?(\d+)\b', text)
            event_id = int(m.group(1)) if m else None
            return ('agenda_cancel', {'event_id': event_id})
        if re.search(r'\b(proximo|proximos|proximo|próximo|próximos)\b', text):
            return ('agenda_nearest', {})
        if re.search(r'\b(liste|listar|lista|mostre|mostrar|verifique|quais|tenho|minha)\b', text):
            return ('agenda_list', {'days': 7})
        if re.search(r'\b(adicione|adicionar|adiciona|crie|criar|cria|agende|agendar|agenda|marque|marcar|marca|coloque|coloca)\b', text):
            ts = parse_datetime(text)
            if ts is not None:
                title = re.sub(r'^(?:por favor\s+)?(?:adicione|adicionar|adiciona|crie|criar|cria|agende|agendar|agenda|marque|marcar|marca|coloque|coloca)\s+(?:um|uma|o|a|meu|minha)?\s*', '', text, flags=re.I)
                title = re.sub(r'\s+(?:amanha|hoje|segunda|terca|quarta|quinta|sexta|sabado|domingo|dia\s+\d+|as\s+\d+|\d+[h:]\d*).*$', '', title, flags=re.I)
                title = re.sub(r'^(?:um|uma|o|a|meu|minha)\s+', '', title.strip(), flags=re.I).strip()
                if not title: title = 'Compromisso'
                return ('agenda_add', {'title': title.capitalize(), 'when': text})
            return None
    return None

def parse_local_command(prompt):
    spoken=strip_wake_word(prompt).strip()
    website=aurora_integrations.site_url_from_request(spoken)
    if website: return ('open_url',{'url':website})
    text=normalize_words(spoken)
    timer=parse_timer_command(text)
    if timer: return timer
    agenda=_parse_agenda_command(text, spoken)
    if agenda: return agenda
    if re.search(r'\b(?:diagnostico|diagnostique|verifique|cheque|teste)\b',text) and re.search(r'\b(?:aurora|assistente|instalacao)\b',text):
        return ('system_diagnostics',{})
    match=re.fullmatch(r'(?:por favor\s+)?(?:foque|focalize|traga para frente)\s+(?:a janela\s+)?["“](.+?)["”]\s+(?:do|no|da)\s+(?:aplicativo|app)\s+["“](.+?)["”]',spoken,re.I)
    if match: return ('focus_accessible_window',{'window':match.group(1),'application':match.group(2)})
    match=re.fullmatch(r'(?:por favor\s+)?(?:inspecione|liste|mostre)\s+(?:as\s+)?janelas acessíveis\s+(?:do|no|da)\s+(?:aplicativo|app)\s+["“](.+?)["”]',spoken,re.I)
    if match: return ('inspect_accessible_windows',{'application':match.group(1)})
    match=re.fullmatch(r'(?:por favor\s+)?(?:digite|escreva)\s+["“](.+?)["”]\s+no campo\s+["“](.+?)["”]\s+da janela\s+["“](.+?)["”]\s+(?:do|no|da)\s+(?:aplicativo|app)\s+["“](.+?)["”]',spoken,re.I)
    if match:
        value,field,window,application=match.groups()
        return ('type_accessible_text',{'text':value,'field':field,'window':window,'application':application})
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
    if re.search(r'\b(?:pare|parar|para|encerre|encerrar|finalize|finalizar|interrompa|interromper|interrompe)\b.*\b(?:gravacao|gravar|gravando|registro)\b',text):
        return ('obs_record',{'action':'stop'})
    if re.search(r'\b(?:grave|grava|gravar|gravacao|inicie|iniciar|comece|comecar)\b.*\b(?:tela|screen|gravacao|gravando|video)\b',text):
        return ('obs_record',{'action':'start'})
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
    match=re.search(r'^\s*(?:por favor\s+)?(?:(?:voce\s+)?(?:pode|poderia|consegue)\s+)?(?P<verb>maximizar|maximiza|maximize|minimizar|minimiza|minimize|restaure|restaurar|feche a janela|fechar a janela|fecha a janela|feche a|fechar a|fecha a)\b\s*(?P<target>.*)$',text)
    if match:
        verb=match.group('verb'); target=(match.group('target') or '').strip(' .,!?:;')
        action='maximize' if verb.startswith('maxim') else 'minimize' if verb.startswith('minim') else 'restore' if verb.startswith('restaur') else 'close'
        target=re.sub(r'^(?:(?:a|o)\s+)?janela\s+(?:(?:do|da|de)\s+)?','',target)
        target=re.sub(r'^(?:do|da|de|the)\s+','',target)
        target='' if target in ('atual','atual agora','atual por favor','atual agora por favor','janela atual','a janela atual','app atual') else target
        return ('manage_window',{'action':action,'target':target})
    match=re.search(r'^\s*(?:por favor\s+)?(?:(?:voce\s+)?(?:pode|poderia|consegue)\s+)?(?:feche|fecha|fechar|encerre|encerrar|termine|terminar|saia de|sair de)\s+(?:o |a |do |da |meu |minha |aplicativo |app |programa )?(.+?)\s*$',text)
    if match and match.group(1) not in ('a janela','janela atual'):
        target=re.sub(r'^(?:(?:app|aplicativo|programa)\s+)+','',match.group(1).strip())
        target=re.sub(r'\s+(?:por favor|pra mim|para mim)$','',target).strip(' .,!?:;')
        return ('close_application',{'application':target})
    match=re.search(r'^\s*(?:por favor\s+)?(?:(?:voce\s+)?(?:pode|poderia|consegue)\s+)?(?:abra|abrir|abre|inicie|iniciar|inicia|execute|executar)\s+(?:(?:o|a|meu|minha)\s+)?(?:(?:app|aplicativo|programa)\s+)?(.+?)\s*$',text)
    if match:
        target=match.group(1).strip(' .,!?:;')
        target=re.sub(r'^(?:por favor|pra mim|para mim)\s+','',target)
        target=re.sub(r'^(?:de|do|da)\s+','',target)
        target=re.sub(r'\s+(?:por favor|pra mim|para mim)$','',target)
        if target and not re.search(r'\b(site|link|url|endereco)\b',target):
            explicit_app=bool(re.search(r'\b(?:app|aplicativo|programa)\b',text))
            if not explicit_app and not find_desktop_app(target):
                return None
            return ('open_application',{'command':target})
    return None
