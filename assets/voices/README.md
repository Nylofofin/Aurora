# Vozes locais

O catálogo ativo mantém Faber (Piper) e oferece dez estilos brasileiros do [Supertonic 3](https://github.com/supertone-oss-archive/supertonic-py): F1–F5 e M1–M5. Os estilos compartilham um único modelo local; escolher outro estilo não baixa outro modelo separado. A instalação pessoal guarda os dados em `~/.local/share/aurora/voices/` e o cache do runtime Supertonic em seu diretório de cache do usuário. Pesos não são distribuídos no repositório nem no RPM.

O pacote Python oficial chama-se [`supertonic`](https://pypi.org/project/supertonic/). A API documentada usa `TTS(auto_download=True)`, `get_voice_style(voice_name=...)` e `synthesize(..., voice_style=..., lang="pt")`. A Aurora usa oito passos de síntese — o padrão documentado pelo Supertonic — e três threads locais. Menos passos reduzem a latência, mas pioram a qualidade; por isso a Aurora prioriza uma fala inteligível em vez do atalho de três passos usado anteriormente. Respostas longas são enviadas ao player por trechos curtos, para a reprodução começar sem esperar a resposta inteira. A primeira prévia baixa o modelo compartilhado, aproximadamente 400 MB segundo a documentação upstream; por isso a interface avisa e só baixa quando solicitado. Faber segue disponível como opção independente.

**Licença:** código Supertonic sob MIT; pesos sob OpenRAIL-M, que exige atribuição e impõe restrições de uso. Leia os termos upstream antes de redistribuir ou usar fora do contexto pessoal. O projeto Aurora não inclui os pesos. A qualidade e a latência variam por máquina e ainda devem ser avaliadas pelo usuário neste hardware.

O catálogo mantém Faber como nome próprio da voz Piper e usa nomes autorais para identificar os dez perfis Supertonic. Os nomes exibidos não alteram o identificador do modelo nem seus parâmetros acústicos.

## Próximo candidato para avaliação

Kokoro-82M é uma alternativa local leve para comparar em outro ciclo: o cartão oficial publica os pesos sob Apache-2.0 e lista três vozes em português brasileiro (uma feminina e duas masculinas). O próprio catálogo alerta que idiomas não ingleses podem ter suporte de G2P/dados de treino reduzido. Por isso, ainda não foi trocado pelo Supertonic: precisa passar por comparação real de qualidade, latência no hardware alvo e suporte de empacotamento da Aurora antes de ser oferecido. Fontes primárias: [cartão do modelo Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) e [catálogo de vozes](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

## Nomes do seletor

Os rótulos são nomes de perfil da Aurora, não nomes pessoais dos locutores. Correspondência do catálogo:

| Perfil | Nome exibido |
|---|---|
| F1 | Soreli |
| F2 | Averin |
| F3 | Neriva |
| F4 | Velune |
| F5 | Calira |
| M1 | Jorven |
| M2 | Orvel |
| M3 | Tavren |
| M4 | Kaelor |
| M5 | Zevran |
