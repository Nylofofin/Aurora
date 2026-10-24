# Histórico de versões

## Aurora Desktop 1.7.1-beta.3 — Cygnus X-1 Private Memory Hardening, 2026-10-24 (pré-release beta)

- Preferências da memória pessoal passam a ser gravadas com permissão `600`, e a leitura restringe permissões de arquivos legados já existentes.
- Arquivos temporários de atualização também são privados; a gravação agora faz flush e `fsync` antes da substituição atômica.
- O arquivo de memória legado existente foi mantido e teve suas permissões restringidas; nenhuma preferência foi removida.

## Aurora Desktop 1.7.1-beta.2 — Cygnus X-1 Hardware Query Recovery, 2026-10-24 (pré-release beta)

- Perguntas naturais sobre os componentes do próprio computador agora são roteadas diretamente à ferramenta local de hardware, sem depender do modelo para iniciar a consulta.
- A coleta de CPU, memória, GPU e armazenamento roda em trabalhador separado; a resposta falada é formada com os dados coletados.
- Testes de regressão cobrem variações de frase, rejeição de pedidos de pesquisa/upgrade e desvio da etapa de inferência.

## Aurora Desktop 1.7.1-beta.1 — Gaia BH1 Resumable Local Timers, 2026-10-24 (pré-release beta)

- Revisita a rotina de saúde local: as consultas continuam somente de leitura, paralelas e limitadas; estados parciais e fontes indisponíveis permanecem explícitos.
- Melhora o controle local de aplicativos Flatpak: falhas imediatas do processo não são anunciadas como sucesso, e início do processo não é confundido com janela visível.
- Adiciona pausa e retomada por voz para timers persistentes: diga “pause o timer 2”, “retome o timer 2” ou omita o número quando existir exatamente um timer.
- A pausa conserva o tempo restante mesmo após reinício do serviço; com vários timers ativos, Aurora pede o número em vez de escolher um.
- Não é uma versão estável; a compatibilidade de Flatpak, PackageKit, firmware e voz ainda depende do sistema local.

## Aurora Desktop 1.7.0-alpha.1 — Cygnus X-1 Local Health Parallelism, 2026-10-24 (pré-release)

- Experimenta verificações paralelas de PackageKit, Flatpak e firmware na rotina local, limitadas a dois workers e reduzidas ainda mais sob carga ou memória baixa.
- Mantém a consulta de Flatpak do usuário e do sistema sequencial para evitar concorrência em seus serviços locais.
- Preserva resultados parciais quando uma fonte local falha; a rotina não instala nem altera nada durante a checagem.
- Permite pedir ao agente uma checagem local e somente de leitura do estado do sistema; resultados e indisponibilidades são entregues estruturados, sem afirmar que o PC está atualizado quando uma fonte falhar.
- A checagem falada usa uma resposta direta baseada nos dados locais em vez de uma segunda inferência Gemma, reduzindo latência e evitando paráfrases que possam distorcer estados ou contagens.
- A abertura de Flatpak detecta encerramento imediato com código de erro e não diz que uma janela abriu quando só foi possível confirmar o início do processo.
- Não é estável; mede a responsividade da rotina no Fedora real antes da próxima promoção.

## Aurora Desktop 1.6.0 — Bellatrix Stability Baseline, 2026-10-24 (release estável)

- Declara a primeira release estável da geração Altair, com versão/build sincronizadas entre aplicação, README e Launchpad.
- Corrige o roteamento de perguntas explicitamente sobre o computador local: elas chegam ao agente local antes da busca factual automática; pedidos explícitos de pesquisa continuam na web.
- Mostra imediatamente o cartão de interpretação para pedidos do agente, com progresso por etapa e fontes quando uma ferramenta realmente consulta a web.
- Mantém pesquisas independentes limitadas pela carga e RAM disponíveis, sem iniciar modelos adicionais.
- Validação desta build: `scripts/check-desktop-release.sh`; a compatibilidade real de voz, portais e integrações externas continua dependente do ambiente documentado no README.

## Aurora Desktop 1.5.7 — Altair Routine & Reliability, 2026-10-23 (pré-release)

Build experimental e **não estável**, publicada para testes antes da futura 1.6.0 Stable.

- Adiciona uma rotina local de verificação após desbloquear a sessão, com saudação e checagem de atualizações quando disponíveis.
- Adiciona timers locais persistentes, retomados após reinício do serviço.
- Mantém a escuta para respostas de esclarecimento de ações e reduz a latência inicial da voz Edge TTS.
- Reforça a preferência por português brasileiro e reduz anúncios repetidos de verificações indisponíveis.
- Adiciona geração local de relatórios de erro com redação de dados sensíveis; o envio exige ação explícita do usuário.
- Testes cobrem timers, rotina, fluxo de esclarecimento, voz e relatórios. Integrações reais dependem da sessão Fedora/GNOME e ainda requerem validação manual.

## Aurora Desktop 1.5.0-alpha.1 — Orchestra, 2026-10-23

