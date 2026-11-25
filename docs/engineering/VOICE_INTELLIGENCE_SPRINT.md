# VOICE & INTELLIGENCE SPRINT (25/11/2026)

Ramo: B6 (`integration/jrv-b6-private-access-20261123`). Sem merges. Sem túnel. Sem pedidos de rede de pesquisa. F01 não retomado.
Classificação: **FACTO** (medido aqui), **UNIT/FAKE** (testes), **REAL** (Qwen/Whisper/Kokoro locais).

## 1. Inspecção prévia (FACTO)
- **OpenJarvis fixado:**
  - `speech/faster_whisper.py` (STT) e `speech/kokoro_tts.py` (TTS, exige o pacote `kokoro`, ou seja PyTorch);
  - rotas `/v1/speech/{transcribe,synthesize,health,tts/health}`;
  - frontend com `useSpeech` (MediaRecorder → transcrição → **o mesmo campo do chat**) e `useTts`/`SpeakMessageButton` ("ouvir" em cada resposta);
  - `tools/calculator.py` (avaliação segura por AST).
- A UI-02 tinha desactivado o microfone de propósito.
- **Disco** (bloqueio inicial): volume a 100%, com 117 MB livres. Removi só o que estava substituído ou se recria: `scratchpad/ui01`, venvs antigos e caches uv/npm/pip. Fiquei com ~1,5 GB.
- **Não toquei** em `/var/lib/docker` (15 GB, imagens goose/Gateway) nem nas exportações OCI (`scratchpad/sv`).

## 2. Voz (implementada, opt-in `--voz`)
- **STT:**
  - o `FasterWhisperBackend` **upstream**, sem alterações (modelo `base`, CPU int8);
  - modelo em `.runtime/voice/whisper` (cache HF, depois offline).
- **TTS:**
  - o **mesmo modelo Kokoro-82M** via `kokoro-onnx` (int8, 89 MB + 27 MB de vozes), atrás da interface **upstream** `TTSBackend` (`rightware/gui/voice.py`);
  - motivo: o backend upstream exige PyTorch (mais de 1 GB), que **não cabe** no disco desta sessão;
  - voz por omissão `pf_dora` (pt-br); `backend_id="kokoro-onnx"`, para o upstream não aplicar a voz inglesa da configuração.
- **Integração na mesma sessão:**
  - rotas e frontend **upstream**: o texto transcrito entra **no mesmo chat** (mesma conversa, persona e ferramentas), e as respostas são lidas pelo botão "ouvir";
  - não há segundo assistente nem segundo motor.
- **Segurança:**
  - as rotas de voz só são permitidas com `--voz` e exigem sessão;
  - em modo público exigem Origin (ORIGIN_REQUIRED);
  - **limite de corpo** com Content-Length obrigatório: 5 MB (transcrição) e 16 KB (síntese);
  - CSP com `media-src 'self' blob:` (necessário para reproduzir o áudio gerado na própria página; nenhuma origem externa);
  - tudo corre localmente e o áudio não sai do anfitrião.
- **Instalação:**
  - `python -m rightware.gui voice-setup` instala os pacotes **fixados** no venv do runtime (o `setup` recria esse venv) e verifica os modelos pelos sha256 registados;
  - os modelos estão em `.runtime/voice` e **nunca são commitados**.
- **Downloads feitos hoje** (dependências desta missão, não pesquisa):
  - PyPI (pacotes);
  - `github.com/thewh1teagle/kokoro-onnx` releases (modelo e vozes; sha256 em `docs/evidence/voice-intelligence/kokoro-model-SHA256SUMS`);
  - Hugging Face `Systran/faster-whisper-base`.

**Validação REAL:**

| Teste | Resultado |
|---|---|
| Kokoro (`pf_dora`) | 6 s de fala gerados em 1,8 s |
| Whisper `base` | 6 s transcritos em 1,0–2,0 s; "Olá, isso sou o Jarvis, a taxa média do dólar hoje é 60 e 3,90 e um medicais" (erros em "Issa" e em números) |
| HTTP pela PolicyApp | health OK; transcrição 2,0 s (pt, confiança 0,996); síntese 1,4 s (WAV, `pf_dora`); síntese >16 KB → 413; anónimo → 401 |
| **E2E no browser** (Chromium com microfone simulado por um WAV) | botão "Falar com o JARVIS" → gravação → transcrição no campo do chat ("Já vi isso quanto a 12 vezes 7.") → resposta do mesmo chat → "ouvir": `synthesize 200 audio/wav` (7–11 s para respostas longas) e reprodução sem erro, depois de corrigida a CSP |

