# Aurora Android Companion — Demo Experimental 0.4.3

Cliente Android nativo Demo Experimental. Modelos, busca e automação ficam no computador; o telefone é a interface, microfone e saída de áudio.

## Estado atual

- APK experimental: [release Android 0.4.3](https://github.com/ruanminezinoficial2025-ctrl/Aurora/releases/tag/android-demo-v0.4.3). É uma build de desenvolvimento assinada para debug.

- Base Android com Jetpack Compose, tema escuro, esfera Aurora animada e ícone adaptativo vetorial próprio em branco, violeta e azul.
- Pareamento HTTPS com fingerprint SHA-256 digitado fora de banda, código de uso único e token cifrado no Android Keystore.
- Envio de mensagens pelo roteador central do desktop e histórico de conversas armazenado no PC.
- Voz por turnos com foreground service do Android: toque em **Voz**, fale e toque em **Parar**; a notificação deixa o uso do microfone visível e a captura pode continuar com a tela bloqueada. O PC transcreve em pt-BR e executa a conversa central; o Android lê a resposta em voz alta.
- Descoberta automática do PC por DNS-SD/mDNS quando ambos estão na mesma LAN; a impressão digital TLS continua sendo verificada fora de banda.
- Controle exclusivo: ao conectar, o stream do microfone e o wake word local do PC são encerrados; **Desconectar** devolve a escuta à Aurora desktop. Se o app ou a rede cair, o lease expira e o PC retoma em até 60 segundos.
- Comandos explícitos de baixo risco: abrir app/site, controlar volume, consultar hardware e capturar tela. Ações que pedem confirmação presencial (como fechar app ou iniciar gravação OBS) são recusadas pelo mobile nesta demo.
- Voz contínua em segundo plano, streaming da tela, aprovação de ações pelo celular e automação móvel ainda não estão implementados.
- O serviço desktop precisa estar atualizado e ativo; versões anteriores à API companion ainda não aceitam pareamento.

## Arquitetura da Demo

1. O desktop Aurora é o servidor e conserva inferência, pesquisa, voz e automação.
2. O app pareia explicitamente com o PC e troca mensagens por um canal autenticado e criptografado. Ollama continua preso a loopback; nunca será exposto ao Wi-Fi.
3. Conversas e histórico são armazenados no PC e sincronizados ao cliente.
4. A demo de voz envia gravação PCM mono a 16 kHz (máximo 45 segundos) por HTTPS ao PC. O PC transcreve pela mesma integração Google Speech usada pelo desktop; o Android pronuncia a resposta com o mecanismo TTS instalado. O microfone só é acessado após permissão e toque explícito. Um foreground service exibe uma notificação e mantém a gravação solicitada ativa enquanto a tela está bloqueada; o limite é 45 segundos e fechar à força o app encerra a captura. O áudio fica apenas em memória no PC; o serviço de reconhecimento Google recebe o trecho de fala, como no cliente desktop.
5. A conexão atual usa a mesma rede local. Acesso remoto futuro deverá usar VPN privada; não encaminhe a porta do PC à internet.
6. A visualização da tela do PC será uma etapa própria, com início explícito e indicador visível. Automação do próprio Android fica fora desta Alpha.

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
5. Ao parear, o app adquire controle exclusivo e fecha o stream do microfone do PC. Digite uma mensagem, peça um comando compatível ou toque em **Voz** e depois **Parar**. O desktop usa o roteamento, os modelos e a busca existentes; as gravações são transcritas pelo Google Speech e o Android fala a resposta. Estados básicos chegam pelos heartbeats. Toque em **Desconectar** para devolver o controle; se o celular perder a rede ou o processo encerrar, o lease expira em até 60 segundos e a escuta local retorna.

O servidor aceita apenas HTTPS/TLS 1.2+, limita tentativas de pareamento e escuta no IP privado detectado, nunca em todas as interfaces. O pin deve ser comparado com o arquivo lido diretamente no PC antes de parear. Não encaminhe a porta `8765` ao roteador. O token é guardado no PC e continua válido após reiniciar o serviço; remova `device-tokens.json` no diretório companion para revogar todos os celulares pareados.

Texto e transcrição são processados pelo serviço desktop e podem acionar os provedores externos documentados no README raiz. O áudio enviado ao Google Speech usa o fluxo já usado pela Aurora PC. Esta demo não mantém escuta contínua, não usa a voz Edge do PC, não exibe a tela e não permite aprovar pelo celular ações que exigem confirmação presencial. DNS-SD depende do Avahi no PC e de mDNS permitido pela rede; redes de convidados ou isolamento entre clientes podem impedir a descoberta automática.
