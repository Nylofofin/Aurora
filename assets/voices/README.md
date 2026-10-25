# Modelo de voz local opcional

O modelo `pt_BR-faber-medium` não é incluído nem baixado pelo instalador. Sua página está no projeto [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/pt/pt_BR/faber/medium) e o arquivo tem aproximadamente 61 MiB. O cartão identifica idioma `pt_BR`, uma voz, qualidade `medium`, taxa de 22.050 Hz e dataset CC0.

**Ressalva de licença:** o cabeçalho do repositório Hugging Face marca MIT, mas o cartão Faber menciona CC0 para o dataset, sem declarar inequivocamente a licença dos pesos ONNX. Existe uma [discussão aberta pedindo essa confirmação](https://huggingface.co/rhasspy/piper-voices/discussions/111). Não redistribuímos os pesos e o instalador não os baixa; confirme com os mantenedores/termos atuais antes de usar ou redistribuir.

Os SHA-256 observados no arquivo testado são:

- `pt_BR-faber-medium.onnx`: `858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7`
- `pt_BR-faber-medium.onnx.json`: `7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f`

Coloque o modelo e o JSON no diretório privado `~/.local/share/aurora/voices/pt_BR-faber-medium/` (ou no equivalente sob `$XDG_DATA_HOME`) para habilitar a opção no onboarding. O runtime [Piper](https://github.com/OHF-Voice/piper1-gpl) é distribuído sob GPL-3.0-or-later; modelo e runtime têm licenças distintas. A voz só é carregada se a pessoa a selecionar; o carregamento sob demanda evita disputar CPU com Ollama ao iniciar a sessão.
