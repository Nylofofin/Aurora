# Aurora — POLARIS-EDGE

**Versão:** `0.1.0a1` (Alpha InDev, PEP 440) · **Build:** `AUR-20261022.01`
**Codinome técnico:** `POLARIS-EDGE` — identidade da build local otimizada para execução no edge, com Gemma via Ollama e alvo gráfico AMD Polaris.

> **Alpha privada e incompleta.** Esta build é para uso e refinamento pessoal; ainda pode conter falhas de voz, busca, interface e integrações. Não é uma versão estável nem um pacote pronto para outras distribuições. A release do GitHub deve permanecer privada.

**A única interface da Aurora é a bolha flutuante.** Não há janela de chat nem janela de resultados. Em espera fica escondida; ao dizer “Aurora”, aparece no canto inferior direito com uma entrada animada e o som `assets/audio/entrada.wav`. Cada ativação recebe um pedido; depois de responder, a bolha desaparece e o microfone volta a aguardar apenas a palavra “Aurora”. O contexto curto pode ajudar em um seguimento, mas não mantém a captura de voz aberta entre ativações. Clique com o botão direito na bolha para interromper imediatamente a fala e cancelar o pedido atual. Enquanto estiver visível, você pode arrastá-la para qualquer lugar. A esfera compacta mistura azul e violeta em camadas luminosas com animação contínua; o rótulo de alto contraste indica se está ouvindo, pensando, buscando ou falando. Inferência do Gemma, memória e roteamento de ações são locais. Transcrição de voz, síntese de voz, busca web e serviços externos descritos abaixo usam a internet quando solicitados.

## Perfil deste computador

- Fedora Linux 44, GNOME/Wayland; o lançador usa XWayland quando está disponível para permitir a janela flutuante sempre no topo.
- Intel Core i5-2300, 4 núcleos, sem AVX2.
- 12 GB de RAM.
- AMD Radeon RX 470 (PCI da família Ellesmere), **4 GB de VRAM** confirmados em `/sys`. A verificação com `ollama ps` confirmou o Gemma 3 1B usando 100% GPU via Vulkan; Aurora reserva todo o offload compatível para esse modelo leve.
- Modelo de conversa: `gemma3:1b-it-qat`, contexto efetivo 4096, 4 threads e respostas curtas. Ações complexas que precisam de ferramentas usam `gemma4:e2b-it-q4_K_M`; clima e busca na web usam rotas diretas sem LLM. O Gemma 1B é pré-carregado ao iniciar e permanece na GPU enquanto a Aurora está aberta.

## Estrutura interna

O código está separado por responsabilidade em `aurora_core/`: `system/` contém automação local; `web/` contém parsers, validação e pipeline de busca; `llm/` contém prompts e inferência; `voice/` contém wake word e síntese; `ui/` contém a bolha; `service.py` coordena esses componentes. `aurora.py` permanece como ponto de entrada e compatibilidade para ferramentas existentes. A separação não altera contratos nem comportamento da build.

## Inicialização

Aurora usa hoje um **instalador nativo em shell**, adequado para esta Alpha pessoal no Fedora/GNOME: integra o serviço de usuário, Ollama local e ferramentas do desktop. Não há pacote Flatpak ou RPM nesta build. Flatpak exigiria desenhar e validar permissões para microfone, portais, OBS, Spotify e abertura/controle de apps; RPM faria sentido depois que a instalação e as dependências estiverem estáveis. A instalação atual usa Python virtualenv e scripts versionados, sem instalar arquivos do app em diretórios globais.

1. Instale Ollama para sua distribuição e baixe os dois modelos: `ollama pull gemma3:1b-it-qat` e `ollama pull gemma4:e2b-it-q4_K_M`.
2. Clone o repositório privado e entre na pasta `Aurora-Assistant` (ou na pasta escolhida para o clone).
3. Execute `./setup-voice.sh`. Isso instala as dependências de voz e baixa o modelo Vosk em português para `assets/vosk-model/`.
4. Execute `./install-desktop.sh`. O script cria o ambiente virtual e instala as dependências Python na primeira inicialização, instala o serviço `systemd --user`, habilita o início com a sessão gráfica e cria um atalho no menu.
5. Confira com `systemctl --user status aurora.service`; pare ou inicie com `systemctl --user stop aurora.service` e `systemctl --user start aurora.service`. Para remover o serviço, execute `./uninstall-service.sh`.

