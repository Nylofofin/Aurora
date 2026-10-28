# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
from pathlib import Path
from ..memory import user_memory_update
from ..system.apps import launch_application
from ..system.files import create_user_file
from ..system.hardware import system_hardware_summary
from ..system.volume import control_volume
from ..system.windows import manage_window
from ..system.accessibility import inspect_accessible_windows
from ..system.audit import audit_action
from ..system.agenda import agenda_add, agenda_cancel, agenda_clear, agenda_list, agenda_nearest, parse_datetime
from ..system.routine import check_system_health, format_health_response

TOOLS=[
 {'type':'function','function':{'name':'search_files','description':'Procurar arquivos pelo nome na pasta pessoal, sem ler o conteúdo.','parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}}},
 {'type':'function','function':{'name':'take_screenshot','description':'A pedido explícito do usuário, solicitar ao portal do desktop uma captura de tela e salvar em Imagens/Aurora com nome exclusivo. O portal ainda pode exigir permissão do sistema.','parameters':{'type':'object','properties':{},'required':[]}}},
 {'type':'function','function':{'name':'obs_record','description':'Iniciar ou parar a gravação local no OBS Studio conectado por WebSocket autenticado.','parameters':{'type':'object','properties':{'action':{'type':'string','enum':['start','stop']}},'required':['action']}}},
 {'type':'function','function':{'name':'open_application','description':'Abrir um aplicativo instalado pelo nome, usando os lançadores .desktop do sistema e apelidos comuns. Use só quando o usuário pediu para abrir um app.','parameters':{'type':'object','properties':{'command':{'type':'string'}},'required':['command']}}},
 {'type':'function','function':{'name':'close_application','description':'Encerrar um aplicativo pelo nome. Só use se o usuário pediu explicitamente; a Aurora pede confirmação na bolha porque pode haver trabalho não salvo.','parameters':{'type':'object','properties':{'application':{'type':'string'}},'required':['application']}}},
 {'type':'function','function':{'name':'manage_window','description':'Maximizar, restaurar, minimizar ou fechar uma janela. target vazio indica a janela atual. Fechar pede confirmação; o suporte a maximizar/minimizar depende do sistema de janelas.','parameters':{'type':'object','properties':{'action':{'type':'string','enum':['maximize','restore','minimize','close']},'target':{'type':'string'}},'required':['action','target']}}},
 {'type':'function','function':{'name':'inspect_accessible_windows','description':'Listar títulos e nomes/roles dos controles acessíveis de um aplicativo permitido. Não ler o texto digitado nos campos.','parameters':{'type':'object','properties':{'application':{'type':'string'}},'required':['application']}}},
 {'type':'function','function':{'name':'focus_accessible_window','description':'Focar uma janela pelo título em um aplicativo permitido na allowlist.','parameters':{'type':'object','properties':{'application':{'type':'string'},'window':{'type':'string'}},'required':['application','window']}}},
 {'type':'function','function':{'name':'type_accessible_text','description':'Inserir texto em campo acessível nomeado. Exige confirmação na bolha; nunca usar em senha, credencial ou campo protegido.','parameters':{'type':'object','properties':{'application':{'type':'string'},'window':{'type':'string'},'field':{'type':'string'},'text':{'type':'string'}},'required':['application','window','field','text']}}},
 {'type':'function','function':{'name':'volume_control','description':'Consultar, silenciar, reativar ou ajustar o volume de saída do PC. Em set value é percentual; em up/down é o passo percentual.','parameters':{'type':'object','properties':{'action':{'type':'string','enum':['status','mute','unmute','set','up','down']},'value':{'type':'integer'}},'required':['action','value']}}},
 {'type':'function','function':{'name':'get_system_info','description':'Identificar hardware e recursos do computador local: CPU, RAM disponível, GPU/VRAM, discos e Vulkan.','parameters':{'type':'object','properties':{},'required':[]}}},
 {'type':'function','function':{'name':'check_system_health','description':'Consultar o estado atual do computador, sem alterar nada: atualizações RPM/Flatpak/firmware, espaço em disco e componentes essenciais da Aurora. Use quando perguntarem se o PC está em dia ou sobre sua saúde. Informe indisponibilidades sem afirmar que tudo está atualizado.','parameters':{'type':'object','properties':{},'required':[]}}},
 {'type':'function','function':{'name':'create_file','description':'Criar um arquivo novo de texto no local natural solicitado. Nunca substituir arquivos existentes. Resolva área de trabalho, documentos, downloads, pasta do projeto, pasta da Aurora, caminho completo ou nome exato de uma pasta.','parameters':{'type':'object','properties':{'filename':{'type':'string'},'location':{'type':'string'},'content':{'type':'string'}},'required':['filename','location','content']}}},
 {'type':'function','function':{'name':'remember_preference','description':'Salvar uma preferência local persistente somente quando o usuário pedir explicitamente para lembrar, guardar ou seguir isso no futuro.','parameters':{'type':'object','properties':{'preference':{'type':'string'}},'required':['preference']}}},
 {'type':'function','function':{'name':'forget_preference','description':'Apagar da memória local uma preferência específica que o usuário pediu para esquecer.','parameters':{'type':'object','properties':{'preference':{'type':'string'}},'required':['preference']}}},
 {'type':'function','function':{'name':'agenda_add','description':'Adicionar um compromisso na agenda pessoal. Use quando o usuário pedir para agendar, marcar ou criar um compromisso com título e data/hora.','parameters':{'type':'object','properties':{'title':{'type':'string','description':'Título do compromisso, ex: "Reunião com cliente"'},'when':{'type':'string','description':'Data e hora em linguagem natural, ex: "amanhã às 15h", "sexta às 9h30", "dia 5 de novembro às 18h"'},'notes':{'type':'string','description':'Anotações opcionais sobre o compromisso'}},'required':['title','when']}}},
 {'type':'function','function':{'name':'agenda_list','description':'Listar compromissos futuros na agenda pessoal.','parameters':{'type':'object','properties':{'days':{'type':'integer','description':'Número de dias à frente para listar. Padrão: 7'}},'required':[]}}},
 {'type':'function','function':{'name':'agenda_cancel','description':'Cancelar/remover um único compromisso da agenda. É obrigatório informar o ID mostrado ao listar a agenda; nunca use esta ferramenta para apagar vários compromissos.','parameters':{'type':'object','properties':{'event_id':{'type':'integer','description':'ID exato do compromisso a remover'}},'required':['event_id']}}},
 {'type':'function','function':{'name':'agenda_clear','description':'Apagar todos os compromissos da agenda. Esta ação exige confirmação na bolha. Use somente quando o usuário pedir explicitamente para limpar todos os compromissos.','parameters':{'type':'object','properties':{},'required':[]}}},
 {'type':'function','function':{'name':'agenda_nearest','description':'Informar o próximo compromisso agendado.','parameters':{'type':'object','properties':{},'required':[]}}},
]


def _execute_local_tool(name,args,cfg=None):
    if name=='inspect_accessible_windows':
        return inspect_accessible_windows(args.get('application',''),(cfg or {}).get('screen_control_apps',[]))
    if name=='get_system_info': return system_hardware_summary()
    if name=='check_system_health':
        report=check_system_health(cfg or {})
        return format_health_response(report)
    if name=='volume_control': return control_volume(args.get('action','status'),args.get('value',5))
    if name=='manage_window' and args.get('action')!='close': return manage_window(args.get('action',''),args.get('target',''))
    if name=='open_application': return launch_application(args.get('command',''))
    if name=='create_file':
        try: return create_user_file(args.get('filename',''),args.get('location',''),args.get('content',''))
        except Exception as exc: return f'Não criei o arquivo: {exc}'
    if name in ('remember_preference','forget_preference'):
        try:
            return user_memory_update(
                args.get('preference',''), forget=name=='forget_preference'
            )
        except ValueError as exc:
            return f'Não consegui atualizar a memória local: {exc}'
    if name=='agenda_add':
        ts = parse_datetime(str(args.get('when', '')))
        return agenda_add(str(args.get('title', '')), ts or 0, str(args.get('notes', '')))
    if name=='agenda_list': return agenda_list(int(args.get('days', 7)))
    if name=='agenda_cancel': return agenda_cancel(args.get('event_id'))
    if name=='agenda_clear': return agenda_clear()
    if name=='agenda_nearest': return agenda_nearest()
    if name=='search_files':
        query=str(args.get('query','')).lower().strip()
        if not query: return 'Busca sem termo.'
        hits=[]; skip={'.cache','.local','.mozilla','.var','node_modules','.git'}
        visited=0; truncated=False
        for root,dirs,files in os.walk(Path.home()):
            dirs[:]=[d for d in dirs if not d.startswith('.') and d not in skip]
            visited+=1
            if visited>3000:
                truncated=True
                break
            for filename in files:
                if query in filename.lower():
                    hits.append(str(Path(root)/filename))
                    if len(hits)>=25: break
            if len(hits)>=25: break
        if hits:
            result='\n'.join(hits)
            return result+'\nBusca parcial: limite de pastas atingido.' if truncated else result
        return 'Busca parcial: limite de pastas atingido. Refine o nome para continuar.' if truncated else 'Nenhum arquivo encontrado pelo nome.'
    return None


def execute_local_tool(name,args,cfg=None):
    audited={
        'open_application','close_application','manage_window','volume_control',
        'get_system_info','create_file','remember_preference','forget_preference','search_files',
    }
    try:
        result=_execute_local_tool(name,args,cfg)
    except Exception:
        if name in audited: audit_action(name,'failed')
        raise
    if result is not None and name in audited: audit_action(name,"returned",result)
    return result
