# AGENTS.md — Aurora

Instruções permanentes para o agente de código (Codex). Leia tudo antes de mexer em qualquer arquivo. Se algo aqui conflitar com um pedido isolado do usuário, pergunte antes de agir.

**Se este arquivo chegou colado no chat:** execute **somente a Fase 0** (seção 3), que cria a raiz fixa do projeto e salva este texto como `AGENTS.md` lá. Não comece nenhuma outra fase sem o usuário pedir.

## 1. O que é a Aurora

Assistente pessoal de IA por voz, local-first, para o PC do usuário. Interface única: uma bolha flutuante (PySide6 + QML) que aparece quando o usuário diz "Aurora". Stack atual:

- Wake word local: Vosk (modelo pt pequeno), blocos de 200 ms.
- Transcrição do comando: `recognize_google` (pt-BR), fallback para a transcrição local.
- LLM local via Ollama: `gemma3:1b-it-qat` (conversa) e `gemma4:e2b-it-q4_K_M` (ferramentas/agente). Endpoint só `localhost`.
- Voz: Edge TTS (`pt-BR-ThalitaMultilingualNeural`).
- Serviço `systemd --user`, instalador e desinstalador em shell.

Hardware-alvo (não ignore): Fedora 44, GNOME/Wayland, Intel i5-2300 (4 núcleos, **sem AVX2**), 12 GB de RAM, AMD RX 470 com 4 GB de VRAM (Ollama via Vulkan). Modelos grandes ou dependências pesadas estão fora de cogitação.

## 2. Regras de ouro (valem para TODAS as fases)

1. **Nada de código feito sob medida para um exemplo.** Quando o usuário citar um caso (um preço, uma versão de jogo, uma cotação, um cargo), isso é **ilustração do tipo de problema**, nunca um requisito de função própria. É proibido criar funções, regex, constantes, prompts ou ramos de `if` ligados a um assunto específico. A solução tem que funcionar para qualquer assunto que o usuário perguntar.
2. **A Aurora busca o dado na hora.** Para qualquer pergunta cuja resposta possa ter mudado, a resposta vem de fontes consultadas agora, nunca da memória do modelo.
3. **Uma fase por vez.** Cada fase termina com testes passando, README atualizado e um commit. Não comece a fase seguinte sem o usuário pedir.
4. **Refatorar não muda comportamento.** Na fase de módulos, só mova e reorganize. Nenhuma funcionalidade nova, nenhum "já que estou aqui".
5. **Não adicione o que não foi pedido.** Se achar uma melhoria, liste no final da resposta e não implemente.
6. **Respeite o hardware.** Mantenha o Gemma 3 1B quente na GPU e as respostas curtas rápidas. Qualquer mudança que aumente latência da primeira resposta precisa ser medida e informada.
7. **Privacidade honesta.** Prompt e resposta do LLM só vão a `localhost`. O que sai para a internet (áudio do comando para o Google, texto da resposta para o Edge TTS, buscas web, localização aproximada por IP) deve estar descrito sem ambiguidade no README. Não escreva "tudo local" quando não for.
8. **Segurança de ações.** Ações destrutivas ou irreversíveis exigem confirmação na bolha. Arquivos existentes nunca são sobrescritos. Mantenha `public_http_url` e o handler de redirecionamento público (proteção contra acesso a rede interna).

## 3. Fase 0 — Criar a raiz fixa do projeto e git

Contexto: hoje o projeto mora em `~/Documents/Codex/2026-10-21/va/outputs/aurora/` (pasta temporária de sessão, fácil de perder ou apagar). A raiz definitiva será **`~/Projects/aurora/`**. Este arquivo pode ter chegado colado direto no chat, sem estar em nenhuma pasta; nesse caso esta fase é a primeira coisa a fazer.

Passos, nesta ordem:

1. **Parar o serviço** antes de mexer: `systemctl --user stop aurora.service`.
2. **Criar** `~/Projects/aurora/` (e `~/Projects/` se não existir).
3. **Copiar, não mover.** Copie o conteúdo de `~/Documents/Codex/2026-10-21/va/outputs/aurora/` para a nova raiz, **excluindo** `.venv/`, `__pycache__/` e `*-preview.png`. Inclua `assets/` (áudios de entrada/saída e o modelo Vosk, se existir). A pasta antiga fica **intacta** como backup até o usuário confirmar que tudo funciona; nunca apague nada dela.
4. **Salvar este arquivo** como `~/Projects/aurora/AGENTS.md` (se ele não existir lá), para que as próximas sessões o leiam sozinhas.
5. **Verificar dependências fora da pasta.** O `start-alpha.sh` usa o runtime local em `~/Documents/Codex/2026-10-21/va/work/` quando disponível, e existem logs e amostras `.wav` lá. Liste o que o projeto realmente usa de `work/` e **relate ao usuário** antes de copiar qualquer coisa grande; não traga logs, amostras de áudio nem venvs antigos sem necessidade.
6. **Git:** `git init` na nova raiz, criar `.gitignore` (ignorar `.venv/`, `__pycache__/`, `assets/vosk-model/`, `*.wav`, `*.log`, `*-preview.png`, caches) e fazer o commit inicial **antes de qualquer alteração de código**.
7. **Recriar o `.venv`** na nova pasta (não copiar o antigo) e instalar os requirements. Se o modelo Vosk não foi copiado, usar `setup-voice.sh`.
8. **Atualizar todos os caminhos absolutos** em `install-service.sh`, `install-desktop.sh`, `aurora.desktop`, `run.sh`, `start-alpha.sh` e `uninstall-service.sh`. Antes de reinstalar, rodar o `uninstall-service.sh` da instalação antiga para não ficar um `aurora.service` apontando para a pasta velha. Depois reinstalar e conferir com `systemctl --user status aurora.service`.
9. **Manter `~/.config/aurora` como está.** Não perder `aurora-settings.json` nem a memória local do usuário.

