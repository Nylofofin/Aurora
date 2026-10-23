# Aurora Android Companion — Alpha

Cliente Android nativo Alpha. A visão é manter modelos, busca e ações no computador; o telefone será interface, microfone e saída de áudio.

## Estado atual

- APK debug para instalar no celular: [`artifacts/aurora-companion-alpha2-debug.apk`](../artifacts/aurora-companion-alpha2-debug.apk). É uma build de desenvolvimento assinada para debug.

- Base Android com Jetpack Compose, tema escuro e esfera Aurora animada em branco, violeta e azul.
- Pareamento HTTPS com fingerprint SHA-256 digitado fora de banda, código de uso único e token cifrado no Android Keystore.
- Envio de mensagens pelo roteador central do desktop e histórico de conversas armazenado no PC.
- Live por microfone, streaming da tela e automação móvel ainda são controles de prévia e não estão funcionais.
- O serviço desktop precisa estar atualizado e ativo; versões anteriores à API companion ainda não aceitam pareamento.

## Arquitetura da Alpha

1. O desktop Aurora será o servidor e conservará inferência, pesquisa, voz e automação.
2. O app se pareará explicitamente com o PC e trocará mensagens por um canal autenticado e criptografado. Ollama continua preso a loopback; nunca será exposto ao Wi-Fi.
3. Conversas e histórico serão armazenados no PC e sincronizados ao cliente.
4. O modo Live enviará áudio do telefone ao PC e receberá fala e estados da tarefa. A captura começa por ação visível do usuário e terá notificação persistente enquanto o microfone estiver ativo.
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
5. Digite uma mensagem. O desktop usa o roteamento, os modelos e a busca que já possui. Enquanto esse pedido estiver ativo, a bolha do PC acompanha o estado; o áudio não é reproduzido no PC.

O servidor aceita apenas HTTPS/TLS 1.2+, limita tentativas de pareamento e escuta no IP privado detectado, nunca em todas as interfaces. O pin deve ser comparado com o arquivo lido diretamente no PC antes de parear. Não encaminhe a porta `8765` ao roteador. O token é guardado no PC e continua válido após reiniciar o serviço; remova `device-tokens.json` no diretório companion para revogar todos os celulares pareados.

O texto é processado pelo mesmo serviço desktop e pode acionar os provedores externos já documentados neste README. Esta build ainda não transmite o microfone do celular, não envia áudio para o TTS do PC, não exibe a tela do PC e bloqueia pedidos de automação feitos pelo celular.
