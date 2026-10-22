# Aurora — Alpha InDev

**A única interface da Aurora é a bolha flutuante.** Não há janela de chat nem janela de resultados. Em espera fica escondida; ao dizer “Aurora”, aparece no canto inferior direito com uma entrada animada e o som `assets/audio/entrada.wav`. Cada ativação recebe um pedido; depois de responder, a bolha desaparece e o microfone volta a aguardar apenas a palavra “Aurora”. O contexto curto pode ajudar em um seguimento, mas não mantém a captura de voz aberta entre ativações. Clique com o botão direito na bolha para interromper imediatamente a fala e cancelar o pedido atual. Enquanto estiver visível, você pode arrastá-la para qualquer lugar. A esfera compacta mistura azul e violeta em camadas luminosas com animação contínua; o rótulo de alto contraste indica se está ouvindo, pensando, buscando ou falando. Pesquisas e clima são resumidos em voz, com distinção entre o que as fontes dizem e o que não foi confirmado.

## Perfil deste computador

- Fedora Linux 44, GNOME/Wayland; o lançador usa XWayland quando está disponível para permitir a janela flutuante sempre no topo.
- Intel Core i5-2300, 4 núcleos, sem AVX2.
- 12 GB de RAM.
- AMD Radeon RX 470 (PCI da família Ellesmere), **4 GB de VRAM** confirmados em `/sys`. A verificação com `ollama ps` confirmou o Gemma 3 1B usando 100% GPU via Vulkan; Aurora reserva todo o offload compatível para esse modelo leve.
- Modelo de conversa: `gemma3:1b-it-qat`, contexto 1024, 4 threads e respostas curtas. Ações complexas que precisam de ferramentas usam `gemma4:e2b-it-q4_K_M`; clima e busca na web usam rotas diretas sem LLM. O Gemma 1B é pré-carregado ao iniciar e permanece na GPU enquanto a Aurora está aberta.

## Inicialização

1. Instale Ollama e rode `ollama pull gemma3:1b-it-qat` e `ollama pull gemma4:e2b-it-q4_K_M`.
2. Na pasta da Aurora, execute `./install-desktop.sh`. O instalador cria o serviço `systemd --user`, habilita o início com a sessão gráfica e mantém um atalho no menu. O ambiente virtual fica em `.venv` dentro da pasta da Aurora.
3. Consulte `systemctl --user status aurora.service`; pare ou inicie com `systemctl --user stop aurora.service` e `systemctl --user start aurora.service`. Para remover o serviço, execute `./uninstall-service.sh`.

Os parâmetros ajustáveis estão em `aurora-settings.json`, na pasta do app. Endpoint remoto não é aceito: prompt e resposta só vão a `localhost`.

### Testes da busca

Rode a suíte local de parsers, intenção, atualidade, relevância, fontes independentes e cache com `./.venv/bin/python -m pytest -q tests/web`. As respostas HTML de teste ficam em `tests/web/fixtures/`; os testes não fazem requisições à internet.

## Voz

O reconhecimento local Vosk fica ouvindo a palavra de ativação “Aurora”, em blocos de 200 ms. Após a ativação, captura um pedido e não reabre a escuta até outro wake word. A fala de entrada continua em português brasileiro (`pt-BR`). Você pode pedir “fale em inglês”, espanhol ou outro idioma; a preferência vale até pedir para voltar ao português brasileiro ou encerrar a Aurora. Cada trecho reconhecido é enviado ao reconhecimento de fala do Google (`recognize_google`, idioma `pt-BR`) com timeout de 2 s e fallback para a transcrição local. O texto da resposta é convertido em voz pelo Edge TTS com `pt-BR-ThalitaMultilingualNeural` (Thalita Multilingual), não Francisca. Se uma frase gerada vier em inglês sem ter sido solicitada, Aurora tenta traduzi-la localmente para o idioma escolhido. Emojis e descrições comuns de emoji são removidos da voz. O áudio de cada fala vai ao Google e a resposta escrita vai ao serviço online do Edge TTS; a detecção da palavra de ativação e os modelos Gemma continuam locais. `./setup-voice.sh` instala as dependências e baixa o modelo Vosk pequeno em português para `assets/vosk-model`.

## Agente interno

Gemma 4 pode chamar ferramentas locais para abrir ou fechar aplicativos, controlar janelas quando o gerenciador permitir, ajustar volume, identificar CPU/RAM/GPU/discos, criar arquivos em pastas naturais e guardar preferências solicitadas explicitamente. O resolvedor entende Documentos, Área de Trabalho, Downloads, pastas conhecidas, nomes exatos e caminhos completos; arquivos existentes nunca são substituídos. Fechar aplicativos pede confirmação na bolha. Conversa cotidiana, opiniões e desabafos seguem direto para o modelo local; fatos externos e atuais, notícias, guias, tutoriais e instruções seguem pelo pipeline de pesquisa. Notícias brasileiras usam o feed regional do Google Notícias; pedidos internacionais mudam a região do feed, enquanto a resposta continua no idioma escolhido. Buscas gerais consultam DuckDuckGo Lite e Bing RSS em paralelo; se a consulta completa não trouxer resultados utilizáveis, tentam também uma formulação compacta que mantém os termos do assunto. O pipeline abre até duas páginas gerais e extrai trechos e datas disponíveis. Perguntas com sinal explícito de atualidade recebem o ano vigente na consulta; páginas fora da janela pedida são descartadas e fatos atuais exigem duas fontes datadas independentes. Resultados positivos ficam em cache por até 90 segundos. O resumo é feito localmente e deve usar somente a evidência encontrada; quando a busca não confirma, a Aurora deve admitir isso. A data da publicação pode não estar disponível em toda página, e bloqueios dos sites podem limitar a verificação. O histórico curto fica apenas em memória local para apoiar seguimentos após uma nova ativação. Mouse e teclado ficam bloqueados sob Wayland; maximizar/minimizar depende de `wmctrl` ou `xdotool` e de o compositor expor a janela.

## Adaptação local

As respostas comuns mantêm o Gemma 3 1B rápido, com mais espaço de saída quando o pedido pede explicação. Tarefas com ferramentas usam mais contexto e resposta para o Gemma 4. Preferências entram na memória local apenas quando a pessoa pede explicitamente para lembrar; “lembre-se...” salva e “esqueça...” remove. Isso personaliza instruções e contexto, mas não altera os pesos do Gemma: um fine-tuning real exige exemplos de treino revisados e um processo de treinamento e avaliação, que ainda não está configurado.

## Limites atuais

- Ollama e o modelo Gemma precisam ser instalados/baixados uma vez. No desenvolvimento, `start-alpha.sh` usa o runtime local da pasta `work/` quando disponível e desliga recursos de nuvem.
- A palavra de ativação roda localmente, mas a transcrição e a voz Edge TTS precisam de internet. `recognize_google` usa uma chave genérica indicada pelo projeto SpeechRecognition para uso pessoal/testes; o projeto avisa que ela pode ser revogada.
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
