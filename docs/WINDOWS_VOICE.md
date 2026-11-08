# Jarvis do Issa — voz e acções Windows (H20)

Estado: **código e testes unitários prontos; voz, microfone e acções Windows NOT RUN em Windows real.** Não declarar PASS sem executar a secção «Validação real» e registar os resultados em `docs/HANDOFF.md`.

## O que existe

```
microfone ──record_until_silence (upstream)──► WAV 16 kHz
   ──FasterWhisperBackend (upstream, local, pt)──► texto
   ├─ pedido de acção? (regras fixas em português, nunca o modelo)
   │     └─ sessão autorizada? → "Queres que eu abra…? sim/não" → executa → confirma processo
   └─ senão: SimpleAgent + OllamaEngine (upstream) com o prompt do Issa e histórico da sessão
──► resposta ──► voz (Windows SAPI por omissão, ou Kokoro do upstream) + texto no ecrã
```

| Componente | Origem | Notas |
|---|---|---|
| STT | `openjarvis.speech.faster_whisper.FasterWhisperBackend` | Modelo `small` por omissão, CPU int8, língua `pt`. Instanciado directamente: **sem** descoberta automática, logo sem recurso a OpenAI/Deepgram. |
| Gravação/reprodução | `openjarvis.speech.voice_io` | Pára após 1,5 s de silêncio; desiste se não houver fala em 5 s; máximo 30 s. |
| Conversa | `SimpleAgent` + `OllamaEngine` | O mesmo motor do `chat`; histórico mantido durante a sessão. |
| TTS por omissão | Windows SAPI (`System.Speech`) | Já incluído no Windows, offline. Usa uma voz **pt-PT**, ou pt-BR se for a única. Sem voz portuguesa instalada, avisa e continua só em texto. |
| TTS opcional | `KokoroTTSBackend` (upstream), voz `pf_dora` | Só português do **Brasil**; instala torch (vários GB) e exige `espeak-ng`. |
| Acções | `rightware/windows_actions.py` | Apenas `%SystemRoot%\System32\notepad.exe` e `calc.exe`, sem shell nem argumentos. |

### Regras de segurança das acções

1. Desligadas por omissão. Só a flag `--allow-actions` as autoriza, e apenas nessa sessão.
2. Cada pedido pede confirmação. Só «sim» ou «confirmo», sem negação, executam. Qualquer outra resposta, silêncio ou Ctrl+C cancela.
3. Só pedidos explícitos («abre…», «podes abrir…», «inicia…») contam. Perguntas como «Já abriste o Bloco de Notas?» e frases negadas («não abras…») nunca disparam acções. Duas acções na mesma frase são recusadas.
4. «Abri» só é dito depois de o `tasklist` mostrar um **novo** processo (`notepad.exe`, ou `CalculatorApp.exe`/`calc.exe`). Caso contrário, a resposta é «não consegui confirmar».
5. Se o modelo afirmar ter executado algo sem acção real, é acrescentado «nenhuma acção foi executada neste pedido».
6. A auditoria fica em `.runtime/logs/actions-AAAAMMDD.jsonl`, com acção, autorização, confirmação, resultado e PID. **Não guarda texto da conversa.**

## Instalação no Windows (só com autorização do dono do PC)

Requisitos: Windows 10/11 x64, Git, Python 3.11–3.13 x64, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com/download), microfone e colunas. Espaço: cerca de 1 GB de dependências de voz mais o modelo Whisper `small` (cerca de 460 MB, descarregado do Hugging Face no primeiro arranque). Os modelos Ollama são à parte.

```powershell
git clone --branch develop --recurse-submodules https://github.com/rightware-corporations/jarvis-v2.0.git
cd jarvis-v2.0
python jarvis.py setup --voice
ollama pull qwen3.5:2b
python jarvis.py doctor
```