O serviço usa `start-alpha.sh`, que procura Ollama em `PATH` ou no runtime opcional definido por `AURORA_OLLAMA_RUNTIME_DIR`. O diretório de estado e logs padrão é `~/.local/state/aurora`; para usar um runtime/modelos locais alternativos, configure `AURORA_WORK_DIR`, `AURORA_OLLAMA_RUNTIME_DIR` e, se necessário, `AURORA_OLLAMA_MODELS_DIR` em `~/.config/aurora/runtime.env` (formato `NOME=valor`, uma variável por linha). O serviço carrega esse arquivo se existir. Esses caminhos são configuráveis e não dependem do checkout de desenvolvimento do autor.

As configurações ativas ficam em `~/.config/aurora/aurora-settings.json`, com permissões privadas para o usuário (diretório `700`, arquivo `600`); na primeira inicialização, uma configuração antiga em `aurora-settings.json` na pasta do app é migrada sem apagar o arquivo legado. O `aurora-settings.json` versionado é apenas um modelo sem localização ou preferências pessoais. Endpoint remoto não é aceito: prompt e resposta só vão a `localhost`.

### Testes da busca

Rode a suíte local de parsers, intenção, atualidade, relevância, fontes independentes e cache com `./.venv/bin/python -m pytest -q tests/web`. As respostas HTML de teste ficam em `tests/web/fixtures/`; os testes não fazem requisições à internet.

### Desenvolver e diagnosticar

- Suíte completa: `./.venv/bin/python -m pytest -q`.
- Compilação: `./.venv/bin/python -m compileall -q aurora.py aurora_core aurora_fx.py aurora_integrations.py scripts`.
- Rodar na sessão gráfica: `./run.sh` (ou `./start-alpha.sh`, que inicia Ollama se necessário e disponível).
- Ver logs do serviço: `journalctl --user -u aurora.service -f`.
- O arquivo legado `requirements-control.txt` ainda lista `pyautogui`, mas nenhuma ferramenta da Aurora o utiliza ou expõe; a dependência ficou fora do caminho de instalação. A remoção do arquivo é uma decisão pendente conforme a regra do projeto. O controle de janelas depende de `wmctrl`/`xdotool` quando presentes.

## Voz

O reconhecimento local Vosk fica ouvindo a palavra de ativação “Aurora”, em blocos de 200 ms. Após a ativação, captura um pedido e não reabre a escuta até outro wake word. A fala de entrada continua em português brasileiro (`pt-BR`). Você pode pedir “fale em inglês”, espanhol ou outro idioma; a preferência vale até pedir para voltar ao português brasileiro ou encerrar a Aurora. Cada trecho reconhecido é enviado ao reconhecimento de fala do Google (`recognize_google`, idioma `pt-BR`) com timeout de 2 s e fallback para a transcrição local. O texto da resposta é convertido em voz pelo Edge TTS com `pt-BR-ThalitaMultilingualNeural` (Thalita Multilingual), não Francisca. Se uma frase gerada vier em inglês sem ter sido solicitada, Aurora tenta traduzi-la localmente para o idioma escolhido. Emojis e descrições comuns de emoji são removidos da voz. O áudio de cada fala vai ao Google e a resposta escrita vai ao serviço online do Edge TTS; a detecção da palavra de ativação e os modelos Gemma continuam locais. `./setup-voice.sh` instala as dependências e baixa o modelo Vosk pequeno em português para `assets/vosk-model`.

## Agente interno

