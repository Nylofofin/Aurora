# Aurora Desktop

**Versão:** `2.1.2` · **Build:** `aurora-desktop-2.1.2-rigel-update-integrity`

**Uma assistente de voz para Linux, com uma presença pequena na tela e o processamento principal no próprio computador.** A Aurora desperta por voz, entende pedidos cotidianos, conversa em uma sessão contínua e pode pesquisar na web ou executar ações locais.

<p align="center">
  <img src="docs/media/bubble-enter.gif" width="360" alt="A bolha real da Aurora entrando com a animação de escuta">
  <img src="docs/media/bubble-exit.gif" width="360" alt="A Aurora falando e recolhendo a bolha ao concluir">
</p>

## Veja a Aurora

A esfera mantém o formato circular e muda de cor, luz e detalhes conforme o estilo escolhido.

![Seis estilos de bolha da Aurora](docs/media/bubble-skins.png)

O onboarding deixa a pessoa configurar nome, palavra de ativação, aparência, voz e assinatura sonora. O treinamento de um nome personalizado aparece quando necessário.

As animações abaixo foram capturadas dos próprios componentes do onboarding: a troca de páginas desliza, e as escolhas percorrem os carrosséis com o mesmo movimento usado na configuração.

![Fluxo animado do onboarding: perfil, aparência, voz e sons, com as transições entre etapas](docs/media/onboarding-transitions.gif)

<p align="center">
  <img src="docs/media/onboarding-skins.gif" width="32%" alt="Carrossel animado de estilos da bolha">
  <img src="docs/media/onboarding-voices.gif" width="32%" alt="Carrossel animado de vozes locais">
  <img src="docs/media/onboarding-sounds.gif" width="32%" alt="Carrossel animado de assinaturas sonoras">
</p>

## O que ela faz

- Ativação e transcrição de fala locais com Vosk e Whisper.cpp.
- Conversa e síntese de voz locais com Ollama, Piper ou Supertonic; apenas a voz selecionada é preparada.
- Pesquisa web quando pedida, com fontes reunidas em um resumo.
- Ações no desktop e rotinas locais, com confirmação antes de operações que alteram o sistema.
- Perfil, nome de ativação, aparência, voz, sons e dados de uso mantidos no computador.

A pesquisa web precisa de internet. Modelos e pesos de voz são baixados quando necessários e têm licenças próprias. Consulte os detalhes de [vozes e modelos](assets/voices/README.md) e das [fontes dos sons](assets/audio/SOURCES.md).

## Instalação

A versão gráfica é voltada ao **Fedora Workstation com GNOME em Wayland**. Baixe o RPM mais recente do Aurora Launchpad na página de [Releases](https://github.com/Nylofofin/Aurora/releases/latest), abra-o pelo GNOME Software e siga as etapas apresentadas. O Launchpad verifica o ambiente, explica os componentes e permite atualizar uma instalação existente preservando as preferências do usuário.

Instruções de empacotamento e instalação manual estão em [`packaging/rpm/README.md`](packaging/rpm/README.md). Outros ambientes Linux ainda não são oficialmente suportados.

## Privacidade e segurança

Áudio, transcrição, inferência e perfil são processados localmente. Quando você pede uma pesquisa, o texto da consulta é enviado a serviços web para obter resultados; o áudio não é enviado. Modelos e vozes escolhidos são baixados quando necessário. Ações que alteram o sistema pedem confirmação. Pesos de modelos não são incluídos no repositório ou no RPM.

## Projeto e licença

Aurora é um projeto independente, conduzido por **Nylofofin**. O código e a documentação foram gerados por IA. O mantenedor conduz as decisões, a integração e os testes.

O código próprio é licenciado sob **GNU GPL-3.0-only**. Modelos, dependências e outros materiais mantêm as licenças de seus autores. Leia [`LICENSE`](LICENSE) antes de redistribuir.

[Releases](https://github.com/Nylofofin/Aurora/releases) · [Código-fonte](https://github.com/Nylofofin/Aurora) · [Licença](LICENSE)
