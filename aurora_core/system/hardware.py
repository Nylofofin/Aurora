# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
import platform, re, shutil, subprocess
from ..config import hardware_profile

def system_hardware_summary():
    hw=hardware_profile(); ram_total=hw['ram']/1024**3 if hw['ram'] else 0; ram_free=0
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'): ram_free=int(line.split()[1])*1024/1024**3; break
    except Exception: pass
    def command_lines(command,args,limit=5):
        path=shutil.which(command)
        if not path: return []
        try:
            result=subprocess.run([path,*args],capture_output=True,text=True,timeout=4,check=True)
            return [line.strip() for line in result.stdout.splitlines() if line.strip()][:limit]
        except Exception: return []
    devices=command_lines('lspci',['-nn'],30)
    gpus=[line for line in devices if re.search(r'vga compatible controller|3d controller|display controller',line,re.I)]
    audio=[line for line in devices if 'audio device' in line.casefold()]
    disks=command_lines('lsblk',['-dn','-o','NAME,SIZE,MODEL,TYPE'],8)
    try: disk=shutil.disk_usage(Path.home()); disk_text=f'{disk.total/1024**3:.0f} GB total, {disk.free/1024**3:.0f} GB livres'
    except Exception: disk_text='disponibilidade desconhecida'
    pieces=[f'Sistema: {platform.platform()}',f'Processador: {hw["cpu"]} ({hw["threads"]} threads; AVX2 {"sim" if hw["avx2"] else "não"})',f'Memória: {ram_total:.1f} GB total, {ram_free:.1f} GB disponível',f'GPU: {"; ".join(gpus) if gpus else "não identificada via PCI"}']
    if hw['vram']: pieces.append(f'VRAM: {hw["vram"]/1024**3:.1f} GB')
    if audio: pieces.append('Áudio: '+'; '.join(audio[:3]))
    if disks: pieces.append('Discos: '+'; '.join(disks))
    pieces.append('Armazenamento do diretório pessoal: '+disk_text)
    pieces.append(f'Ollama Vulkan: {"disponível" if hw["vulkan"] else "não detectado"}')
    return '. '.join(pieces)+'.'