Gemma 4 pode chamar ferramentas locais para abrir ou fechar aplicativos, controlar janelas quando o gerenciador permitir, consultar o volume em percentual e estado de mudo, ajustar volume (o aumento consulta o nível atual, para em 100% e falha fechado se não conseguir consultá-lo), identificar CPU/RAM/GPU/discos, criar arquivos em pastas naturais e guardar preferências solicitadas explicitamente. O resolvedor entende Documentos, Área de Trabalho, Downloads, pastas conhecidas, nomes exatos e caminhos completos; uma busca de pasta interrompida pelo limite de varredura pede o caminho completo para evitar escolher um destino ambíguo; arquivos existentes nunca são substituídos. Fechar aplicativos e outras ações sensíveis pedem confirmação na bolha; cada aprovação expira após 90 segundos e cliques tardios não executam a ação. Conversa cotidiana, opiniões e desabafos seguem direto para o modelo local; fatos externos e atuais, notícias, guias, tutoriais e instruções seguem pelo pipeline de pesquisa. Notícias brasileiras usam o feed regional do Google Notícias; pedidos internacionais mudam a região do feed, enquanto a resposta continua no idioma escolhido. Consultas de notícia também usam DuckDuckGo Lite e Bing RSS como fontes adicionais e fallback se o feed do Google falhar. O feed do Google Notícias tem limite de 3,5 s para não prender a tentativa dos outros provedores. Buscas gerais consultam DuckDuckGo Lite e Bing RSS em paralelo; se a consulta completa não trouxer resultados utilizáveis, tentam também uma formulação compacta que mantém os termos do assunto. O pipeline abre até duas páginas gerais e extrai trechos e datas disponíveis. Perguntas com sinal explícito de atualidade recebem o ano vigente na consulta; páginas fora da janela pedida são descartadas e fatos atuais exigem duas fontes datadas independentes. Resultados positivos ficam em cache por até 90 segundos. O resumo é feito localmente e deve usar somente a evidência encontrada; quando a busca não confirma, a Aurora deve admitir isso. A data da publicação pode não estar disponível em toda página, e bloqueios dos sites podem limitar a verificação. O histórico curto fica apenas em memória local para apoiar seguimentos após uma nova ativação. Mouse e teclado ficam bloqueados sob Wayland; maximizar/minimizar depende de `wmctrl` ou `xdotool` e de o compositor expor a janela.

### Ações rápidas e integrações

Comandos explícitos para abrir um site com domínio/URL, abrir um aplicativo instalado, solicitar captura de tela, tocar música no Spotify ou iniciar/parar gravação no OBS são reconhecidos antes do Gemma. O Gemma não confirma uma ação: Aurora só fala sucesso depois que o sistema ou serviço confirma. Sites exigem URL ou a expressão “site”; nomes de aplicativos seguem os catálogos `.desktop` do sistema, incluindo os exports de Flatpak e Snap, evitando tratar automaticamente um nome ambíguo como site. O fechamento de Flatpaks usa o ID e a instância reportados por `flatpak ps`, sem adivinhar o PID interno. Capturas passam pelo portal de screenshot do desktop e são salvas em `Imagens/Aurora/` com data, hora e nome exclusivo. O portal do GNOME pode apresentar uma confirmação do sistema.

Para Spotify, crie um app pessoal no [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), cadastre exatamente o redirect URI `http://127.0.0.1:43827/callback` e coloque o Client ID em `spotify_client_id` dentro de `aurora-settings.json`. Depois diga “conectar Spotify” e aprove o acesso na página aberta. A autorização usa OAuth PKCE; o token é salvo com permissão somente para o usuário em `~/.config/aurora/spotify-token.json`. Requer conta Premium e um dispositivo Spotify Connect ativo; a Aurora controla esse dispositivo, não baixa nem toca áudio por conta própria. O nome da faixa vai à API do Spotify e não é enviado ao Gemma.

Para OBS (inclusive o Flatpak `com.obsproject.Studio`), habilite **WebSocket Server** em Ferramentas → Configurações do servidor WebSocket. No Flatpak, as preferências ficam no diretório isolado do app, em `~/.var/app/com.obsproject.Studio/config/obs-studio/`; configure pela interface do OBS. A conexão da Aurora fica em loopback (`127.0.0.1`), tem limite total de 1,5 segundo e lê a porta e a senha do perfil Flatpak sem colocá-las nos logs. Neste computador, a configuração do OBS indica que o servidor está desativado; Aurora agora explica como habilitá-lo quando você pedir uma gravação. Para OBS instalado fora do Flatpak, se a autenticação estiver ligada, salve `AURORA_OBS_PASSWORD=...` em `~/.config/aurora/obs.env` com permissão `600` e adicione `EnvironmentFile=%h/.config/aurora/obs.env` em `systemctl --user edit aurora.service`. Diga “comece a gravar minha tela” ou “pare de gravar a tela”. O início pede confirmação pela bolha; parar é imediato. Se OBS estiver fechado ou a gravação for recusada, Aurora informa que não confirmou a ação. A indicação **CONTROLANDO** aparece durante a captura e os comandos OBS. Ações dessas integrações são registradas localmente em `~/.local/state/aurora/actions.jsonl`, sem gravar tokens ou senhas no log.

