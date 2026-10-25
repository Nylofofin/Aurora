# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
import configparser, json, os, re, shlex, shutil, signal, subprocess, time
from .files import normalize_words

FLATPAK_CLOSE_CONFIRM_TIMEOUT=2.0
FLATPAK_LAUNCH_CONFIRM_TIMEOUT=2.0

def _flatpak_instance_active(app_id, flatpak=None):
    """Confirm that a Flatpak instance exists, without guessing its window."""
    flatpak = flatpak or shutil.which('flatpak')
    if not app_id or not flatpak:
        return False
    try:
        listing = subprocess.run([flatpak, 'ps', '--json'], capture_output=True,
                                 text=True, timeout=.6, check=True)
        rows = json.loads(listing.stdout or '[]')
        return any(str(item.get('application', '')).casefold() == app_id.casefold()
                   and item.get('instance') for item in rows if isinstance(item, dict))
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return False

def _flatpak_app_id(app):
    if not app:
        return None
    path = Path(app['file'])
    app_id = path.stem if '/flatpak/exports/share/applications/' in str(path) else ''
    if not app_id:
        # Some launchers are copied to a local applications directory while
        # retaining the Flatpak command in Exec. Resolve that ID generically.
        try:
            parts = shlex.split(str(app.get('exec', '')))
            for index, part in enumerate(parts):
                if part == 'run' and index + 1 < len(parts):
                    candidate = parts[index + 1]
                    if re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+', candidate):
                        app_id = candidate
                        break
        except ValueError:
            return None
    return app_id if re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+', app_id) else None

def _close_flatpak_app(app):
    """Stop matching Flatpak instances by ID without guessing sandbox PIDs."""
    app_id = _flatpak_app_id(app)
    flatpak = shutil.which('flatpak')
    if not app_id or not flatpak:
        return False
    try:
        def active_instances():
            listing = subprocess.run([flatpak, 'ps', '--json'], capture_output=True,
                                     text=True, timeout=3, check=True)
            return {str(item.get('instance', '')) for item in json.loads(listing.stdout)
                    if str(item.get('application', '')).casefold() == app_id.casefold()
                    and item.get('instance')}

        instances=active_instances()
        if not instances: return False
        for instance in instances:
            subprocess.run([flatpak, 'kill', instance], capture_output=True,
                           text=True, timeout=5, check=True)
        deadline=time.monotonic()+FLATPAK_CLOSE_CONFIRM_TIMEOUT
        while True:
            if not active_instances(): return True
            if time.monotonic()>=deadline: return False
            time.sleep(min(0.1,max(0,deadline-time.monotonic())))
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return False

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
        'roblox':['sober'],
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

def launch_application(name, *, background=False):
    query=' '.join(str(name or '').split()).strip()
    if not query: return 'Diga qual aplicativo deseja abrir.'
    app=find_desktop_app(query)
    app_id=_flatpak_app_id(app) if app else None
    flatpak=shutil.which('flatpak')
    if app_id and flatpak:
        # Launch the exported app ID directly, then inspect whether the
        # Flatpak launcher already failed. A live launcher is not proof that a
        # visible window appeared, so keep the spoken result explicit.
        try:
            env = os.environ.copy()
            # Aurora pins Qt to X11 for its own overlay. OBS's Qt platform
            # plugin aborts during startup when that override is inherited
            # through Flatpak; let OBS select the session's native backend.
            if app_id == 'com.obsproject.Studio':
                env.pop('QT_QPA_PLATFORM', None)
            arguments = ['--minimize-to-tray'] if background and app_id == 'com.obsproject.Studio' else []
            process=subprocess.Popen([flatpak,'run',app_id,*arguments],start_new_session=True,
                                     stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,env=env)
        except OSError:
            return f'Não consegui iniciar {app["name"]} pelo Flatpak.'
        poll=getattr(process,'poll',None)
        try: returncode=poll() if callable(poll) else None
        except Exception: returncode=None
        deadline=time.monotonic()+FLATPAK_LAUNCH_CONFIRM_TIMEOUT
        while time.monotonic() < deadline:
            if _flatpak_instance_active(app_id, flatpak):
                return f'Abri {app["name"]}; o processo Flatpak está ativo.'
            time.sleep(.12)
        if returncode not in (None,0):
            return f'O Flatpak encerrou com erro ao tentar iniciar {app["name"]} (código {returncode}).'
        if returncode==0:
            return f'O Flatpak aceitou abrir {app["name"]}, mas não confirmei se a janela apareceu.'
        return f'Iniciei o processo Flatpak de {app["name"]}; ainda não confirmei se a janela apareceu.'
    gio=shutil.which('gio')
    if app and gio:
        try:
            result=subprocess.run([gio,'launch',str(app['file'])],capture_output=True,
                                  text=True,timeout=4)
        except subprocess.TimeoutExpired:
            return f'O pedido para abrir {app["name"]} demorou; não confirmei se o aplicativo abriu.'
        except OSError:
            return f'Não consegui iniciar o lançador de {app["name"]}.'
        if result.returncode:
            detail=(result.stderr or '').strip()
            return f'Não consegui abrir {app["name"]}.'+(f' {detail}' if detail else '')
        return f'Solicitei a abertura de {app["name"]}; o sistema aceitou o pedido.'
    if re.fullmatch(r'[\w.+-]{1,80}',query,flags=re.UNICODE):
        executable=shutil.which(query)
        if executable:
            try:
                subprocess.Popen([executable],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError:
                return f'Não consegui iniciar {query}.'
            return f'Solicitei a abertura de {query}; o processo foi iniciado.'
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
    # Flatpak processes do not reliably expose a Wayland window to wmctrl.
    # Resolve and close their sandbox instance before attempting X11 windows.
    app = find_desktop_app(query)
    if _close_flatpak_app(app):
        return f'Fechei {app["name"]} pelo Flatpak.'
    if windows:
        try:
            rows=subprocess.run([windows,'-l','-x'],capture_output=True,text=True,timeout=3,check=True).stdout.splitlines()
            match=normalize_words(query); ids=[]
            for row in rows:
                parts=row.split(maxsplit=5)
                if len(parts)>=6 and (match in normalize_words(parts[3]) or match in normalize_words(parts[5])): ids.append(parts[0])
            if ids:
                sent=[]
                for wid in dict.fromkeys(ids):
                    try:
                        subprocess.run([windows,'-ic',wid],capture_output=True,timeout=2,check=True)
                        sent.append(wid)
                    except (OSError,subprocess.SubprocessError): pass
                if sent: return f'Enviei o comando de fechar {query}.'
        except Exception: pass
    app,names=process_names_for_app(query)
    normalized_names = {value.casefold() for value in names}
    matched=[]
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            pid=int(proc.name)
            if pid in (os.getpid(),os.getppid()): continue
            comm=(proc/'comm').read_text().strip()
            exe=Path(os.readlink(proc/'exe')).name
            if comm.casefold() in normalized_names or exe.casefold() in normalized_names: matched.append(pid)
        except (OSError,ValueError): continue
    if not matched: return f'Não encontrei uma janela ou processo ativo de {app["name"] if app else query}.'
    label=app['name'] if app else query
    sent=0; denied=0
    for pid in matched:
        try:
            os.kill(pid,signal.SIGTERM); sent+=1
        except ProcessLookupError: pass
        except PermissionError: denied+=1
    if sent:
        return f'Enviei o sinal de encerramento para {label}. O aplicativo pode pedir para salvar alterações.'
    if denied:
        return f'Não consegui encerrar {label}: o sistema negou permissão.'
    return f'{label} já não está em execução.'
