# Aurora Android Companion — Alpha

Cliente Android nativo em desenvolvimento. A visão é manter modelos, busca e ações no computador; o telefone será interface, microfone e saída de áudio.

## Estado atual

- APK debug para instalar no celular: [`artifacts/aurora-companion-alpha1-debug.apk`](../artifacts/aurora-companion-alpha1-debug.apk). É uma build de desenvolvimento assinada para debug.

- Base Android com Jetpack Compose, tema escuro e esfera Aurora animada em branco, violeta e azul.
- Esboço das telas de conversa, histórico e conexão com o PC.
- **Ainda não conectado ao servidor**: envio de mensagens, sincronização de conversas, Live, pareamento e streaming ainda não estão funcionais. Os controles visuais não devem ser tratados como ações concluídas.
- O APK debug é apenas uma prévia de interface, não a Alpha funcional.

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

O APK de desenvolvimento, quando compilado, fica em `app/build/outputs/apk/debug/app-debug.apk`.
