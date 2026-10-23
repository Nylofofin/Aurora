# Aurora Android Companion — 1.2.3 · NOVA-COMPANION-MATERIAL-R1

Cliente Android nativo Companion. Modelos, busca e automação ficam no computador; o telefone é a interface, microfone e saída de áudio.

## Novidades da Release 1.2.3

- **Interface reconstruída sobre a experiência conversacional Aurora**: tela inicial limpa em lavanda e azul, bolha animada, conversa central, composer compacto com acesso ao Live, histórico em gaveta e abas enxutas para Conversa, Desktop e Ajustes.
- **Conexão acessível**: botão visível de conexão, descoberta do PC na rede, formulário de pareamento com código e pin SHA-256; anteriormente os controles de conexão estavam escondidos e não permitiam completar o pareamento de uma instalação nova.
- **Perfil Local**: nome, idade opcional, avatar e tema ficam no armazenamento privado do Android; preferências selecionadas são enviadas pela LAN/TLS para personalização local no PC. Não há autenticação Google/GitHub nem conta na nuvem.
- **Personalização visual**: Aurora pastel é o tema inicial; Noturno, Névoa e Neon ficam em opções separadas e legíveis.
- **Modo Live contínuo**: o `AudioRecord` é recriado se o Android invalidar o dispositivo durante a sessão; o waveform no composer abre a tela imersiva de voz; o botão X encerra o Live.
- **Desktop remoto experimental por toque**: a aba Desktop pede consentimento do portal GNOME e mostra a tela do PC; toque, toque duplo, toque longo e arrasto enviam eventos de ponteiro.
- **Comandos de voz do Desktop**:
  - Diga *"Aurora, mostre meu computador"* ou acesse a aba Desktop para espelhar a tela do PC em tempo real.
  - Controle completo por toque: toque simples clica, toque duplo abre itens, toque longo abre o menu de contexto (botão direito) e arrasto move o cursor.
  - Para voltar, basta dizer *"Sair do desktop"* ou clicar em Sair.