## Adaptação local

As respostas comuns mantêm o Gemma 3 1B rápido, com mais espaço de saída quando o pedido pede explicação. Tarefas com ferramentas usam mais contexto e resposta para o Gemma 4. Preferências entram na memória local apenas quando a pessoa pede explicitamente para lembrar; “lembre-se...” salva e “esqueça...” remove. Isso personaliza instruções e contexto, mas não altera os pesos do Gemma: um fine-tuning real exige exemplos de treino revisados e um processo de treinamento e avaliação, que ainda não está configurado.

## Limites atuais

- Ollama e os modelos Gemma precisam ser instalados/baixados uma vez. `start-alpha.sh` aceita um runtime Ollama opcional via `AURORA_OLLAMA_RUNTIME_DIR`; sem isso, usa o Ollama instalado no sistema. A configuração local de runtime não faz parte do repositório.
- A palavra de ativação roda localmente, mas a transcrição e a voz Edge TTS precisam de internet. `recognize_google` usa uma chave genérica indicada pelo projeto SpeechRecognition para uso pessoal/testes; o projeto avisa que ela pode ser revogada.
- A busca e leitura de páginas usam conexões HTTP(S) diretas, sem proxies definidos por variáveis de ambiente, para conectar ao IP público validado e impedir que uma mudança de DNS redirecione a chamada para uma rede privada. Resoluções públicas verificadas ficam em cache por 10 segundos, com limite de 256 domínios.
- Não há ainda instalador gráfico, Flatpak, RPM, atualização automática, workflow de CI ou canal de atualização. A instalação por shell foi escolhida para a Alpha privada; revise os scripts antes de executá-los em qualquer outra máquina.
- O Gemma 3 1B é pré-aquecido em segundo plano usando o mesmo endpoint de chat e as mesmas opções de inferência da Aurora. No smoke test após inicialização, a primeira resposta curta começou em 0,21 s e terminou em 0,27 s; esse número depende da pergunta e não representa respostas longas. O modelo ficou em 100% GPU via Vulkan. O Gemma 4 para tarefas de agente continua mais lento neste hardware.
- O serviço fixa `QT_QPA_PLATFORM=xcb` para renderizar a bolha pelo XWayland nesta sessão Wayland; o backend Wayland direto não oferece a opacidade e o posicionamento necessários para essa animação. Transparência e always-on-top ainda dependem de XWayland/Mutter e das regras do GNOME.

## Referências de compatibilidade

O catálogo Ollama lista Gemma 3 QAT em 270M e 1B, e Gemma 4 E2B em 4,6 GB. O modelo 270M foi medido, mas descartado para conversa por qualidade insuficiente. Vosk lista `vosk-model-small-pt-0.3` com 31 MB.

- [Gemma 3 e QAT (Ollama)](https://ollama.com/library/gemma3)
- [Tag Gemma 4 E2B quantizada (Ollama)](https://ollama.com/library/gemma4/tags)
- [GPU e backend Vulkan (Ollama)](https://github.com/ollama/ollama/blob/main/docs/gpu.mdx)
- [Modelos de português Vosk](https://alphacephei.com/vosk/models)
- [Edge TTS (voz Thalita Multilingual)](https://github.com/rany2/edge-tts)
- [Reconhecimento Google usado por SpeechRecognition](https://github.com/Uberi/speech_recognition#google-cloud-speech)
- [Comportamento e controles do ChatGPT Voice](https://help.openai.com/en/articles/20001274-chatgpt-voice)

O clima usa Open-Meteo com geolocalização aproximada por IP (ipwho.is), consultada apenas quando o clima é solicitado e mantida em cache local por 24 horas. A localização por IP não é GPS e pode errar a cidade; para maior precisão, diga “tempo em [cidade]”. A rede recebe o IP público para localizar a cidade e as coordenadas usadas no pedido de clima.
