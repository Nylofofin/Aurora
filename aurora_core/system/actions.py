# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
from urllib.parse import urlparse
import os, re
import aurora_integrations
from .apps import close_application, launch_application
from .files import create_user_file, xdg_user_directory
from .hardware import system_hardware_summary
from .diagnostics import run_local_diagnostics
from .accessibility import focus_accessible_window, inspect_accessible_windows, type_into_accessible_field
from .volume import control_volume
from .windows import manage_window
from .agenda import agenda_add, agenda_cancel, agenda_clear, agenda_list, agenda_nearest, parse_datetime
from ..memory import user_memory_update

def execute_action(self,name,args):
    if name=='inspect_accessible_windows':
        return inspect_accessible_windows(args.get('application',''),self.cfg.get('screen_control_apps',[]))
    if name=='focus_accessible_window':
        self.orb.set_mode('controlling')
        return focus_accessible_window(args.get('application',''),args.get('window',''),self.cfg.get('screen_control_apps',[]))
    if name=='type_accessible_text':
        self.orb.set_mode('controlling')
        return type_into_accessible_field(args.get('application',''),args.get('window',''),args.get('field',''),
            args.get('text',''),self.cfg.get('screen_control_apps',[]))
    if name=='open_application': return launch_application(args.get('command',''))
    if name=='close_application': return close_application(args.get('application',''))
    if name=='manage_window': return manage_window(args.get('action',''),args.get('target',''))
    if name=='volume_control': return control_volume(args.get('action','status'),args.get('value',5))
    if name in ('system_info','get_system_info'): return system_hardware_summary()
    if name=='system_diagnostics': return run_local_diagnostics(self.cfg)
    if name=='timer_start': return self.timer_manager.start(args.get('seconds',0))
    if name=='timer_cancel': return self.timer_manager.cancel(args.get('timer_id'))
    if name=='timer_list': return self.timer_manager.list_active()
    if name=='agenda_add':
        ts = parse_datetime(str(args.get('when', '')))
        return agenda_add(str(args.get('title', '')), ts or 0, str(args.get('notes', '')))
    if name=='agenda_cancel': return agenda_cancel(args.get('event_id'))
    if name=='agenda_clear': return agenda_clear()
    if name=='agenda_list': return agenda_list(int(args.get('days', 7)))
    if name=='agenda_nearest': return agenda_nearest()
    if name=='create_file':
        try: return create_user_file(args.get('filename',''),args.get('location',''),args.get('content',''))
        except Exception as exc: return f'Não criei o arquivo: {exc}'
    if name=='remember_preference': return user_memory_update(args.get('preference',''))
    if name=='forget_preference': return user_memory_update(args.get('preference',''),forget=True)
    if name=='open_url':
        url=str(args.get('url','')).strip(); u=urlparse(url)
        if u.scheme not in ('http','https') or not u.hostname: return 'URL rejeitada por formato inválido.'
        opened=QDesktopServices.openUrl(QUrl(url))
        aurora_integrations._append_action_log('open_website','opened' if opened else 'failed')
        return 'Abri o site no navegador padrão.' if opened else 'Não consegui abrir o site no navegador padrão.'
    if name=='take_screenshot':
        self.orb.set_mode('controlling')
        QApplication.processEvents()
        if not self.voice.request_active.is_set() and not getattr(self,'companion_request',None): return 'A captura foi cancelada.'
        try:
            view=getattr(self.orb,'view',None)
            parent_window=aurora_integrations.screenshot_parent_identifier(
                view.winId() if view else None, QApplication.platformName())
            path=aurora_integrations.capture_screenshot(
                xdg_user_directory('PICTURES'), cancel_event=getattr(self,'action_cancel_event',None),
                parent_window=parent_window)
            aurora_integrations._append_action_log('screenshot','saved')
            return 'Pronto, tirei o print. Salvei em Imagens, na pasta Aurora.'
        except Exception as exc:
            aurora_integrations._append_action_log('screenshot','failed',
                {'error_type':type(exc).__name__,'phase':getattr(exc,'phase','unknown')})
            return f'Não consegui confirmar a captura: {exc}'
    if name=='spotify_authorize':
        return aurora_integrations.start_spotify_authorization(
            self.cfg.get('spotify_client_id',''), lambda url: QDesktopServices.openUrl(QUrl(url)))
    if name=='spotify_play':
        return aurora_integrations.play_spotify_track(args.get('query',''),self.cfg.get('spotify_client_id',''))
    if name=='obs_record':
        self.orb.set_mode('controlling')
        QApplication.processEvents()
        if not self.voice.request_active.is_set() and not getattr(self,'companion_request',None): return 'A gravação foi cancelada.'
        return aurora_integrations.obs_record(args.get('action',''),os.environ.get('AURORA_OBS_PASSWORD',''),
            self.cfg.get('obs_host','127.0.0.1'),self.cfg.get('obs_port',4455))
    return 'Ação não disponível.'
