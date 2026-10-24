# SPDX-License-Identifier: GPL-3.0-only
"""Unlock greeting and bounded, read-only local system readiness checks."""
from __future__ import annotations

from datetime import datetime
import getpass
import os
import re
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, SLOT

from . import diagnostics
from .files import normalize_words
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage


def greeting_for(moment=None, username=None):
    moment=moment or datetime.now().astimezone()
    hour=moment.hour
    greeting='Bom dia' if 5<=hour<12 else 'Boa tarde' if 12<=hour<18 else 'Boa noite'
    name=' '.join(str(username or getpass.getuser()).split())
    return f'{greeting}, {name}.' if name else f'{greeting}.'


def confirmation_intent(text):
    """Return yes/no only for clear spoken answers; ambiguous speech is None."""
    value=re.sub(r'[^a-z0-9]+',' ',normalize_words(text)).strip()
    if value in {'sim','sim quero','quero sim','quero','pode','pode atualizar','pode instalar','atualize','atualiza','confirmo','confirmado','manda ver'}:
        return True
    if value in {'nao','nao quero','agora nao','nao agora','depois','cancela','cancelar','pare','para','nao atualize','nao instale','nao reinicie','nao reiniciar','nao deixa para depois','nao obrigado','nao obrigada'}:
        return False
    return None


def _run(argv, timeout, runner=subprocess.run):
    env={**os.environ,'LC_ALL':'C'}
    try:
        return runner(argv,capture_output=True,text=True,timeout=timeout,check=False,env=env)
    except (OSError,subprocess.SubprocessError):
        return None


def parse_packagekit_updates(output):
    packages={}
    in_results=False
    pattern=re.compile(r'^\s*([A-Za-z][A-Za-z ]*?)\s{2,}(\S+)\s+\(([^()]*)\)\s*$')
    for line in str(output or '').splitlines():
        if line.strip().casefold()=='results:':
            in_results=True
            continue
        if not in_results: continue
        match=pattern.match(line)
        if match:
            classification,package_id,_repo=match.groups()
            packages[package_id]=(classification.strip().casefold()=='security')
    return {'packages':sorted(packages),'security_count':sum(packages.values())}


def _packagekit_updates(runner=subprocess.run):
    executable=shutil.which('pkcon')
    if not executable: return {'ok':False,'packages':[],'security_count':0}
    result=_run([executable,'--plain','--cache-age','86400','get-updates'],35,runner)
    if result is None or result.returncode:
        return {'ok':False,'packages':[],'security_count':0}
    return {'ok':True,**parse_packagekit_updates(result.stdout)}


def _flatpak_updates(installation, runner=subprocess.run):
    executable=shutil.which('flatpak')
    if not executable: return {'ok':True,'apps':[],'available':False}
    result=_run([executable,'remote-ls','--updates','--columns=application','--cached',f'--{installation}'],8,runner)
    if result is None or result.returncode:
        return {'ok':False,'apps':[],'available':True}
    return {'ok':True,'apps':sorted({line.strip() for line in result.stdout.splitlines() if line.strip()}),'available':True}


def _firmware_updates(runner=subprocess.run):
    executable=shutil.which('fwupdmgr')
    if not executable: return {'ok':True,'devices':[],'available':False}
    result=_run([executable,'get-updates','--no-metadata-check'],12,runner)
    if result is None or result.returncode:
        return {'ok':False,'devices':[],'available':True}
    output=str(result.stdout or '')
    if re.search(r'no (?:available )?updates|no updatable devices',output,re.I):
        return {'ok':True,'devices':[],'available':True}
    devices=[]
    for line in output.splitlines():
        if re.match(r'^\s*(?:Available version|Update Version):',line,re.I):
            devices.append(line.split(':',1)[-1].strip())
    return {'ok':True,'devices':devices,'available':True}


def _disk_warnings():
    warnings=[]
    seen_devices=set()
    for path,label in ((Path('/'),'sistema'),(Path.home(),'pasta pessoal')):
        try:
            stat=path.stat(); usage=shutil.disk_usage(path)
        except OSError:
            warnings.append(f'não consegui verificar o espaço em {label}')
            continue
        if stat.st_dev in seen_devices: continue
        seen_devices.add(stat.st_dev)
        free_percent=usage.free*100/max(1,usage.total)
        if usage.free<5*1024**3 or free_percent<10:
            warnings.append(f'pouco espaço livre em {label}: {usage.free/1024**3:.1f} GB ({free_percent:.0f}%)')
    return warnings


def _aurora_warnings(cfg):
    checks=(diagnostics._ollama_status(cfg),diagnostics._voice_status(),
            diagnostics._desktop_status(),diagnostics._service_status())
    markers=('indisponível','ausente','incompleto','recusado','não foi possível','sem xwayland','nenhuma sessão')
    return [check for check in checks if any(marker in check.casefold() for marker in markers)]


def check_system_health(cfg, *, runner=subprocess.run):
    """Inspect update sources and essential local prerequisites without changing them."""
    rpm=_packagekit_updates(runner)
    system_flatpak=_flatpak_updates('system',runner)
    user_flatpak=_flatpak_updates('user',runner)
    flatpak_apps=sorted(set(system_flatpak['apps'])|set(user_flatpak['apps']))
    firmware=_firmware_updates(runner)
    try: warnings=_disk_warnings()
    except Exception: warnings=['não consegui verificar o espaço em disco']
    try: warnings.extend(_aurora_warnings(cfg))
    except Exception: warnings.append('não consegui verificar os componentes da Aurora')
    return {
        'rpm':rpm,'flatpak':{'ok':system_flatpak['ok'] and user_flatpak['ok'],'apps':flatpak_apps,
                             'available':system_flatpak['available'] or user_flatpak['available']},
        'firmware':firmware,'warnings':warnings,
    }


