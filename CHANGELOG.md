# Histórico de versões

## Aurora Desktop 3.0.0e — Vega Voice & Wake, 2026-10-25 (release estável)

- Ajusta o Supertonic para cinco passos, equilibrando qualidade vocal e latência no hardware de referência.
- Torna a ativação por nome mais criteriosa: a gramática limitada já não ativa a Aurora sozinha; o reconhecimento livre precisa confirmar o nome com confiança por palavra.
- Mantém o treinamento acústico local para nomes personalizados fora do vocabulário do Vosk.
- Atualiza o Launchpad para 0.4.8-1, reconhece tags estáveis no formato compacto `3.0.0e` e corrige a identificação da versão após a autoatualização.
- Adiciona uma demonstração animada do onboarding à descrição da release.

## Aurora Desktop 2.1.2 — Rigel Update Integrity, 2026-10-25 (release estável)

- Torna a atualização da Aurora transacional: prepara os arquivos antes da troca, preserva dados locais e recupera a versão anterior se a ativação falhar.
- Atualiza o Launchpad para 0.4.6-1, com nova tentativa para consultas ao GitHub e sem baixar de novo modelos já instalados.
- Adiciona três assinaturas sonoras originais para a entrada e a saída da bolha.
- Reescreve o README e inclui GIFs da bolha, uma prancha das skins e um tour em vídeo do onboarding.

## Aurora Desktop 2.1.1 — Capella Interface Polish, 2026-10-25 (release estável)

- Reduz a latência inicial da síntese local com blocos de áudio menores e menos etapas de denoising no Supertonic.
- Refina o onboarding e o Launchpad com etapas mais compactas, transições mais claras e carrossel de SFX com prévias separadas.
- Cria três pares de sons de entrada e saída com assinaturas sonoras próprias e mantém a seleção visível durante a personalização.
- Atualiza o Aurora Launchpad para 0.4.5-1, que troca a lista de builds por um botão único para instalar a release estável mais recente preservando perfil, nome, voz, aparência, memória, configurações e modelos locais.

## Aurora Desktop 2.1.0 — Proxima Local Voice, 2026-10-25 (release estável)

- Adiciona transcrição local de comandos com Whisper.cpp Base Q5, mantendo o Vosk local para wake word e interrupção.
- Oferece Faber/Piper e dez estilos Supertonic 3 como motores locais opcionais; somente o motor selecionado é preparado e carregado.
- Alinha geometria, reflexos e movimento contínuo das seis bolhas do onboarding aos protótipos visuais.
- Amplia o diagnóstico e a telemetria local de voz e atualiza dependências e instruções de instalação.
- Atualiza o Aurora Launchpad para 0.4.1-1.

## Aurora Desktop 2.0.1 — Interface Fix, 2026-10-25 (patch estável)

- Corrige o espaçamento vertical excessivo no onboarding.
- Evita sobreposição entre previews das skins, legendas e botões.
- Reorganiza campos e cartões para telas horizontais.
- Separa os previews de SFX em controles individuais de entrada e saída.

## Aurora Desktop 2.0.0a — Kepler-452b, 2026-10-25 (release estável)

- Reorganiza o onboarding em uma composição horizontal, com campos e cartões que não se sobrepõem.
- Corrige o contraste dos textos e melhora a legibilidade dos controles no tema escuro.
- Amplia a transição entre etapas com deslocamento elástico e fade sincronizados.
- Refina os seis estilos de orb e renova os SFX temáticos com assinaturas rítmicas distintas.
- Atualiza o Launchpad para 0.4.0-2.

## Aurora Desktop 1.9.2 — Launchpad Update Fix, 2026-10-24 (release estável)

- Compacta e escurece o onboarding e o Launchpad.
- Adiciona três pares originais de feedback sonoro selecionáveis.
- Reduz ativações falsas de perfis de wake personalizados.
- Corrige a identidade da build usada pelo Launchpad para verificar atualizações.

## Aurora Desktop 1.8.6 — Sirius Control Panel, 2026-10-24 (release estável)

- Adiciona ao Launchpad uma seção para reabrir a personalização de nome, voz e estilo.
- Preserva escolhas existentes até o usuário concluir o novo onboarding.
- Fecha aplicativos Flatpak pelo ID da instância antes de depender de janelas X11, funcionando melhor em Wayland.
- Torna a comparação de processos independente de maiúsculas e minúsculas.

## Aurora Desktop 1.8.5 — Sirius Onboarding Migration, 2026-10-24 (release estável)

- Migra automaticamente marcadores antigos de primeira instalação.
- Permite que o onboarding apareça após logout/login sem reinstalar a Aurora.
- Preserva o comportamento de espera quando o serviço inicia pela primeira vez na sessão da instalação.

## Aurora Desktop 1.8.4 — Sirius Session Onboarding, 2026-10-24 (release estável)

- Dispara o onboarding no próximo login, mesmo quando a instalação terminou sem reinicialização.
- Oferece no Launchpad as opções explícitas de reiniciar ou encerrar a sessão.
- Mantém compatibilidade com marcadores antigos baseados no boot.

