# Histórico de versões

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