Aceite: a Aurora sobe pelo serviço a partir de `~/Projects/aurora/`, responde ao wake word, o repositório git tem o commit inicial, e a pasta antiga continua intacta para o usuário apagar quando quiser. Ao terminar, informe o caminho final e quais arquivos foram alterados nos scripts.

## 4. Fase 1 — Modularização (sem mudar comportamento)

Hoje o `aurora.py` tem ~2000 linhas misturando tudo. Dividir em um pacote, por exemplo:

```
aurora/
  config.py          # settings_load/save, local_endpoint, hardware_profile
  memory.py          # memória local explícita (lembre-se / esqueça)
  system/            # apps.py, windows.py, volume.py, files.py, hardware.py
  web/               # providers/, fetch.py, parsers.py, freshness.py, pipeline.py
  llm/               # ollama.py (Inference, warmup), prompts.py, tools.py
  voice/             # wake.py (LocalVoice), stt.py, tts.py (Speaker)
  ui/                # orb.py (AuroraOrb), orb.qml
  service.py         # AuroraService (orquestração)
  main.py
tests/
```

Regras da fase:

- Mover funções por camada, mantendo nomes e assinaturas. Imports explícitos, sem import circular.
- A classe `AuroraService` deve ficar apenas como orquestradora: decide o caminho e delega. Lógica de negócio sai dela.
- Escrever testes (`pytest`) para o que é puro e não depende de GUI: `parse_local_command`, `spoken_percentage`, resolução de pastas naturais, parsers HTML com fixtures salvas, utilitários de data. Rede sempre **mockada** nos testes.
- Antes de remover ou mover qualquer função, liste quem a chama (`grep`) e confirme que nada quebra.
- Corrigir divergências entre README e `aurora-settings.json` (por exemplo contexto 1024 no texto e `num_ctx: 4096` na config). Decida qual é o valor real e deixe um só.
- Verificar se `pyautogui` está realmente em uso; se não estiver, propor remoção (listar, não remover sozinho).
- Aceite: `pytest` verde, a Aurora se comporta igual à versão anterior, e o `aurora.py` antigo deixa de existir (ou vira só um ponto de entrada fino).

## 5. Fase 2 — Busca web atual e genérica (prioridade máxima)

### Problema a resolver

A Aurora às vezes responde com informação antiga. Além disso, exemplos do usuário viraram funções fixas no código (`robux_price_answer`, `currency_rate_answer`, `minecraft_java_latest_release` e semelhantes). Isso está errado e deve ser desfeito.

### O que remover

- Todas as funções e ramos ligados a assuntos específicos, incluindo os três acima e qualquer outro do mesmo tipo que você encontrar (liste todos no relatório final).
- Listas de assuntos ou marcas dentro de detectores de intenção. Detectores podem usar **sinais linguísticos de atualidade** (palavras como hoje, agora, atual, último, mais recente, quanto custa, quem é o atual) e **tipo de pergunta** (factual vs. conversa), mas nunca tópicos.
- Fica permitido o que é do próprio sistema e não da web: hora e data locais, clima (rota própria já existente), dados do hardware.

### Como deve funcionar (pipeline único para qualquer assunto)

