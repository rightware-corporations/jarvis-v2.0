# JRV-V02 — Experiência de voz do JARVIS

Ramo de integração B6 (mesma aplicação). Baseline `9a9180a` (A+B). Sem merges, sem túnel, sem novos modelos instalados, Docker do goose intacto. Data: 25/11/2026.
Classificação: **FACTO** (medido aqui com áudio e browser reais), **UNIT** (testes), **NÃO VERIFICADO** (sem medição ou fonte consultada nesta sessão).

## 1. Identidade vocal (decisão do operador)
- **Voz aprovada:** `pf_dora` (Kokoro-82M, ONNX int8), em `configs/profile.json` (`voice.status = APROVADA`).
- As amostras de `pm_alex` e `pm_santa` ficam preservadas em `docs/evidence/voice-samples/`.
- **Velocidade persistente:** `voice.speed` (0,5–2,0). **Aprovada: 1,15** (operador, 25/11/2026, decisão final). Aplica-se a todas as sínteses pela rota upstream (saudação, fala progressiva por frases, "ouvir"), que não pedem outra velocidade. A cache de frases tem a velocidade na chave: áudio antigo a 1,00 nunca é servido a 1,15.
- **Teste de velocidade (FACTO; 4 frases; amostras em `docs/evidence/voice-samples/dora-speed/`):**

| Velocidade | Duração do áudio | Tempo de síntese | WER (Whisper) |
|---|---|---|---|
| 1,00 | 17,1 s | 4,69 s | 0,24 |
| 1,10 | 16,1 s | 4,54 s | 0,25 |
| 1,15 | 15,7 s | 4,45 s | 0,23 |
| 1,20 | 14,9 s | 4,20 s | 0,24 |

  A velocidade muda a **duração da fala**, não o custo de inferência (síntese ≈ constante) nem a inteligibilidade medida. A escolha final é auditiva (operador).

## 2. Activação da sessão e saudação
- **"Activar JARVIS":** um gesto explícito por sessão do browser (`sessionStorage`), cumprindo as políticas de autoplay.
  - Depois do clique, a saudação toca automaticamente: hora local + nome do perfil autorizado, mesmo leitor partilhado, cache do anfitrião.
  - **Não abre o microfone.**
- O botão "Ouvir saudação" no núcleo fica para repetir.
- **FACTO (browser real, Africa/Maputo 19h):**
  - 0 fluxos de microfone antes e depois da activação;
  - saudação "Boa noite, Issa. Estou operacional…";
  - não reaparece depois de mudar de página ou recarregar no mesmo separador.

## 3. Conversação por voz
**Reutilizado do upstream:**
- `useSpeech` (botão de microfone, gravação → transcrição → campo do chat);
- `useTts` e o store de áudio partilhado (um só leitor: uma nova reprodução termina a anterior, por isso não há sobreposição);
- `SpeakMessageButton` ("ouvir" por resposta);
- leitura automática `voiceAutoplay`, configurável nas Definições;
- rotas `/v1/speech/*`.

**RIGHTWARE (`ConversationController`, sempre montado; só activo com consentimento explícito no botão "Conversa contínua"):**
- **VAD local** (WebAudio, energia com chão de ruído adaptativo): início ≥ 200 ms de fala; **fim de fala** = 900 ms de silêncio.
- MediaRecorder por enunciado → transcrição upstream → **o mesmo chat** (texto e voz alternam na mesma sessão).
- **Half-duplex:** enquanto o JARVIS pensa ou fala, o microfone é ignorado (sem transcrição da própria voz); `echoCancellation`/`noiseSuppression` ligados.
- **Fala progressiva por frases**, pelo leitor partilhado.
- **Interromper:** pára a reprodução e descarta as frases pendentes.
- **Desligar:** liberta o microfone (tracks "ended") e repõe a leitura automática do utilizador.
- **Estados reais:** a ouvir, a gravar, a transcrever, a pensar, a falar, erro.
- **Segurança da fala:**
  - o texto lido passa pelo filtro do anfitrião (sem rodapé nem linhas de fonte/verificação);
  - **valores financeiros não confirmados (⚠) nunca são lidos**, só um aviso;
  - a voz só começa depois da resposta completa e verificada.

**FACTO (browser real, microfone simulado por um WAV):**
- Ciclo completo: a ouvir 12,7 s → a gravar 14,9 s → a transcrever 17,2 s → a pensar 19,6 s → a falar 39,7 s → a ouvir 48,0 s.
- Nenhuma transcrição durante a fala.
- Interromper: reacção de **43 ms**, 0 sínteses pendentes depois.
- Desligar: microfone "ended" e 0 transcrições nos 6 s seguintes.

**Limites:**
- Half-duplex: não há "barge-in" por voz enquanto o JARVIS fala; usa-se o botão Interromper.
- O VAD por energia pode disparar com ruído forte (não há modelo de VAD no browser).
- Microfone e altifalante reais do operador ainda não testados.

## 4. Latência (FACTO, CPU 4 vCPU, Qwen 2B, modelos pré-carregados)
**Pré-carregamento:** Whisper e Kokoro carregados em segundo plano no arranque (**2,6 s**); o servidor fica pronto em 3,0 s.

