# Aurora Android Companion — descontinuado

**Anúncio — 23 de outubro de 2026:** o cliente Android foi descontinuado. Não haverá novas builds, suporte ou releases Android. O desenvolvimento ativo da Aurora volta a se concentrar no cliente desktop Linux. Os commits do período ficam preservados como registro histórico; as tags de release e os APKs Android foram removidos.

## Motivo

O comportamento do microfone em segundo plano variou conforme as restrições do Android, permissões visíveis, controles de privacidade e economia de bateria. O foreground service com notificação melhorou a elegibilidade da captura, mas não remove essas limitações nem foi validado na última build em um aparelho físico. Manter a promessa de uma sessão Live confiável exigiria uma rodada de testes em aparelhos reais e manutenção específica para versões e fabricantes Android. A prioridade volta para a experiência integrada no PC.

## Registro de testes e validações

### Verificações feitas no ambiente de desenvolvimento

| Build / etapa | Resultado registrado |
| --- | --- |
| Android 1.2.3 — compilação Kotlin | `:app:compileDebugKotlin` passou. |
| Android 1.2.3 — testes Android | `:app:testDebugUnitTest` retornou `NO-SOURCE`: não havia testes unitários Android. |
| Android 1.2.3 — APK debug e release | `:app:assembleDebug` e `:app:assembleRelease` passaram. APK release: versionCode 23, versionName 1.2.3, 5.257.118 bytes. |
| Suíte Python do repositório | `PYTHONPATH=. .venv/bin/pytest -q`: 263 passaram. Essa suíte valida o desktop/servidor, não o microfone Android. |
| Aparelho/emulador conectado | Não testado nesta sessão: `adb` não estava instalado/disponível. |

### Testes relatados pelo usuário durante o desenvolvimento

- O pareamento/conexão com o computador foi usado no celular.
- Os sons de entrada e saída foram confirmados funcionando no telefone.
- Em uma versão posterior, o usuário confirmou que a voz sintetizada no PC chegou ao celular; relatou atraso perceptível e pediu sincronização com a animação.
- O modo de automação remota do PC não teve confirmação de funcionamento completo pelo usuário.
- O usuário relatou que a escuta do microfone parava após a primeira fala e que o Android restringia a captura. As tentativas de manter a sessão Live contínua não foram suficientes para tornar esse comportamento confiável.
- A versão 1.2.3 não recebeu validação de interface, captura de microfone, reprodução de voz ou controle remoto em aparelho físico antes de ser publicada como pré-release.

As observações acima são relatos de uso, não uma certificação de compatibilidade com modelos de telefone específicos. Não foram registrados fabricante, versão Android, configuração de bateria ou logs de captura para todos os testes.

## Histórico das releases retiradas

As páginas de release e APKs Android foram removidos. Os tags abaixo permanecem no Git para preservar o código-fonte e o histórico:

- `android-v1.2.3`, `android-v1.2.2`, `android-v1.2.0`, `android-v1.0.0`
- `android-demo-v0.5.1`, `android-demo-v0.5.0`, `android-demo-v0.4.4`, `android-demo-v0.4.3`, `android-demo-v0.4.2`, `android-demo-v0.4.1`, `android-demo-v0.4.0`
- `android-beta-v0.8.3`, `android-beta-v0.8.2`, `android-beta-v0.8.1`, `android-beta-v0.8.0`, `android-beta-v0.7.3`, `android-beta-v0.7.2`, `android-beta-v0.7.1`, `android-beta-v0.7.0`, `android-beta-v0.6.0`

Este registro distingue builds de desenvolvimento, testes feitos pelo usuário e funções que nunca foram confirmadas. Ele não promete suporte futuro ao Android.
