from __future__ import annotations

from pathlib import Path
import asyncio, base64, concurrent.futures, configparser, html, json, os, platform, queue, re, shlex, shutil, signal, subprocess, sys, threading, time, urllib.error, urllib.request, unicodedata

from .files import normalize_words

def desktop_app_entries():
    directories=(Path.home()/'.local/share/applications',Path('/usr/local/share/applications'),Path('/usr/share/applications'),Path.home()/'.local/share/flatpak/exports/share/applications',Path('/var/lib/flatpak/exports/share/applications'),Path('/var/lib/snapd/desktop/applications'))
    for directory in directories:
        if not directory.is_dir(): continue
        for file in sorted(directory.glob('*.desktop')):
            parser=configparser.ConfigParser(interpolation=None,strict=False)
            try: parser.read(file,encoding='utf-8'); entry=parser['Desktop Entry']
            except Exception: continue
            if entry.get('Type','Application')!='Application' or entry.get('NoDisplay','false').casefold()=='true': continue
            yield {'file':file,'name':entry.get('Name',file.stem),'exec':entry.get('Exec',''),'class':entry.get('StartupWMClass','')}

def find_desktop_app(query):
    name=normalize_words(query)
    aliases={
        'browser':['navegador padrao','firefox','chromium','google chrome','brave'],
        'navegador':['navegador padrao','firefox','chromium','google chrome','brave'],
        'terminal':['terminal','console','ptyxis','gnome terminal'],
        'arquivos':['files','nautilus','gerenciador de arquivos'],
        'gerenciador de arquivos':['files','nautilus','gerenciador de arquivos'],
    }
    wanted=aliases.get(name,[name]); entries=list(desktop_app_entries())
    preferred=[]
    if name in ('browser','navegador'):
        xdg=shutil.which('xdg-settings')
        if xdg:
            try:
                default=subprocess.run([xdg,'get','default-web-browser'],capture_output=True,text=True,timeout=2).stdout.strip()
                preferred=[e for e in entries if e['file'].name.casefold()==default.casefold()]
            except Exception: pass
    if preferred: return preferred[0]
    ranked=[]
    for app in entries:
        title=normalize_words(app['name']); stem=normalize_words(app['file'].stem); exec_cmd=normalize_words(app['exec'])
        score=max((100 if target in (title,stem) else 80 if target and (target in title or title in target) else 0 for target in wanted),default=0)
        if name in ('browser','navegador') and re.search(r'firefox|chromium|chrome|brave|browser',title+' '+stem+' '+exec_cmd): score=max(score,40)
        if name in ('terminal',) and re.search(r'terminal|console|ptyxis',title+' '+stem+' '+exec_cmd): score=max(score,35)
        if name in ('arquivos','gerenciador de arquivos') and re.search(r'nautilus|file manager|files',title+' '+stem+' '+exec_cmd): score=max(score,35)
        if score: ranked.append((score,app))
    return max(ranked,key=lambda x:x[0])[1] if ranked else None

def launch_application(name):
    query=' '.join(str(name or '').split()).strip()
    if not query: return 'Diga qual aplicativo deseja abrir.'
    app=find_desktop_app(query)
    gio=shutil.which('gio')
    if app and gio:
        subprocess.Popen([gio,'launch',str(app['file'])],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return f'Abri {app["name"]}.'
    if re.fullmatch(r'[\w.+-]{1,80}',query,flags=re.UNICODE):
        executable=shutil.which(query)
        if executable:
            subprocess.Popen([executable],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return f'Abri {query}.'
    return f'Não encontrei um aplicativo instalado chamado “{query}”.'

def process_names_for_app(query):
    app=find_desktop_app(query); values=set()
    if app:
        values.update((Path(app['file']).stem,Path(app['class']).name if app['class'] else ''))
        try:
            parts=shlex.split(app['exec'])
            parts=[part for part in parts if not part.startswith('%')]
            if parts:
                command=Path(parts[0]).name
                if command=='env':
                    command=next((Path(x).name for x in parts[1:] if '=' not in x),command)
                if command not in ('flatpak','snap','env','/usr/bin/env'): values.add(command)
        except Exception: pass
    if re.fullmatch(r'[\w.+-]{1,80}',str(query).strip(),flags=re.UNICODE): values.add(Path(str(query).strip()).name)
    return app,{value for value in values if value and re.fullmatch(r'[\w.+-]{1,100}',value,flags=re.UNICODE)}

def close_application(name):
    query=' '.join(str(name or '').split()).strip()
    if not query: return 'Diga qual aplicativo deseja fechar.'
    windows=shutil.which('wmctrl')
    if windows:
        try:
            rows=subprocess.run([windows,'-l','-x'],capture_output=True,text=True,timeout=3,check=True).stdout.splitlines()
            match=normalize_words(query); ids=[]
            for row in rows:
                parts=row.split(maxsplit=5)
                if len(parts)>=6 and (match in normalize_words(parts[3]) or match in normalize_words(parts[5])): ids.append(parts[0])
            if ids:
                for wid in ids: subprocess.run([windows,'-ic',wid],capture_output=True,timeout=2)
                return f'Enviei o comando de fechar {query}.'
        except Exception: pass
    app,names=process_names_for_app(query)
    matched=[]
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            pid=int(proc.name)
            if pid in (os.getpid(),os.getppid()): continue
            comm=(proc/'comm').read_text().strip()
            exe=Path(os.readlink(proc/'exe')).name
            if comm in names or exe in names: matched.append(pid)
        except (OSError,ValueError): continue
    if not matched: return f'Não encontrei uma janela ou processo ativo de {app["name"] if app else query}.'
    for pid in matched:
        try: os.kill(pid,signal.SIGTERM)
        except ProcessLookupError: pass
        except PermissionError: pass
    label=app['name'] if app else query
    return f'Enviei o sinal de encerramento para {label}. O aplicativo pode pedir para salvar alterações.'