| Etapa | Medido |
|---|---|
| Captura (VAD) | fala + **0,9 s** de silêncio para declarar fim |
| Transcrição (6 s de áudio) | 1,1–1,2 s (WAV via HTTP); 2,4 s no browser (webm) |
| Routing (modelo) | 1,4–1,6 s (5,3 s na 1.ª chamada, com o modelo frio) |
| Chat total (routing + inferência + verificação) | 5,2 s (conversa), 7,9 s (cálculo), 31,0 s (cotação com ferramentas) |
| Tempo até ao 1.º token | **= tempo total**: o caminho actual não faz streaming de tokens (TextFacade/AgentSession devolvem a resposta completa) |
| Síntese da 1.ª frase | 0,4–3,8 s |
| Síntese da resposta inteira | 0,9–24,7 s |
| 1.º áudio depois da resposta | **1,8 s** (progressivo) contra até 24,7 s (resposta inteira) |
| Fim da fala → 1.º áudio (ciclo real) | 30,3 s; dominado pela inferência (20,2 s) |

**Decisões:**
- **Implementado:** pré-carregamento, reutilização de instâncias (backends únicos no processo), síntese e reprodução incremental por frases, cache de frases curtas, cancelamento da fila.
- **Não implementado:** streaming de tokens para a voz. A verificação financeira exige o texto completo antes de qualquer fala, e o caminho de ferramentas não faz streaming. Streaming de tokens no ecrã para respostas sem ferramentas é possível no futuro, com autorização.
- A inferência do 2B é o factor dominante; não foi substituída nesta fase.

**Qualidade observada:**
- O 2B respondeu errado a "doze vezes sete" no caminho de chat simples (2×2=4…); no caminho com router respondeu **84**.
- As decisões do router nem sempre são as esperadas ("plano para 90 dias" → ferramentas; "factores do ouro" → conversa). Ficou registado, sem afinação.

## 5. Investigação de motores vocais (documental; NADA instalado)
Espaço livre actual: **~510 MB** (as imagens Docker do goose, 15 GB, mantêm-se).

| Motor | Licença | Português | Expressividade / voz própria | Recursos (indicativos) | Streaming | Estado |
|---|---|---|---|---|---|---|
| **Kokoro-82M (ONNX int8)** — actual | Apache-2.0 (pesos) | **pt-br** (3 vozes); sem pt-PT/pt-MZ | média; sem clonagem; voicepacks por mistura de estilos | **FACTO:** 89 MB + 27 MB; CPU; RTF ≈ 0,33 aqui | por frase (implementado) | em produção (opt-in) |
| **Piper** (VITS) | MIT no repositório original rhasspy/piper; o fork activo OHF-Voice/piper1-gpl é GPL-3.0 (**NÃO VERIFICADO** nesta sessão) | vozes pt-PT e pt-BR (ex.: `pt_PT-tugão`; **NÃO VERIFICADO**) | baixa a média; voz própria por treino/fine-tune | ~20–60 MB por voz, CPU muito leve | por frase | candidato para pt-PT leve |
| **Chatterbox Multilingual** (Resemble AI) | MIT (**NÃO VERIFICADO**) | 20+ línguas, incluindo português (**NÃO VERIFICADO**) | alta (controlo de emoção); **clonagem zero-shot** por amostra de referência | ~0,5 B parâmetros; PyTorch; GPU recomendada; vários GB | limitado | não cabe sem libertar disco; CPU provavelmente lento |
| **ResembleAI/Chatterbox-Multilingual-pt-pt** | por confirmar | pt-PT (pelo nome) | idem | idem | — | **NÃO VERIFICADO:** existência e conteúdo do repositório não confirmados nesta sessão (sem rede autorizada para pesquisa) |

**Requisitos para avaliar um motor novo (a aprovar antes de instalar):**
- Piper: ≤ 100 MB e pacote `piper-tts`.
- Chatterbox: PyTorch CPU (≥ 700 MB) + pesos (≥ 1 GB), sem garantia de latência aceitável em CPU. Exige libertar espaço (por exemplo, as imagens Docker do goose, só com aprovação) ou GPU.
- **Identidade vocal própria:** só com voz gravada com consentimento explícito do dono da voz e licença compatível.

## 6. Próxima missão registada — JRV-R02 (agente de pesquisa na Internet)
Depois da estabilização da voz:
- A Wikipédia deixa de ser a única fonte geral.
- Investigar a reutilização no OpenJarvis fixado de `WebSearchTool`, `Browser`, `PDFTool`, `DeepResearchAgent`, `ResearchLoop` e o Browser Assistant.
- Avaliar SearXNG, DuckDuckGo, Crawl4AI e Firecrawl self-hosted.
- Objectivo: pesquisa geral, navegação autónoma, leitura de documentos, comparação de fontes, verificação e respostas com citações, com as políticas de rede, os recibos e a integridade já existentes.
- **Só registada; nada iniciado.**

## 7. Evidência
- `docs/evidence/voice-samples/`: 3 vozes × 4 frases; Dora × 4 velocidades; métricas; captura da HUD.
- `docs/evidence/voice-v02/`: linha temporal da conversa contínua, latência, captura.
- Testes:
  - Vitest: VAD, divisão de frases, fala progressiva cancelável, saudação, filtro de fala;
  - Python: rotas de voz, limites de corpo e router.
