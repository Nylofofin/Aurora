from __future__ import annotations

import os, re, shutil, subprocess
from .apps import find_desktop_app
from .files import normalize_words

def manage_window(action,target=''):
    wmctrl=shutil.which('wmctrl'); xdotool=shutil.which('xdotool')
    action=str(action).casefold(); query=normalize_words(target)
    if action not in ('maximize','restore','minimize','close'):
        return 'Ação de janela desconhecida.'
    if query:
        app=find_desktop_app(target)
        if app:
            query_candidates=(normalize_words(app['name']),normalize_words(app['file'].stem),normalize_words(app['class']))
            query=next((candidate for candidate in query_candidates if candidate),query)
    if wmctrl:
        try:
            rows=subprocess.run([wmctrl,'-l','-x'],capture_output=True,text=True,timeout=3,check=True).stdout.splitlines()
            ids=[]
            if not query:
                xprop=shutil.which('xprop')
                if xprop:
                    active=subprocess.run([xprop,'-root','_NET_ACTIVE_WINDOW'],capture_output=True,text=True,timeout=2).stdout
                    match=re.search(r'0x[0-9a-fA-F]+',active)
                    if match: ids=[match.group(0)]
            for row in rows:
                parts=row.split(maxsplit=5)
                if len(parts)>=6 and ((query and (query in normalize_words(parts[3]) or query in normalize_words(parts[5]))) or (not query and parts[0] in ids)): ids.append(parts[0])
            if not ids: return 'Não encontrei uma janela compatível. Selecione a janela e tente “janela atual”.'
            for wid in ids:
                if action=='maximize': args=[wmctrl,'-ir',wid,'-b','add,maximized_vert,maximized_horz']
                elif action=='restore': args=[wmctrl,'-ir',wid,'-b','remove,maximized_vert,maximized_horz,hidden']
                elif action=='minimize': args=[wmctrl,'-ir',wid,'-b','add,hidden']
                elif action=='close': args=[wmctrl,'-ic',wid]
                else: return 'Ação de janela desconhecida.'
                subprocess.run(args,capture_output=True,timeout=3,check=True)
            return f'Janela {"atual" if not target else target}: {action} concluído.'
        except Exception: pass
    if xdotool and not os.environ.get('WAYLAND_DISPLAY'):
        try:
            ids=subprocess.run([xdotool,'search','--onlyvisible','--name',str(target)],capture_output=True,text=True,timeout=3,check=True).stdout.split() if target else [subprocess.run([xdotool,'getactivewindow'],capture_output=True,text=True,timeout=2,check=True).stdout.strip()]
            if not ids: return 'Não encontrei uma janela correspondente.'
            for wid in ids:
                if action=='maximize': subprocess.run([xdotool,'windowstate',wid,'--add','MAXIMIZED_VERT','--add','MAXIMIZED_HORZ'],check=True,timeout=3)
                elif action=='minimize': subprocess.run([xdotool,'windowminimize',wid],check=True,timeout=3)
                elif action=='close': subprocess.run([xdotool,'windowclose',wid],check=True,timeout=3)
                elif action=='restore': subprocess.run([xdotool,'windowstate',wid,'--remove','MAXIMIZED_VERT','--remove','MAXIMIZED_HORZ'],check=True,timeout=3)
            return f'Janela: {action} concluído.'
        except Exception: return 'Não consegui controlar essa janela pelo X11.'
    return 'Esta sessão Wayland não expõe o controle de janelas para a Aurora. Fechar aplicativos e outras ações continuam disponíveis; para maximizar/minimizar, instale wmctrl e use janelas XWayland.'
