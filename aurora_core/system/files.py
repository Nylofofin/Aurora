from __future__ import annotations

from pathlib import Path
import asyncio, base64, concurrent.futures, configparser, html, json, os, platform, queue, re, shlex, shutil, signal, subprocess, sys, threading, time, urllib.error, urllib.request, unicodedata

from ..config import APP_DIR
from .text import normalize_words

def xdg_user_directory(kind):
    command=shutil.which('xdg-user-dir')
    if command:
        try:
            result=subprocess.run([command,kind],capture_output=True,text=True,timeout=2,check=True).stdout.strip()
            path=Path(result).expanduser()
            if path.is_dir(): return path
        except Exception: pass
    fallbacks={'DESKTOP':['Desktop','Área de Trabalho'],'DOCUMENTS':['Documents','Documentos'],'DOWNLOAD':['Downloads'],'PICTURES':['Pictures','Imagens'],'MUSIC':['Music','Música'],'VIDEOS':['Videos','Vídeos']}
    for name in fallbacks.get(kind,[]):
        path=Path.home()/name
        if path.is_dir(): return path
    default=fallbacks.get(kind,[''])[0]
    return Path.home()/default if default else Path.home()

def resolve_natural_directory(location):
    """Resolve spoken destinations to standard XDG folders, explicit paths, or an exact folder name."""
    raw=' '.join(str(location or '').split()).strip(' .,:;!?')
    if not raw: return xdg_user_directory('DOCUMENTS')
    expanded=Path(os.path.expandvars(raw)).expanduser()
    if expanded.is_absolute(): return expanded.resolve(strict=False)
    normalized=normalize_words(raw)
    normalized=re.sub(r'^(?:dentro da pasta de|dentro do diretorio de|dentro da|dentro do|dentro de|na pasta da|na pasta do|pasta da|pasta do|na pasta de|no diretorio de|no diretorio|pasta de|diretorio de|na pasta|na|no|em|para|pra)\s+','',normalized)
    mapping={
        'desktop':'DESKTOP','area de trabalho':'DESKTOP','mesa':'DESKTOP',
        'documentos':'DOCUMENTS','documento':'DOCUMENTS','documents':'DOCUMENTS','meus documentos':'DOCUMENTS',
        'downloads':'DOWNLOAD','baixados':'DOWNLOAD','pasta de downloads':'DOWNLOAD',
        'imagens':'PICTURES','fotos':'PICTURES','pictures':'PICTURES',
        'musicas':'MUSIC','musica':'MUSIC','music':'MUSIC',
        'videos':'VIDEOS','video':'VIDEOS',
        'pasta pessoal':'HOME','inicio':'HOME','home':'HOME','raiz da minha pasta':'HOME',
        'pasta da aurora':'AURORA','aurora':'AURORA','pasta do projeto':'PROJECT','projeto':'PROJECT','workspace':'PROJECT','pasta de trabalho':'PROJECT','projeto codex':'PROJECT',
    }
    mapped=mapping.get(normalized)
    if mapped:
        if mapped=='HOME': return Path.home()
        if mapped=='AURORA': return APP_DIR
        if mapped=='PROJECT': return APP_DIR.parent.parent
        return xdg_user_directory(mapped)
    if '/' in raw or raw.startswith('./'):
        return (Path.home()/expanded).resolve(strict=False)
    # Search only likely user folders and stop at shallow depth; reject ambiguous exact matches.
    roots=[]
    for base in (xdg_user_directory('DOCUMENTS'),xdg_user_directory('DESKTOP'),xdg_user_directory('DOWNLOAD'),APP_DIR.parent.parent,Path.home()):
        if base.is_dir() and base not in roots: roots.append(base)
    wanted=normalized; matches=[]; visited=0; skipped={'.cache','.local','.mozilla','.var','node_modules','.git','__pycache__'}
    for base in roots:
        for current,dirs,_ in os.walk(base):
            depth=len(Path(current).relative_to(base).parts)
            dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d not in skipped) if depth<4 else []
            visited+=1
            if visited>3000: break
            if normalize_words(Path(current).name)==wanted: matches.append(Path(current).resolve())
        if visited>3000: break
    unique=list(dict.fromkeys(matches))
    if len(unique)==1: return unique[0]
    if len(unique)>1: raise ValueError('Achei mais de uma pasta com esse nome: '+', '.join(str(x) for x in unique[:4])+'. Diga qual caminho deseja usar.')
    raise FileNotFoundError(f'Não localizei uma pasta chamada “{raw}”. Use Documentos, Área de Trabalho, Downloads ou diga o caminho completo.')

def create_user_file(filename,location,content):
    name=' '.join(str(filename or '').split()).strip()
    if not name or name in ('.','..') or Path(name).name!=name or '\x00' in name:
        raise ValueError('Diga apenas o nome do arquivo; o local vai separado.')
    directory=resolve_natural_directory(location)
    if not directory.is_dir(): raise FileNotFoundError(f'A pasta de destino não existe: {directory}')
    target=directory/name
    payload=str(content or '').encode('utf-8')
    if len(payload)>2_000_000: raise ValueError('O arquivo excede o limite de 2 MB.')
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
    with os.fdopen(fd,'wb') as output: output.write(payload)
    return f'Criei {target} sem substituir nenhum arquivo existente.'
