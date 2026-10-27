# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import json, os, platform, shutil, subprocess, threading

APP_DIR = Path(__file__).resolve().parent.parent

CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'aurora'
APP_CONFIG = CONFIG_DIR/'aurora-settings.json'
LEGACY_APP_CONFIG = APP_DIR/'aurora-settings.json'
_SETTINGS_SAVE_LOCK=threading.RLock()

VOSK_PATH = APP_DIR/'assets/vosk-model'
DATA_DIR = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'aurora'
STT_MODEL_PATH = DATA_DIR/'models'/'ggml-base-q5_1.bin'
VOICE_ROOT = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'aurora'/'voices'
PIPER_MODEL_DIR = VOICE_ROOT/'pt_BR-faber-medium'
PIPER_MODEL_PATH = PIPER_MODEL_DIR/'pt_BR-faber-medium.onnx'

DEFAULTS = {
    'endpoint':'http://127.0.0.1:11434',
    'model':'gemma3:1b-it-qat',
    'agent_model':'qwen2.5:1.5b',
    'num_ctx':1024,
    'num_thread':4,
    'num_gpu':99,
    'keep_alive':-1,
    'tts_voice':'pt_BR-faber-medium',
    'tts_engine':'piper',
    'tts_pitch':1.25,
    'tts_speed':1.0,
    'feedback_theme':'boreal',
    'user_name':'',
    'profile_configured':False,
    'assistant_name':'Aurora',
    'assistant_personality':'companion',
    'conversation_tone':55,
    'response_detail':'balanced',
    'custom_instructions':'',
    'wake_profile':None,
    'bubble_style':'boreal',
    'onboarding_pending':False,
    'onboarding_boot_id':'',
    'onboarding_session_id':'',
    'bubble_position':None,
    'agent_num_ctx':2048,
    'agent_num_predict':384,
    'obs_host':'127.0.0.1',
    'obs_port':4455,
    'screen_control_apps':[],
    # The Android companion is archived; do not expose an HTTPS listener on
    # the LAN unless the user explicitly opts in.
    'companion_enabled':False,
    'companion_port':8765,
    'system_routine_enabled':True,
    'conversation_mode_enabled':True,
    'conversation_idle_seconds':18,
    'conversation_max_turns':8,
}

def current_boot_id():
    """Return this Linux boot's unique ID, or an empty string if unavailable."""
    try: return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    except OSError: return ''

def current_session_id():
    """Return the login session identifier used to trigger first-run setup."""
    value = str(os.environ.get('XDG_SESSION_ID') or '').strip()
    if value:
        return value
    loginctl = shutil.which('loginctl')
    if not loginctl:
        return ''
    try:
        result = subprocess.run([loginctl, 'list-sessions', '--no-legend'],
                                capture_output=True, text=True, timeout=2, check=False)
        uid = str(os.getuid())
        candidates = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 2 or fields[1] != uid:
                continue
            session = fields[0]
            active = subprocess.run([loginctl, 'show-session', session, '-p', 'Active', '--value'],
                                    capture_output=True, text=True, timeout=2, check=False)
            if active.stdout.strip().casefold() == 'yes':
                candidates.append(session)
        return candidates[-1] if candidates else ''
    except (OSError, subprocess.SubprocessError):
        return ''

def onboarding_state(settings, boot_id=None, session_id=None):
    """Return (wait_for_new_login, show_wizard) for an onboarding marker."""
    if not isinstance(settings,dict) or not settings.get('onboarding_pending'):
        return False,False
    current_session = current_session_id() if session_id is None else str(session_id)
    installed_session = str(settings.get('onboarding_session_id') or '')
    if current_session and installed_session:
        return installed_session == current_session, installed_session != current_session
    current=current_boot_id() if boot_id is None else str(boot_id)
    installed=str(settings.get('onboarding_boot_id') or '')
    if not current:
        return False,True
    return installed==current, installed!=current

def settings_load():
    should_save = False
    try:
        data=json.loads(APP_CONFIG.read_text())
    except FileNotFoundError:
        try: data=json.loads(LEGACY_APP_CONFIG.read_text())
        except Exception: data={}
        if not isinstance(data,dict): data={}
        if data: settings_save(data)
    except Exception: data={}
    if not isinstance(data,dict): data={}
    data.pop('hands_free',None); data.pop('wake_enabled',None)
    result={**DEFAULTS,**data}
    if result.get('assistant_personality') not in {'companion','direct','playful','formal'}:
        result['assistant_personality']='companion'
        should_save=True
    if result.get('response_detail') not in {'concise','balanced','detailed'}:
        result['response_detail']='balanced'
        should_save=True
    try:
        normalized_tone=max(0,min(100,int(result.get('conversation_tone',55))))
    except (TypeError,ValueError):
        normalized_tone=55
    if normalized_tone != result.get('conversation_tone'):
        result['conversation_tone']=normalized_tone
        should_save=True
    custom_instructions=' '.join(str(result.get('custom_instructions') or '').split())[:240]
    if custom_instructions != result.get('custom_instructions'):
        result['custom_instructions']=custom_instructions
        should_save=True
    try:
        pitch = float(result.get('tts_pitch', 1.25))
        result['tts_pitch'] = max(0.5, min(2.0, pitch))
    except (TypeError, ValueError):
        result['tts_pitch'] = 1.25
    try:
        speed = float(result.get('tts_speed', 1.0))
        result['tts_speed'] = max(0.5, min(2.0, speed))
    except (TypeError, ValueError):
        result['tts_speed'] = 1.0
    # Standardize on Faber with pitch/speed customization
    result['tts_engine'] = 'piper'
    result['tts_voice'] = 'pt_BR-faber-medium'
    if result.get('tts_voice') != 'pt_BR-faber-medium' or result.get('tts_engine') != 'piper':
        should_save = True
    if not APP_CONFIG.exists() or should_save: settings_save(result)
    return result

def settings_save(data):
    with _SETTINGS_SAVE_LOCK:
        snapshot=dict(data)
        APP_CONFIG.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(APP_CONFIG.parent,0o700)
        temporary=APP_CONFIG.with_suffix('.tmp')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            json.dump(snapshot,output,ensure_ascii=False,indent=2)
            output.write('\n')
            output.flush(); os.fsync(output.fileno())
        os.replace(temporary,APP_CONFIG)
        os.chmod(APP_CONFIG,0o600)

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
