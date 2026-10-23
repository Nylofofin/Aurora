# Histórico de versões

## Em desenvolvimento

- A verificação do OBS agora aguarda a propagação assíncrona do estado de gravação, evitando falso “não confirmei” após o OBS aceitar `StartRecord`. Testes cobrem estado atrasado e estado que nunca muda.

## 1.0.2 — Polaris-Edge, Patch 2 (pré-release, 2026-10-22)

- Separa OBS, captura pelo portal, Spotify e registro de ações em módulos dedicados sob `aurora_core/system/`, mantendo a fachada de compatibilidade.
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

Primeira release oficial da Aurora para uso pessoal e privado.

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