**Limites:**
- O Whisper `base` erra nomes ("Jarvis" → "Já vi isso") e números. O `small` (~460 MB) não cabe no disco actual.
- A voz é pt-br (o Kokoro não tem pt-PT/pt-MZ).
- Não foi validada no hardware do Issa.
- A leitura automática (`voiceAutoplay`) está desligada: o utilizador clica em "ouvir".

## 3. Inteligência
- **CalculatorTool upstream** é ferramenta declarada pelo anfitrião (`calculator`). Recusa código (`__import__`).
- **Conversa directa vs ferramentas:** `ModelRouter`, em que **o modelo decide** (`{"rota": "conversa"|"ferramentas"}`), sem regras por palavra-chave.
  - Qualquer falha ou saída inesperada leva a "ferramentas" (fail-safe).
  - "conversa" usa a mesma persona, sem ferramentas: o cumprimento passou de ~16 s com chamadas de ferramentas para 6,7–10,3 s sem nenhuma.
- **Estados contraditórios:** o novo estado `ANSWERED_WITH_TOOLS` aplica-se quando uma ferramenta declarada teve sucesso (antes dava `TOOLS_FAILED`). O texto de `TOOLS_FAILED` passou a ser verdadeiro e não contraditório: "não foi possível concluir a parte do pedido que dependia de ferramentas…".
- **Integridade:**
  - o anfitrião **remove linhas do modelo que imitam as suas anotações** ("Fonte…", "✓/⚠ Verificação do anfitrião"); observado: o 2B copiou um ✓ do histórico;
  - verificação de atributo **na mesma linha**;
  - o modelo recebe valores **inequívocos** (número + texto com unidade); a forma impressa do documento fica só no registo do anfitrião.
- **Persona:** valores de ferramentas são factos com fonte, nunca simulações; copiar compra, venda e média com o nome dado pela ferramenta; margem (lucro ÷ preço de venda) vs markup (lucro ÷ custo), indicando sempre qual se usa.
- **ECB:** o URL passou para `api.frankfurter.dev/v1` (o `.app` dava 301 a 24/11). **Exige uma nova autorização de rede que inclua `api.frankfurter.dev`.**

**Validação REAL** (Qwen 2B, offline com os documentos BM reais de 24/11, voz activa; antes e depois das correcções):

| Pergunta | Antes | Depois |
|---|---|---|
| Bom dia | ✓ directo, 6,7 s | ✓ directo, 10,3 s |
| Organizar receitas e despesas | ✓ sem corte (4 chamadas, contra 12 ontem); pede dados reais | ✓ igual |
| Margem (120 un.; 350/210) | ✗ 66,67% (markup chamado margem) | ✓ **40%**, com o cálculo |
| USD/MZN | ✓ valores certos; ✗ chama-lhe "simulação" | ✓ valores certos; ✗ ainda diz "simulação" |
| 250 USD à venda | ✓ 16 135 MZN | ✓ 16 135 MZN (o anfitrião avisa que não houve ferramenta financeira nesse turno) |
| XAU/USD | ✗ atributos trocados + **✓ falso imitado** | ✗ 36,29 (o ⚠ do anfitrião detectou) → depois da vista inequívoca: ✓ **3 629,39 / 3 630,60** USD/onça, "referência diária, não tempo real" |

N=1 por pergunta: são resultados reais, mas não uma taxa de fiabilidade. A palavra "simulação" aplicada a valores oficiais continua por resolver no 2B.

## 4. Próximo passo (recomendação)
1. Nova autorização de rede para a apresentação (hosts de 24/11 + `api.frankfurter.dev`).
2. Validar a voz no browser real do operador (microfone e altifalante).
3. Decidir se se libertam as imagens Docker para permitir o Whisper `small` ou o Kokoro com PyTorch.
4. Retomar F01 (configuração D e 4B) só com autorização.
