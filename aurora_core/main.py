from __future__ import annotations

from PySide6.QtWidgets import QApplication
import asyncio, base64, concurrent.futures, configparser, html, json, os, platform, queue, re, shlex, shutil, signal, subprocess, sys, threading, time, urllib.error, urllib.request, unicodedata

from .config import APP_CONFIG, hardware_profile, settings_load, settings_save
from .service import AuroraService

def main():
    app=QApplication(sys.argv); app.setApplicationName('Aurora'); app.setQuitOnLastWindowClosed(False)
    print(f'[aurora] qt_platform={app.platformName()}',file=sys.stderr,flush=True)
    cfg=settings_load(); hw=hardware_profile()
    # Hardware-tuned defaults for this host: Sandy Bridge CPU, 12 GiB RAM, 4 GiB Polaris Vulkan GPU.
    raw={}
    try: raw=json.loads(APP_CONFIG.read_text())
    except Exception: pass
    if 'num_thread' not in raw: cfg['num_thread']=min(4,max(2,hw['threads']))
    if 'num_gpu' not in raw: cfg['num_gpu']=99 if hw['vram']>=2*1024**3 and hw['vulkan'] else 0
    if 'num_ctx' not in raw: cfg['num_ctx']=4096
    settings_save(cfg)
    service=AuroraService(app); app.aboutToQuit.connect(service.stop); sys.exit(app.exec())