- `setup --voice` = `uv sync --frozen --no-dev --extra speech` sobre o lockfile do upstream fixado: não acrescenta dependências novas. Usar sempre `--voice` em reinstalações, porque `setup` sem a flag remove o extra de voz.
- Voz portuguesa do Windows: *Definições → Hora e idioma → Idioma e região → Adicionar idioma → Português (Portugal)*, com a opção de voz/conversão de texto em voz. Para confirmar:

```powershell
Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices().VoiceInfo | Select Name, Culture
```

- Opcional, Kokoro: `python jarvis.py setup --kokoro`, instalar o `espeak-ng` e arrancar com `--tts kokoro`.
- Atrás de um proxy: o processo de voz remove as variáveis de proxy (para não desviar o tráfego local do Ollama). Nesse caso o primeiro download do Whisper falha, e o modelo tem de ser descarregado antes noutra janela.

## Arranque

```powershell
# Ollama numa janela própria (sem cloud):
$env:OLLAMA_NO_CLOUD = '1'; ollama serve
```

```powershell
# Noutra janela:
python jarvis.py voice                      # voz, sem acções Windows
```

```powershell
python jarvis.py voice --allow-actions      # autoriza Bloco de Notas/Calculadora, com confirmação
```

Outras opções: `--model qwen3.5:4b`, `--stt-model base|small|medium`, `--tts sapi|kokoro|none`, `--text-only` (sem microfone).

Uso: **Enter numa linha vazia → falar**; escrever texto também funciona. «sair» termina. **Ctrl+C** cancela o passo em curso (gravação, resposta do modelo, fala); na linha de entrada termina a sessão.

## Validação real (operador, Windows autorizado)

Registar em `docs/HANDOFF.md`: SHA, versão do Windows, CPU/RAM, microfone, voz SAPI usada, modelo Ollama, tempos aproximados e o resultado de cada linha. Copiar as linhas `actions-*.jsonl`. **Não colar conversas pessoais.**

| # | Cenário | Esperado | PASS/FAIL |
|---|---|---|---|
| V1 | `setup --voice`, `doctor` | Termina sem erro; `READY` | |
| V2 | `voice --text-only --tts sapi`, escrever «Quem és tu?» | Resposta em PT como Jarvis do Issa/RIGHTWARE, **ouvida** numa voz portuguesa | |
| V3 | Enter, dizer «Qual é a capital de Moçambique?» | Transcrição correcta no ecrã; resposta «Maputo» falada | |
| V4 | Seis turnos falados (identidade, Orion fictício, Maputo, recordar Orion, orçamento desconhecido, «já abriste o Bloco de Notas?») | Contexto mantido; não inventa orçamento; não diz que abriu nada | |
| V5 | **Sem** `--allow-actions`: dizer «Abre o Bloco de Notas» | Recusa; nenhuma janela abre; auditoria `REFUSED` | |
| V6 | `--allow-actions`: «Abre o Bloco de Notas» → «sim» | Bloco de Notas abre; «Confirmei que o processo está em execução»; auditoria `VERIFIED` com PID | |
| V7 | «Abre a calculadora» → «não» | Nada abre; «Cancelado»; auditoria `CANCELLED` | |
| V8 | «Abre a calculadora» → «sim» | Calculadora abre; `VERIFIED` | |
| V9 | «Abre a calculadora», e na confirmação carregar Ctrl+C | Nada abre; `CANCELLED`; sessão continua | |
| V10 | Ctrl+C durante a gravação e durante uma resposta longa | «Gravação cancelada» / «Cancelado»; sessão continua | |
| V11 | Parar o Ollama e fazer uma pergunta | «Não consigo ligar ao modelo local…»; sem crash | |
| V12 | Fechar e voltar a arrancar após reinício do PC | Arranca com o mesmo comando | |

Critério de aceitação H20: V1–V9 PASS no Windows do Issa ou num host autorizado equivalente; V10–V12 PASS ou com falha documentada. Qualquer abertura **não pedida** ou confirmação ignorada = **P0 NO-GO**.