## Aurora Desktop 1.8.3 — Sirius Clean Desktop, 2026-10-24 (release estável)

- Remove a integração Spotify, o fluxo OAuth, o token local e a configuração `spotify_client_id`.
- Remove a ferramenta de reprodução musical do agente e o roteamento local correspondente.
- Mantém o desktop focado em automação local, pesquisa, voz, captura e OBS.

## Aurora Desktop 1.8.2 — Sirius Orb Motion, 2026-10-24 (release estável)

- Reimagina o movimento da superfície da bolha com refração e reflexo contínuos.
- Alinha as prévias animadas dos três estilos do onboarding à bolha real.
- Preserva a seleção de estilo, voz e perfil de ativação durante a personalização.

## Aurora Desktop 1.8.1 — Sirius Wake Profile, 2026-10-24 (patch estável)

- Sincroniza a instalação local com o perfil de wake word personalizado.
- Permite treinamento local com quatro amostras quando o nome não existe no vocabulário do Vosk.
- Mantém somente características acústicas privadas; o áudio bruto não é armazenado.
- Mantém o serviço, o microfone e as configurações do usuário durante a atualização.

## Aurora Desktop 1.8.0 — Sagittarius, 2026-10-24 (release estável)

- Corrige a atualização de instalações existentes preservando os links internos normais do `.venv`.
- Abre o Launchpad em um painel de manutenção quando a Aurora já está instalada, com serviço, integridade e modelos visíveis.
- Mostra no máximo as três builds da Aurora mais novas que a versão instalada, somente quando elas existem.
- Adiciona fallback de reconhecimento para nomes personalizados no Vosk, mantendo a validação de frase exata.
- Adiciona transições de página com fade e deslocamento suave no onboarding.
- Adiciona tema claro/escuro automático baseado na paleta do sistema.
- Dá movimento contínuo à orb de prévia, com deslocamento de luz, respiração e inclinação sutil.
- Refina os SFX de seleção, avanço e conclusão com áudio estéreo sintetizado pela Aurora.
- Faz o texto da prévia de voz acompanhar em tempo real o nome personalizado escolhido.
- Interrompe uma prévia anterior antes de iniciar outra, evitando fila de áudio acumulada.
- Mantém o fluxo limitado às três vozes brasileiras suportadas e valida o nome de ativação no vocabulário do Vosk.
- Corrige o auto-update do Launchpad para aceitar o redirecionamento oficial de assets do GitHub, mantendo a verificação SHA-256.
- Adiciona treinamento local opcional de wake word para nomes ausentes no vocabulário do Vosk, com quatro amostras acústicas e armazenamento sem áudio bruto.

## Aurora Desktop 1.7.2 — Andromeda First Light, 2026-10-24 (release estável)

- Reformula a personalização inicial com cartões Material claros, transições suaves e campos de perfil mais legíveis.
- Mostra três prévias animadas da bolha (Névoa Boreal, Pulso Esmeralda e Flare Carmesim), com seleção explícita.
- Limita a tela de voz às três vozes brasileiras suportadas pelo produto: Thalita, Francisca e Antonio; cada cartão oferece prévia e seleção por rádio.
- Atualiza o Launchpad para 0.3.2, com autoatualização obrigatória do próprio RPM por asset verificado do GitHub, e mantém o instalador separado do payload da Aurora.

## Aurora Desktop 1.7.1-beta.4 — V404 Cygni First-Run Personalization, 2026-10-24 (pré-release beta)

- Adiciona o assistente de primeira configuração após uma instalação nova: nome de saudação, nome de ativação validado pelo vocabulário instalado do Vosk, acabamento da bolha e voz Edge TTS.
- Guarda as escolhas nas configurações locais privadas e adiciona validações para configurações, roteamento, idioma, wake word e integração com o Launchpad.
- Atualiza o Launchpad para concluir o fluxo de personalização na primeira inicialização após a instalação.

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

- Separa OBS, captura pelo portal e registro de ações em módulos dedicados sob `aurora_core/system/`, mantendo a fachada de compatibilidade.
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
- Integrações locais para captura de tela, controle de aplicativos/janelas compatíveis e gravação pelo OBS WebSocket.
- Instalador nativo por scripts, serviço `systemd --user`, diagnóstico somente leitura e testes automatizados.

### Limites conhecidos desta release

- Destinada ao desktop Linux; Wayland, XWayland, portais e suporte AT-SPI variam conforme o ambiente.
- A busca depende de provedores e páginas públicas acessíveis; bloqueios, captchas e páginas sem datas podem impedir confirmação.
- Wake word é local, mas a transcrição Google e a voz Edge TTS dependem da internet.
- Ollama e os modelos Gemma são instalados à parte. Não há atualização automática, pacote Flatpak/RPM nem workflow de CI.
- OBS e captura de tela dependem de configuração e permissões locais. A integração OBS tem testes automatizados, mas não foi possível validar uma gravação real nesta sessão de publicação porque o OBS/WebSocket não estava ativo.
