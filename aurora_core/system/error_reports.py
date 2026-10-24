# SPDX-License-Identifier: GPL-3.0-only
"""Private, minimal diagnostic reports and explicit service recovery."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid


def user_data_dir() -> Path:
    return Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local'/'share'))/'aurora'


def classify_error(error_type: str, message: str) -> str:
    value=f'{error_type} {message}'.casefold()
    if any(token in value for token in ('connectionrefused', 'connection refused', 'urlerror','ollama local')):
        return 'serviço local ou conexão recusada'
    if any(token in value for token in ('timeout', 'timed out', 'tempo limite', 'expired')):
        return 'operação excedeu o tempo limite'
    if any(token in value for token in ('modulenotfound', 'importerror', 'no module named')):
        return 'dependência ausente ou incompatível'
    if any(token in value for token in ('permissionerror', 'permission denied', 'acesso negado')):
        return 'permissão insuficiente'
    if any(token in value for token in ('filenotfound', 'no such file', 'arquivo não encontrado')):
        return 'arquivo ou recurso local ausente'
    return 'causa não identificada automaticamente'


def _redact(value: str) -> str:
    text=str(value or '')
    home=str(Path.home())
    if home:
        text=text.replace(home,'~')
    text=re.sub(r'(?i)\bauthorization\b\s*[:=]\s*(?:bearer\s+)?[^\s,;]+','Authorization=[REDACTED]',text)
    text=re.sub(r'(?i)\b(password|passwd|token|secret|api[_-]?key)\b\s*[:=]\s*[^\s,;]+',r'\1=[REDACTED]',text)
    text=re.sub(r'\bgh[pousr]_[A-Za-z0-9_]{10,}\b','[REDACTED_GITHUB_TOKEN]',text)
    return text[:1200]


def _safe_message(error_type: str, message: str) -> str:
    """Use the exception only for classification; never persist arbitrary text."""
    category=classify_error(error_type,message)
    return {
        'serviço local ou conexão recusada':'A conexão a um serviço local não foi concluída.',
        'operação excedeu o tempo limite':'Uma operação excedeu o tempo limite.',
        'dependência ausente ou incompatível':'Uma dependência necessária não foi carregada.',
        'permissão insuficiente':'O sistema recusou uma operação por permissão.',
        'arquivo ou recurso local ausente':'Um arquivo ou recurso necessário não foi encontrado.',
    }.get(category,'A operação falhou; o texto livre do erro foi omitido para proteger dados locais.')


def write_error_report(root: Path, *, context: str, error_type: str,
                       message: str, frames=(), now=None) -> Path:
    """Write a mode-0600 report; deliberately omit prompts, transcripts and env."""
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    try: os.chmod(root,0o700)
    except OSError: pass
    now=now or datetime.now().astimezone()
    stamp=now.strftime('%Y%m%d-%H%M%S-%f')
    report=root/f'aurora-error-{stamp}.md'
    safe_frames=[]
    for frame in list(frames or ())[-12:]:
        if isinstance(frame,dict):
            filename=_redact(str(frame.get('file','')))
            line=frame.get('line','?')
            function=_redact(str(frame.get('function','?')))
            safe_frames.append(f'- `{filename}:{line}` — `{function}`')
    content=(
        '# Relatório local de erro da Aurora\n\n'
        f'- Data: {now.isoformat(timespec="seconds")}\n'
        f'- Contexto: {_redact(context)}\n'
        f'- Classificação automática: {classify_error(error_type,message)}\n'
        f'- Tipo: `{_redact(error_type)}`\n'
        f'- Resumo seguro: {_safe_message(error_type,message)}\n\n'
        '## Frames do projeto\n\n'
        + ('\n'.join(safe_frames) if safe_frames else '- Não disponíveis para este erro.')
        + '\n\nEste relatório fica neste dispositivo. Não contém prompts, transcrições, áudio, '
          'variáveis de ambiente ou conteúdo de arquivos pessoais. Revise antes de compartilhar.\n'
    )
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    fd=os.open(report,flags,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as output:
        output.write(content)
        output.flush(); os.fsync(output.fileno())
    return report


def schedule_user_service_restart(*, runner=subprocess.run, which=shutil.which) -> tuple[bool,str]:
    """Ask the user systemd manager to restart Aurora after this UI callback returns."""
    systemd_run=which('systemd-run')
    systemctl=which('systemctl')
    if not systemd_run or not systemctl:
        return False,'systemd-run ou systemctl não está disponível'
    unit=f'aurora-error-restart-{uuid.uuid4().hex[:10]}'
    argv=[systemd_run,'--user',f'--unit={unit}','--on-active=2s','--collect',
          systemctl,'--user','restart','aurora.service']
    try:
        result=runner(argv,capture_output=True,text=True,timeout=5,check=False)
    except (OSError,subprocess.SubprocessError) as exc:
        return False,type(exc).__name__
    if result.returncode:
        return False,_redact(result.stderr or result.stdout or 'systemd-run falhou')
    return True,'reinício agendado'