1. **Decidir se busca.** Pergunta factual, ou com sinal de atualidade, ou sobre algo que muda com o tempo → busca. Conversa, opinião e tarefas locais → sem busca. Na dúvida, busque. Evite depender só do Gemma 1B para classificar; combine sinais linguísticos com uma checagem barata.
2. **Montar a consulta.** Curta, com os termos da pergunta e o **ano/data atual do sistema** quando a atualidade importa. Nunca fixar ano no código.
3. **Consultar vários provedores** (Google Notícias RSS para notícia, DuckDuckGo HTML com fallback para Bing, como já existe) em paralelo, com timeouts curtos.
4. **Ranquear** por relevância ao termo da pergunta, por recência (data de publicação via metadados da página, `PageMetadata`, e data na URL) e por autoridade da fonte quando fizer sentido. Descartar fontes com data velha para a janela pedida (reaproveitar `_has_stale_source_date` e similares, que são genéricos).
5. **Ler o conteúdo** das melhores páginas (`web_fetch` com a proteção de URL pública) e extrair trechos relevantes. O resumo é feito localmente.
6. **Responder só com o que as fontes dizem.** Dar o valor ou fato, a fonte e a data dela. Se as fontes divergirem, dizer que divergem. Se não confirmou, dizer "não consegui confirmar" em vez de completar de memória. O prompt do modelo deve proibir explicitamente usar conhecimento próprio quando a fonte não traz o dado.
7. **Cache curto** (minutos) só para evitar buscas repetidas na mesma conversa. Nada de cache longo para dado volátil.
8. **Seguimento de contexto** ("e na semana passada?", "qual a fonte?") continua usando o histórico curto da sessão, sem criar rotas novas.

### Como testar sem hardcode

- Testes em `tests/web/` com **respostas HTTP gravadas (fixtures)** de vários assuntos diferentes. Os assuntos ficam só nos dados de teste, nunca na lógica.
- Casos obrigatórios: fonte com data velha deve ser rejeitada; duas fontes conflitantes; nenhuma fonte confiável (deve admitir que não confirmou); pergunta sem necessidade de busca (não deve buscar).
- Teste de regressão: um teste que falha se aparecer no código de produção uma função com nome ou lógica de assunto específico (por exemplo, varredura simples por nomes proibidos que a Aurora não deve ter).

### Aceite

- Os exemplos antigos (preço, versão de jogo, cotação) continuam funcionando **pelo pipeline genérico**, sem nenhuma função dedicada.
- Uma pergunta nova, de um assunto que nunca foi mencionado antes, também funciona do mesmo jeito.
- Respostas trazem fonte e data. Quando não há confirmação, a Aurora diz isso.

## 6. Fase 3 — Automação de tela no GNOME/Wayland

O Wayland bloqueia mouse e teclado sintéticos de aplicativos comuns, então **primeiro pesquise e relate, depois implemente.** Entregue antes um relatório curto com o que funciona neste Fedora 44 e o custo de cada opção:

1. **Portais do `xdg-desktop-portal`** (RemoteDesktop, Screenshot, GlobalShortcuts): caminho preferido, exige permissão explícita do usuário.
2. **D-Bus do GNOME Shell e acessibilidade (AT-SPI)**: ler a interface e acionar controles de apps compatíveis.
3. **`ydotool`** (precisa de acesso a `uinput`): fallback para teclado e mouse, com atenção a permissões e segurança.
4. Captura de tela + modelo de visão: **só como fase opcional**, e apenas se couber em 4 GB de VRAM sem tirar o Gemma 1B da GPU. Se não couber, descartar.

Regras de implementação:

- Expor ao agente poucas ferramentas, com argumentos tipados e fechados (por exemplo: focar janela, pressionar atalho, digitar texto, clicar em controle por nome acessível, tirar print). O Gemma 4 E2B é pequeno: quanto mais simples o conjunto de ferramentas, melhor.
- **Segurança obrigatória:** confirmação na bolha para ações sensíveis; nunca digitar em campo de senha; lista de apps permitidos configurável; log de tudo que foi executado; parada imediata por comando de voz ("para") ou atalho; indicação visível quando a Aurora estiver controlando a tela.
- Cada ferramenta nova tem teste com a camada de sistema mockada.
- Aceite: demonstração de pelo menos 3 ações reais (por exemplo focar uma janela, digitar texto num app aberto, tirar um print) com confirmação e log, e relatório do que ficou de fora e por quê.

## 7. Fase 4 — Documentação e limpeza

- README alinhado com o que realmente existe (modelos, contextos, o que vai para a internet, limites do Wayland).
- `requirements*.txt` sem duplicatas e sem dependência não usada.
- Seção "Como contribuir/testar" no README: como rodar `pytest`, como subir o serviço, como ver logs.

## 8. Como trabalhar e como responder

- Comece cada tarefa dizendo em 2 ou 3 linhas qual fase está executando e quais arquivos vai tocar.
- Faça commits pequenos, com mensagem clara, ao fim de cada etapa concluída.
- Rode os testes e o smoke test antes de dizer que terminou. Se algo não pôde ser testado aqui (voz, GUI, Wayland), diga isso explicitamente.
- Resposta final em português, curta, nesta ordem: **o que mudou**, **o que foi testado e o resultado**, **o que ficou pendente ou arriscado**, **sugestões que você NÃO implementou**.
- Se o pedido do usuário for ambíguo, faça **uma** pergunta objetiva em vez de adivinhar.
- Em prompts futuros, trate qualquer exemplo do usuário como ilustração do tipo de problema (regra de ouro nº 1).
