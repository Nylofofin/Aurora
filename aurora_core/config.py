from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs, urljoin
import asyncio, base64, concurrent.futures, configparser, html, json, os, platform, queue, re, shlex, shutil, signal, subprocess, sys, threading, time, urllib.error, urllib.request, unicodedata

APP_DIR = Path(__file__).resolve().parent.parent

APP_CONFIG = APP_DIR/'aurora-settings.json'

VOSK_PATH = APP_DIR/'assets/vosk-model'

DEFAULTS = {
    'endpoint':'http://127.0.0.1:11434',
    'model':'gemma3:1b-it-qat',
    'agent_model':'gemma4:e2b-it-q4_K_M',
    'num_ctx':1024,
    'num_thread':4,
    'num_gpu':99,
    'keep_alive':-1,
    'tts_voice':'pt-BR-ThalitaMultilingualNeural',
    'bubble_position':None,
    'agent_num_ctx':2048,
    'agent_num_predict':384,
    'spotify_client_id':'',
    'obs_host':'127.0.0.1',
    'obs_port':4455,
}

def settings_load():
    try: data=json.loads(APP_CONFIG.read_text())
    except Exception: data={}
    data.pop('hands_free',None); data.pop('wake_enabled',None)
    result={**DEFAULTS,**data}
    APP_CONFIG.parent.mkdir(parents=True,exist_ok=True)
    if not APP_CONFIG.exists(): APP_CONFIG.write_text(json.dumps(result,indent=2))
    return result

def settings_save(data):
    APP_CONFIG.parent.mkdir(parents=True,exist_ok=True)
    APP_CONFIG.write_text(json.dumps(data,ensure_ascii=False,indent=2))

def local_endpoint(value):
    try:
        u=urlparse(value)
        return u.scheme in ('http','https') and u.hostname in ('localhost','127.0.0.1','::1')
    except Exception: return False

def hardware_profile():
    cpu=''; flags=set(); total=0
    try:
        for ln in Path('/proc/cpuinfo').read_text().splitlines():
            if ln.startswith('model name') and not cpu: cpu=ln.split(':',1)[1].strip()
            if ln.startswith('flags') and not flags: flags=set(ln.split(':',1)[1].split())
        for ln in Path('/proc/meminfo').read_text().splitlines():
            if ln.startswith('MemTotal:'): total=int(ln.split()[1])*1024
    except Exception: pass
    vram=0
    for f in Path('/sys/class/drm').glob('card*/device/mem_info_vram_total'):
        try: vram=max(vram,int(f.read_text().strip()))
        except Exception: pass
    return {'os':platform.platform(),'cpu':cpu or platform.processor(),'threads':os.cpu_count() or 4,
            'ram':total,'vram':vram,'avx2':('avx2' in flags),'vulkan':shutil.which('vulkaninfo') is not None}