- O GNOME apresenta o diálogo do portal RemoteDesktop/ScreenCast para o usuário aprovar tela e ponteiro. A Aurora não habilita RDP/VNC globalmente nem ignora o consentimento do sistema.
- **APK**: [Aurora Android 1.2.3](https://github.com/ruanminezinoficial2025-ctrl/Aurora/releases/tag/android-v1.2.3). Build assinada para debug.

## Reconstrução Android 1.2.3

- A interface está sendo reconstruída em Material 3: navegação inferior com Conversa, PC e Ajustes; composer integrado; histórico em diálogo; telas com largura máxima e controles dimensionados pela área disponível. O desenho da orb e os sons de entrada/saída vêm dos assets do cliente desktop e são incluídos no APK.
- O Live agora inicia `MicCaptureService` como foreground service enquanto o usuário está na sessão. A notificação deixa a captura visível; tocar no X encerra o loop e o serviço. Uma falha de leitura de `AudioRecord` descarta a instância danificada e tenta recriá-la, em vez de manter um loop silencioso.
- A captura de microfone depende da permissão e das regras do Android. O serviço precisa ser iniciado enquanto o app está visível; modos de economia de bateria do fabricante, o seletor de privacidade do microfone ou a revogação da permissão ainda podem interrompê-la. O app não contorna essas proteções.
- Esta versão substitui a interface 1.2.2. Não houve validação visual ou de microfone em aparelho físico antes da publicação; trate o Live como experimental até testar no seu celular.

- Pareamento HTTPS com fingerprint SHA-256 digitado fora de banda, código de uso único e token cifrado no Android Keystore.
- Envio de mensagens pelo roteador central do desktop e histórico de conversas armazenado no PC.
- No Live, o microfone fica ativo entre turnos e uma notificação deixa seu uso visível. A transcrição acontece em pt-BR no PC e a resposta sintetizada volta como áudio.
- Respostas de voz geradas pelo PC via Edge TTS na voz configurada (Thalita por padrão) e enviadas em um POST HTTPS binário separado (`audio/mpeg`), sem Base64 no JSON do chat. O cliente não usa o TTS Google/Android. A síntese precisa de internet no PC e pode levar alguns segundos; se falhar, a mensagem permanece e a interface mostra a etapa/erro.
- Durante o controle pelo celular, a fala parcial e os sons da bolha não tocam nos alto-falantes do PC. Os sons de entrada/saída são assets WAV embutidos no APK, sem streaming pela rede. A voz Edge TTS é gerada no PC e enviada em MP3; o cliente usa extensão reconhecível pelo Android e avisa se não conseguir reproduzir. O som de saída é carregado do APK antes de liberar o controle ao desktop. Cliques usam o feedback de interface configurado no Android.
- O waveform do composer abre o Live em tela cheia e toca o som de entrada; a escuta contínua permanece até tocar no X, que encerra a sessão e toca o som de saída.
- Wake word mobile é experimental. Com conexão ao PC e permissão de microfone, o serviço em primeiro plano envia PCM por HTTPS ao Vosk local do computador. O indicador de microfone permanece na notificação.
- Desktop Remoto pelo botão **Desktop**. O portal GNOME solicita consentimento para tela e ponteiro; quadros JPEG são enviados por HTTPS e os toques mapeados viram eventos de ponteiro no mesmo stream aprovado. O fluxo não salva imagens e encerra ao sair, desconectar ou após 30 segundos sem visualizador.
- Gaveta lateral com histórico completo de conversas do PC, seleção de chat e ação de nova conversa.
- Descoberta automática do PC por DNS-SD/mDNS quando ambos estão na mesma LAN; a impressão digital TLS continua sendo verificada fora de banda.
- Controle exclusivo: ao conectar, o stream do microfone e o wake word local do PC são encerrados; **Desconectar** devolve a escuta à Aurora desktop. Se o app ou a rede cair, o lease expira e o PC retoma em até 60 segundos.
- Comandos explícitos de baixo risco: abrir app/site, controlar volume, consultar hardware e capturar tela. Ações que pedem confirmação presencial (como fechar app ou iniciar gravação OBS) são recusadas pelo mobile nesta demo.
- O wake word mobile é experimental e não equivale ao “Hey Google”: depende do PC pareado, da conexão local e de uma ação do usuário para retomar a conversa se o app estiver em segundo plano. Não detecta a palavra quando o celular está desconectado.
- Nesta build, wake contínuo, captura/stream e validação de eventos passaram por testes de código e compilação. Ainda precisam de validação no celular e aceite real do portal GNOME RemoteDesktop/ScreenCast; trate-os como experimentais.
- O serviço desktop precisa estar atualizado e ativo; versões anteriores à API companion ainda não aceitam pareamento.

## Arquitetura da Demo

1. O desktop Aurora é o servidor e conserva inferência, pesquisa, voz e automação.
2. O app pareia explicitamente com o PC e troca mensagens por um canal autenticado e criptografado. Ollama continua preso a loopback; nunca será exposto ao Wi-Fi.
3. Conversas e histórico são armazenados no PC e sincronizados ao cliente.
4. A demo de voz envia trechos PCM mono a 16 kHz (até 45 segundos cada) por HTTPS ao PC. O PC transcreve pela integração Google Speech e gera a resposta falada via Edge TTS; o app recebe e reproduz o MP3 sem usar TTS Google/Android. Após a permissão, tocar no waveform inicia uma sessão Live explícita e um foreground service com notificação visível. A captura contínua entre turnos segue sujeita às políticas de microfone, bateria e privacidade do Android; fechar à força o app encerra a sessão. O áudio capturado fica apenas em memória no PC; o serviço de reconhecimento Google recebe cada trecho de fala, como no cliente desktop.
5. A conexão atual usa a mesma rede local. Acesso remoto futuro deverá usar VPN privada; não encaminhe a porta do PC à internet.
6. Tela e ponteiro remoto usam os portais GNOME RemoteDesktop/ScreenCast, PipeWire e GStreamer. O usuário aprova o compartilhamento e controle no diálogo do desktop; a Aurora não ativa RDP/VNC globalmente nem contorna o portal. O fluxo é limitado à sessão aprovada e termina ao desconectar.

## Começar uma conversa

1. No PC, deixe a Aurora e o servidor Companion ativos. Conecte celular e PC à mesma rede Wi-Fi.
2. No app, toque em **Conectar** e pareie. A tela inicial oferece conversa por texto e acesso ao Live.
3. Para conversar por voz, toque no waveform no composer e permita o microfone. O Android mostra uma notificação durante a sessão; fale naturalmente e toque no **X** para sair. A resposta falada usa áudio Edge TTS gerado no PC.
4. Para texto, digite no composer e toque em **↑**. O botão **+** inicia uma conversa nova.
5. Abra o histórico pelo botão de menu no topo. A navegação inferior reúne Conversa, PC e Ajustes.
6. Em **Ajustes**, escolha o tema, edite o perfil local ou ative a palavra de ativação. Para ver e controlar o computador, abra **PC** e aprove o compartilhamento no desktop. Em Linux, o host precisa ter o portal ScreenCast, PipeWire, GStreamer e as bindings `python3-gobject`/`python3-dbus`; quando o venv isolado não enxerga essas bindings, o Companion inicia um worker curto com o Python do sistema só para captura e envio de quadros.

## Compilar

Requer JDK 17 ou superior e Android SDK Platform 37 / Build Tools 36.0.0. Defina `ANDROID_HOME` ou crie `local.properties` (não versionado) com `sdk.dir=/caminho/para/Android/Sdk`; então execute:

```sh
./gradlew assembleDebug
```

O APK de desenvolvimento, quando compilado, fica em `app/build/outputs/apk/debug/app-debug.apk`. A cópia publicada na release é um artefato debug e pode exigir a autorização do Android para instalar apps baixados fora da Play Store.

## Parear e testar

1. Atualize o repositório Aurora no PC, instale as dependências existentes e reinicie o serviço de usuário. O servidor companion sobe automaticamente na interface IPv4 privada, na porta `8765` por padrão; `companion_enabled` e `companion_port` podem ser definidos em `~/.config/aurora/aurora-settings.json`. Quando Avahi está instalado, o PC também anuncia `Aurora Companion` na rede por DNS-SD.
2. Mantenha PC e celular na mesma rede local. Instale o APK da release, abra **Conectar** e toque em **Encontrar meu PC automaticamente**.
3. A descoberta preenche o endereço local. Informe a impressão SHA-256 de `~/.config/aurora/companion/server-fingerprint.txt` e o código de `~/.config/aurora/companion/pairing-code.txt`; compare o pin diretamente com o arquivo no PC. O serviço também registra endereço e impressão no log.
4. O código é de uso único e gira depois do pareamento. A autenticação usa bearer token aleatório; o desktop guarda somente seu hash, e o app cifra o token com uma chave não exportável do Android Keystore. O histórico fica em `~/.config/aurora/companion/conversations.json`, com permissões privadas.
5. Ao parear, o app adquire controle exclusivo e fecha o stream do microfone do PC. Digite uma mensagem ou use o modo Live pelo botão waveform. Em Live, toque em **Falar** e depois **Parar e enviar**; o desktop usa o roteamento, os modelos e a busca existentes, transcreve gravações pelo Google Speech e envia a resposta sintetizada com Edge TTS ao telefone. Estados básicos chegam pelos heartbeats. Toque em **Desconectar** para devolver o controle; se o celular perder a rede ou o processo encerrar, o lease expira em até 60 segundos e a escuta local retorna.

O servidor aceita apenas HTTPS/TLS 1.2+, limita tentativas de pareamento e escuta no IP privado detectado, nunca em todas as interfaces. O pin deve ser comparado com o arquivo lido diretamente no PC antes de parear. Não encaminhe a porta `8765` ao roteador. O token é guardado no PC e continua válido após reiniciar o serviço; remova `device-tokens.json` no diretório companion para revogar todos os celulares pareados.

Texto e transcrição são processados pelo serviço desktop e podem acionar os provedores externos documentados no README raiz. O áudio do wake é enviado em blocos PCM pela LAN/TLS e reconhecido localmente pelo Vosk no PC; após o comando, o áudio é enviado ao Google Speech como no desktop. A tela é capturada após autorização do portal, transmitida por HTTPS em quadros de baixa taxa e não é gravada pelo Companion. Se a conexão cair durante o Live, o app interrompe captura/reprodução e fecha a sessão; o lease do PC expira em até 60 segundos. DNS-SD depende do Avahi no PC e de mDNS permitido pela rede; redes de convidados ou isolamento entre clientes podem impedir a descoberta automática.
