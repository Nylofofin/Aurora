# Aurora Android Companion — Beta Demo 0.7.0

Cliente Android nativo Demo Experimental. Modelos, busca e automação ficam no computador; o telefone é a interface, microfone e saída de áudio.

## Estado atual

- APK Beta Demo: [release Android 0.7.0](https://github.com/ruanminezinoficial2025-ctrl/Aurora/releases/tag/android-beta-v0.7.0). É uma build de desenvolvimento assinada para debug.

- Interface renovada em tons claros pastel de lavanda e azul, cartões mais leves, contraste legível, esfera Aurora animada e ícone adaptativo vetorial próprio.
- Pareamento HTTPS com fingerprint SHA-256 digitado fora de banda, código de uso único e token cifrado no Android Keystore.
- Envio de mensagens pelo roteador central do desktop e histórico de conversas armazenado no PC.
- Tela inicial com ações explícitas **Falar com a Aurora** e **Escrever uma mensagem**; os controles de enviar, voz, histórico e conexão são botões com área de toque ampliada.
- Voz por turnos com foreground service do Android: toque em **Falar com a Aurora** ou **Voz**, fale e toque em **Parar e enviar**; a notificação deixa o uso do microfone visível e a captura pode continuar com a tela bloqueada. O PC transcreve em pt-BR, executa a conversa central e devolve o áudio sintetizado.
- Respostas de voz geradas pelo PC via Edge TTS na voz configurada (Thalita por padrão) e enviadas como MP3; o cliente não usa o TTS Google/Android. A síntese precisa de internet no PC e pode levar alguns segundos; sem áudio, a resposta em texto continua disponível.
- Durante o controle pelo celular, a fala parcial e os sons da bolha não tocam nos alto-falantes do PC; a voz Edge TTS e os sons de entrada/saída são recebidos e reproduzidos no telefone. Falhas de reprodução agora aparecem como aviso. O som de saída é baixado antes de liberar o controle ao desktop. Cliques usam o feedback de interface configurado no Android.
- Modo Live em tela cheia: o botão waveform abre uma bolha central animada e toca o som de entrada do PC; cada fala começa por toque, e o X encerra e toca o som de saída. A sessão permanece aberta para novos turnos até sair.
- Wake word experimental pelo botão **Mic**. Com a sessão conectada, um serviço de microfone em primeiro plano envia PCM por HTTPS ao PC; o modelo Vosk local reconhece “Aurora”. Se o app estiver visível, o Live inicia sem outro toque. O indicador de microfone permanece na notificação; com o app em segundo plano, é necessário abrir a notificação e tocar em **Falar** para continuar.
- Visualização ao vivo da tela do PC pelo botão **PC**. O portal do desktop solicita consentimento no computador; quadros JPEG são enviados por HTTPS ao telefone. O fluxo é somente leitura, não salva imagens e encerra ao sair, desconectar ou após 30 segundos sem visualizador.
- Gaveta lateral com histórico completo de conversas do PC, seleção de chat e ação de nova conversa.
- Descoberta automática do PC por DNS-SD/mDNS quando ambos estão na mesma LAN; a impressão digital TLS continua sendo verificada fora de banda.
- Controle exclusivo: ao conectar, o stream do microfone e o wake word local do PC são encerrados; **Desconectar** devolve a escuta à Aurora desktop. Se o app ou a rede cair, o lease expira e o PC retoma em até 60 segundos.
- Comandos explícitos de baixo risco: abrir app/site, controlar volume, consultar hardware e capturar tela. Ações que pedem confirmação presencial (como fechar app ou iniciar gravação OBS) são recusadas pelo mobile nesta demo.
- O wake word mobile é experimental e não equivale ao “Hey Google”: depende do PC pareado, da conexão local e de uma ação do usuário para retomar a conversa se o app estiver em segundo plano. Não detecta a palavra quando o celular está desconectado.
- Nesta build, wake word e transmissão de tela passaram por testes de código e compilação, mas ainda precisam de validação em um celular e de um aceite real do portal ScreenCast; trate os dois como experimentais.
- O serviço desktop precisa estar atualizado e ativo; versões anteriores à API companion ainda não aceitam pareamento.

## Arquitetura da Demo

1. O desktop Aurora é o servidor e conserva inferência, pesquisa, voz e automação.
2. O app pareia explicitamente com o PC e troca mensagens por um canal autenticado e criptografado. Ollama continua preso a loopback; nunca será exposto ao Wi-Fi.
3. Conversas e histórico são armazenados no PC e sincronizados ao cliente.
4. A demo de voz envia gravação PCM mono a 16 kHz (máximo 45 segundos) por HTTPS ao PC. O PC transcreve pela integração Google Speech e gera a resposta falada via Edge TTS; o app recebe e reproduz o MP3 sem usar TTS Google/Android. O microfone só é acessado após permissão e toque explícito. Um foreground service exibe uma notificação e mantém a gravação solicitada ativa enquanto a tela está bloqueada; o limite é 45 segundos e fechar à força o app encerra a captura. O áudio capturado fica apenas em memória no PC; o serviço de reconhecimento Google recebe o trecho de fala, como no cliente desktop.
5. A conexão atual usa a mesma rede local. Acesso remoto futuro deverá usar VPN privada; não encaminhe a porta do PC à internet.
6. A tela ao vivo usa o portal ScreenCast, PipeWire e GStreamer. O consentimento do desktop é obrigatório; o fluxo é somente leitura. Automação do próprio Android fica fora desta Beta Demo.

## Começar uma conversa

1. No PC, deixe a Aurora e o servidor Companion ativos. Conecte celular e PC à mesma rede Wi-Fi.
2. No app, toque em **Conectar ao PC** e pareie. Com conexão ativa, a tela inicial mostra **Falar com a Aurora** e **Escrever uma mensagem**.
3. Para conversa Live, toque no botão **waveform** no campo inferior. A bolha cresce para o centro e toca o som de entrada; toque em **Falar** ou na bolha, permita o microfone, fale e toque em **Parar e enviar**. A resposta falada usa o áudio Edge TTS gerado no PC. Toque no **X** para sair.
4. Para texto, toque em **Escrever uma mensagem**, digite no campo inferior e toque no botão de envio **↑**.
5. Abra **Conversas** na barra superior para navegar pelo histórico ou criar um chat novo.
6. Para ativação por voz, toque em **Mic** no campo de mensagem e mantenha a sessão conectada. Para ver o computador, toque em **PC** e aceite o compartilhamento na janela do desktop. Em Linux, o host precisa ter o portal ScreenCast, PipeWire, GStreamer e as bindings `python3-gobject`/`python3-dbus`; quando o venv isolado não enxerga essas bindings, o Companion inicia um worker curto com o Python do sistema só para captura e envio de quadros.

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
