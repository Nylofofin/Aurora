# Vozes locais

O catálogo ativo oferece uma voz local: Faber, da família Piper VITS. A instalação pessoal guarda o modelo em `~/.local/share/aurora/voices/pt_BR-faber-medium/`. O peso não é distribuído no repositório nem no RPM; é baixado quando o usuário seleciona/prepara a voz.

O sintetizador Piper e o player `ffplay` são usados localmente. O áudio é gerado em trechos e reproduzido sem enviar o texto para um serviço remoto. O tempo depende do processador e do tamanho da resposta; a primeira utilização precisa baixar o modelo Faber.

**Licença:** o modelo Faber é publicado no repositório [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices), com licença e metadados próprios junto ao modelo. Consulte esses termos upstream antes de redistribuir os pesos. A Aurora não inclui os pesos. A qualidade e a latência variam conforme a máquina.

Faber é o nome exibido e o identificador técnico corresponde ao modelo Piper `pt_BR-faber-medium`.