def summarize_health(report):
    parts=[]
    rpm=report.get('rpm',{})
    if rpm.get('ok') and rpm.get('packages'):
        count=len(rpm['packages']); security=int(rpm.get('security_count',0))
        noun='atualização' if count==1 else 'atualizações'
        parts.append(f'{count} {noun} de pacotes do sistema, {security} de segurança')
    elif not rpm.get('ok'):
        parts.append('não consegui consultar atualizações dos pacotes do sistema')
    flatpak=report.get('flatpak',{})
    if flatpak.get('apps'):
        count=len(flatpak['apps']); noun='aplicativo' if count==1 else 'aplicativos'
        parts.append(f'{count} {noun} Flatpak com atualização disponível')
    elif flatpak.get('available') and not flatpak.get('ok'):
        parts.append('não consegui consultar atualizações Flatpak')
    firmware=report.get('firmware',{})
    if firmware.get('devices'):
        count=len(firmware['devices']); noun='atualização' if count==1 else 'atualizações'
        parts.append(f'{count} {noun} de firmware; elas não serão instaladas automaticamente')
    elif firmware.get('available') and not firmware.get('ok'):
        parts.append('não consegui consultar atualizações de firmware')
    parts.extend(report.get('warnings',[]))
    return parts


class SystemRoutineCheck(QThread):
    completed=Signal(object)

    def __init__(self,cfg,parent=None):
        super().__init__(parent)
        self.cfg=dict(cfg)

    def run(self):
        try: self.completed.emit(check_system_health(self.cfg))
        except Exception as exc: self.completed.emit({'error':type(exc).__name__})


class SystemUpdateRequest(QThread):
    progress=Signal(str)
    completed=Signal(object)

    def __init__(self,update_rpm,update_flatpak,parent=None):
        super().__init__(parent)
        self.update_rpm=bool(update_rpm); self.update_flatpak=bool(update_flatpak)

    @staticmethod
    def _update(argv,timeout=1800):
        try:
            return subprocess.run(argv,capture_output=True,text=True,timeout=timeout,
                                  check=False,env={**__import__('os').environ,'LC_ALL':'C'})
        except (OSError,subprocess.SubprocessError) as exc:
            return exc

    def run(self):
        outcomes=[]
        if self.update_rpm:
            executable=shutil.which('pkcon')
            if not executable: outcomes.append(('RPM',False,'PackageKit não está instalado.'))
            else:
                self.progress.emit('Instalando atualizações do sistema')
                result=self._update([executable,'--plain','--noninteractive','update'])
                ok=not isinstance(result,Exception) and result.returncode==0
                outcomes.append(('RPM',ok,'' if ok else 'PackageKit não concluiu a atualização; confira a autenticação e as assinaturas dos repositórios.'))
        if self.update_flatpak:
            executable=shutil.which('flatpak')
            if not executable: outcomes.append(('Flatpak',False,'Flatpak não está instalado.'))
            else:
                for scope in ('system','user'):
                    self.progress.emit(f'Atualizando aplicativos Flatpak ({scope})')
                    result=self._update([executable,'update',f'--{scope}','--assumeyes','--noninteractive'])
                    ok=not isinstance(result,Exception) and result.returncode==0
                    outcomes.append((f'Flatpak {scope}',ok,'' if ok else 'Flatpak não concluiu esta etapa.'))
        self.completed.emit({'ok':bool(outcomes) and all(item[1] for item in outcomes),
                             'outcomes':outcomes})


class SessionUnlockMonitor(QObject):
    unlocked=Signal()
    locked=Signal()
    SERVICE='org.gnome.ScreenSaver'
    PATH='/org/gnome/ScreenSaver'
    INTERFACE='org.gnome.ScreenSaver'

    def __init__(self,parent=None):
        super().__init__(parent)
        self.bus=QDBusConnection.sessionBus()
        self.interface=QDBusInterface(self.SERVICE,self.PATH,self.INTERFACE,self.bus,self)
        self.active=None
        self.slot=SLOT('_active_changed(bool)')
        self.startup_timer=QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.timeout.connect(self._startup_unlocked)
        self.connected=self.bus.connect(self.SERVICE,self.PATH,self.INTERFACE,'ActiveChanged',self,self.slot)
        if not self.connected: return
        reply=self.interface.call('GetActive')
        if reply.type()==QDBusMessage.MessageType.ErrorMessage or not reply.arguments(): return
        self.active=bool(reply.arguments()[0])
        if not self.active: self.startup_timer.start(1500)

    @Slot()
    def _startup_unlocked(self):
        if self.active is False: self.unlocked.emit()

    @Slot(bool)
    def _active_changed(self,active):
        active=bool(active)
        previous=self.active
        self.active=active
        if active:
            self.startup_timer.stop()
            if previous is False: self.locked.emit()
        elif previous is not False:
            self.startup_timer.stop()
            self.unlocked.emit()

    def close(self):
        self.startup_timer.stop()
        if self.connected:
            self.bus.disconnect(self.SERVICE,self.PATH,self.INTERFACE,'ActiveChanged',self,self.slot)
            self.connected=False
