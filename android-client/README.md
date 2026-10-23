# Aurora Android Companion — Alpha

Cliente Android nativo Alpha. A visão é manter modelos, busca e ações no computador; o telefone será interface, microfone e saída de áudio.

## Estado atual

- APK debug experimental para instalar no celular: [`artifacts/aurora-companion-0.3.0-demo-debug.apk`](../artifacts/aurora-companion-0.3.0-demo-debug.apk). É uma build de desenvolvimento assinada para debug.

- Base Android com Jetpack Compose, tema escuro e esfera Aurora animada em branco, violeta e azul.
- Pareamento HTTPS com fingerprint SHA-256 digitado fora de banda, código de uso único e token cifrado no Android Keystore.
- Envio de mensagens pelo roteador central do desktop e histórico de conversas armazenado no PC.
- Voz experimental por turnos: toque em **Voz**, fale e toque em **Parar**; o PC transcreve em pt-BR e executa a conversa central, e o Android lê a resposta em voz alta.
- Voz contínua em segundo plano, streaming da tela e automação móvel ainda não estão implementados.
- O serviço desktop precisa estar atualizado e ativo; versões anteriores à API companion ainda não aceitam pareamento.

## Arquitetura da Alpha

1. O desktop Aurora será o servidor e conservará inferência, pesquisa, voz e automação.
2. O app se pareará explicitamente com o PC e trocará mensagens por um canal autenticado e criptografado. Ollama continua preso a loopback; nunca será exposto ao Wi-Fi.
3. Conversas e histórico serão armazenados no PC e sincronizados ao cliente.
4. A demo de voz envia gravação PCM mono a 16 kHz (máximo 45 segundos) por HTTPS ao PC. O PC transcreve pela mesma integração Google Speech usada pelo desktop; o Android pronuncia a resposta com o mecanismo TTS instalado. O microfone só é acessado após permissão e toque explícito, enquanto o app está aberto.
5. A conexão inicial será na mesma rede local. Acesso remoto virá por VPN privada; não haverá encaminhamento direto da porta do PC à internet.
6. A visualização da tela do PC será uma etapa própria, com início explícito e indicador visível. Automação do próprio Android fica fora desta Alpha.

## Compilar

Requer JDK 17 ou superior e Android SDK Platform 37 / Build Tools 36.0.0. Defina `ANDROID_HOME` ou crie `local.properties` (não versionado) com `sdk.dir=/caminho/para/Android/Sdk`; então execute:

```sh
./gradlew assembleDebug
```

O APK de desenvolvimento, quando compilado, fica em `app/build/outputs/apk/debug/app-debug.apk`. A cópia publicada na release é um artefato debug e pode exigir a autorização do Android para instalar apps baixados fora da Play Store.

## Parear e testar

1. Atualize o repositório Aurora no PC, instale as dependências existentes e reinicie o serviço de usuário. O servidor companion sobe automaticamente na interface IPv4 privada, na porta `8765` por padrão; `companion_enabled` e `companion_port` podem ser definidos em `~/.config/aurora/aurora-settings.json`.
2. Mantenha PC e celular na mesma rede local. Instale o APK da release e abra **Conectar**.
3. No celular, preencha `https://IP-PRIVADO-DO-PC:8765`, o código em `~/.config/aurora/companion/pairing-code.txt` e a impressão SHA-256 em `~/.config/aurora/companion/server-fingerprint.txt`. O log do serviço também informa a URL e a impressão.
4. O código é de uso único e gira depois do pareamento. A autenticação usa bearer token aleatório; o desktop guarda somente seu hash, e o app cifra o token com uma chave não exportável do Android Keystore. O histórico fica em `~/.config/aurora/companion/conversations.json`, com permissões privadas.
5. Digite uma mensagem ou toque em **Voz** e depois **Parar**. O desktop usa o roteamento, os modelos e a busca que já possui. Enquanto esse pedido estiver ativo, a bolha do PC acompanha o estado; o áudio de resposta toca no celular.

O servidor aceita apenas HTTPS/TLS 1.2+, limita tentativas de pareamento e escuta no IP privado detectado, nunca em todas as interfaces. O pin deve ser comparado com o arquivo lido diretamente no PC antes de parear. Não encaminhe a porta `8765` ao roteador. O token é guardado no PC e continua válido após reiniciar o serviço; remova `device-tokens.json` no diretório companion para revogar todos os celulares pareados.

Texto e transcrição são processados pelo mesmo serviço desktop e podem acionar os provedores externos já documentados neste README. A transcrição envia áudio ao Google Speech pelo fluxo já usado pela Aurora PC. Esta demo não mantém escuta contínua, não fala com a voz Edge do PC, não exibe a tela do PC e bloqueia pedidos de automação feitos pelo celular.