Pré-release pública para demonstração e avaliação técnica. Não representa uma versão estável nem promete compatibilidade entre distribuições.

- Endurece o runtime após a 1.4.0 ORC, incluindo cálculo aritmético local e ajustes de roteamento, dependências, busca, cartões e animações.
- Desativa por padrão o servidor LAN do Companion arquivado e documenta a descontinuação do cliente Android.
- Substitui os efeitos de áudio sem redistribuição confirmada por sinais CC0, com origem e licença registradas.
- Remove APKs e tags de release Android do histórico Git publicado.
- Adiciona o RPM experimental Aurora Launchpad para Fedora Workstation, com verificação do ambiente, instalação guiada e limpeza opcional.
- Mantém também a instalação manual por scripts/código-fonte; ainda não fornece Flatpak nem atualizador automático.
- **Limites de demonstração:** voz/STT e Edge TTS dependem da internet; resultados web podem variar por bloqueios e atualidade; OBS, captura e automação dependem do desktop e das permissões locais. Faça revisão humana das ações e dos resultados.

## 1.4.0 — Orchestra Runtime Coordination (ORC), 2026-10-23

- Divide pesquisas compostas em até três consultas web independentes, com limite de concorrência adaptado à carga e à memória.
- Permite até duas inspeções locais independentes em paralelo; ações que alteram estado continuam sequenciais.
- Adiciona cartões de progresso contextual para pesquisas e inspeções locais.
- Mantém uma única inferência Gemma para sintetizar resultados e preserva os limites de fontes e segurança do pipeline existente.
- Não inclui pacotes Flatpak/RPM, atualização automática ou suporte Android ativo.

## 1.3.0 — Lumen Desktop Runtime (LDR), 2026-10-23

- Formaliza a identidade técnica LDR e o identificador da build no cliente e nos logs.
- Adiciona cartões de informação experimentais e refinamentos visuais da bolha.
- Inclui checagens automatizadas de compilação, testes e scripts no GitHub Actions.

## 1.0.2 — Polaris-Edge, Patch 2 (pré-release, 2026-10-22)

- Separa OBS, captura pelo portal, Spotify e registro de ações em módulos dedicados sob `aurora_core/system/`, mantendo a fachada de compatibilidade.
- Aguarda a propagação assíncrona do estado do OBS antes de confirmar início/parada da gravação; testes cobrem estado atrasado e estado que nunca muda.
- Atualiza a documentação para distinguir minimização do OBS de execução realmente sem janela.
- Inclui os commits locais posteriores a 1.0.1; 227 testes automatizados passaram.
- **Limite conhecido:** a sessão atual do OBS iniciou em Safe Mode e desativou `obs-websocket`; gravação real em segundo plano ainda não foi confirmada. Esta publicação é pré-release.
- A classe `AuroraService` ainda contém lógica de coordenação que precisa de uma etapa posterior de modularização.

## 1.0.1 — Polaris-Edge, Patch 1 (2026-10-22)

- Passa a janela X11 da bolha ao portal de screenshot e unifica pedidos diretos e pedidos do Gemma no mesmo worker assíncrono.
- Registra em qual etapa o portal de captura ou o início do OBS falhou, sem gravar conteúdo capturado, caminhos fornecidos ou senhas.
- Classifica resultados de automação como concluídos, aceitos pelo sistema ou falhos, sem persistir o texto retornado.
- 217 testes automatizados passaram. Não foi possível validar captura real nem gravação real nesta sessão; o OBS não estava ativo.

## 1.0.0 — Polaris-Edge, Geração 1 (2026-10-22)

Primeira release oficial da Aurora para uso pessoal; o código-fonte está publicado no GitHub.

- Bolha flutuante persistente, chamada por wake word local, com voz e animação de estados.
- Conversa local com Gemma via Ollama e execução de ações locais com confirmações para operações sensíveis.
- Busca web genérica com provedores públicos, leitura de páginas, filtros de relevância/atualidade e resposta sem completar fatos não confirmados.
- Integrações locais para captura de tela, controle de aplicativos/janelas compatíveis, Spotify e gravação pelo OBS WebSocket.
- Instalador nativo por scripts, serviço `systemd --user`, diagnóstico somente leitura e testes automatizados.

### Limites conhecidos desta release

- Destinada ao desktop Linux; Wayland, XWayland, portais e suporte AT-SPI variam conforme o ambiente.
- A busca depende de provedores e páginas públicas acessíveis; bloqueios, captchas e páginas sem datas podem impedir confirmação.
- Wake word é local, mas a transcrição Google e a voz Edge TTS dependem da internet.
- Ollama e os modelos Gemma são instalados à parte. Não há atualização automática, pacote Flatpak/RPM nem workflow de CI.
- OBS, Spotify e captura de tela dependem de configuração e permissões locais. A integração OBS tem testes automatizados, mas não foi possível validar uma gravação real nesta sessão de publicação porque o OBS/WebSocket não estava ativo.
