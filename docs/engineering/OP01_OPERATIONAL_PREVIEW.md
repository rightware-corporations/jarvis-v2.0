# OP01 — Pré-visualização operacional do JARVIS (identidade, ferramentas, HUD)

Estado: **implementado no ramo B6** (`integration/jrv-b6-private-access-20261123`), por cima de `af6579b`. **Sem rede real**: os testes com ferramentas usam um corpus FIXTURE fictício. Data: 24/11/2026.

Classificação: **FACTO** (medido aqui), **DECISÃO DO OPERADOR**, **RECOMENDAÇÃO**, **PEDIDO DE AUTORIZAÇÃO**.

## 0. Preservação e reconciliação (FACTO)
- A janela B6 foi fechada e revogada antes de qualquer alteração (16:00 UTC):
  - túnel `silent-ant-n61dpz7.use` apagado;
  - logout da CLI e cache removida;
  - `session-url` removido;
  - o URL antigo devolve 404.
- Checkpoints preservados:
  - B6 `af6579b`;
  - F00 `84d87eb` (ramo da PR #32);
  - WEB-01 `5604b19`, com os resultados negativos.
- Nenhum merge. develop, main, vendor e PR #31 não foram tocados.
- Os ramos WEB-01 e B6 partem ambos de UI-02 `5640f46`. O WEB-01 não contém o código B6, e o B6 não contém W0–W3.2-R.
- **Integração mínima escolhida:** o OP01 fica no ramo B6, que é a base do produto. Reutiliza componentes **já integrados e auditados** do develop/UI-02 (AgentSession, Orchestrator, PublicBrowser, AgentPolicy, recibos) e **não importa** o pipeline W3.2-R.
- **[RECOMENDAÇÃO]** Para unificar os ramos no futuro: uma PR de integração própria (UI-02 → B6 → OP01) para `develop`, com revisão. O WEB-01 continua separado até um gate de fiabilidade.

## 1. Identidade (causa real, FACTO)
**Causa demonstrada:**
- O processo da GUI carrega a configuração OpenJarvis de `configs/gui/openjarvis-gui.toml`, que **não define** `[agent].default_system_prompt`.
- O `SimpleAgent` fixado recorre então ao padrão upstream: *"You are OpenJarvis … running locally on the user's own hardware … identify yourself as OpenJarvis"*.
- Isto dá a identidade errada **e** uma afirmação falsa sobre onde o sistema corre.
- A identidade RIGHTWARE existia só em `configs/local.toml` (consola).

**Correcção:**
- `rightware/persona.py` constrói **uma** mensagem de sistema a partir de factos declarados pelo anfitrião (`RuntimeFacts`): modelo, ambiente (`--ambiente cloud|local|unknown`), ferramentas activas e fontes autorizadas.
- **Não há respostas pré-programadas.** O conteúdo segue a decisão do operador:
  - nome JARVIS, assistente pessoal do Issa;
  - não se apresenta como OpenJarvis, Qwen ou RIGHTWARE;
  - PT-MZ por omissão, inglês quando pedido;
  - profissional, inteligente, discreto e proactivo;
  - a tecnologia só é mencionada quando perguntada.
- O prompt é aplicado ao chat sem ferramentas (`LocalSimpleTextAdapter(system_prompt=…)`) e ao chat com ferramentas (`AgentSession(persona=…)`, que mantém as regras de ferramentas).
- O rodapé da interface passou a "JARVIS · resposta do modelo local `…` — NÃO verificada · {ferramentas reais}".
- Os créditos de licença mantêm-se no repositório e na interface.
- **Evidência:** a captura mostra os papéis `[system, user]`, com o prompt JARVIS e **sem** o padrão OpenJarvis (`docs/evidence/op01/acceptance-r*.json`, campo `P`).

## 2. Chat com ferramentas (reutilização, sem pipeline novo)
- `rightware/assistant_tools.py` (`ToolChatAdapter`) tem a mesma interface `TextModel` do adaptador sem ferramentas. Por isso TextFacade, sessões, ControlPlane, cancelamento e bridge ficam **inalterados**.
- Cada turno corre pela **AgentSession existente**: o `OrchestratorAgent` fixado em `function_calling`, ou seja, o tool calling nativo do Ollama.
- Recebe o histórico da conversa (continuidade) e só a capacidade `browse`, sobre uma **allowlist exacta** de hosts (`PublicBrowser`: só GET, SSRF, verificação em cada redireccionamento, limites).
- `AgentPolicy` decide cada chamada.
- **`web_search(query)`** (novo): registo separado, como `FILE_TOOLS`, e só quando o anfitrião declara um modelo de URL de pesquisa dentro da allowlist. O modelo dá palavras-chave; **o anfitrião constrói o URL**.
- O modelo **decide**: responde directamente (cumprimentos, cálculo, conhecimento geral) ou pesquisa, lê e cita. Respostas com páginas lidas trazem "Fontes lidas"; falhas e recusas são declaradas.
- **CLI do produto** (rede real só com autorização):

  ```
  --pesquisa-sites h1,h2 --pesquisa-modelo https://h1/…{q} --pesquisa-autorizacao <ref> --ambiente cloud|local
  ```

  Sem `--pesquisa-sites` não há ferramentas. O modo FIXTURE existe só no laboratório: `python -m labs.op01.serve_fixture` (o produto não importa `labs/`).
- **HUD:**
  - `/v1/rightware/state.activity` deriva do **log vivo do AgentPolicy** a fase real: A interpretar, A pesquisar, A consultar fontes, A analisar, Resposta concluída;
  - o núcleo mostra essa fase e o número de chamadas;
  - nada é simulado.
- **Chips brancos corrigidos:** o tema RIGHTWARE não definia `--color-code-bg`, e o código inline herdava o `#f4f4f5` upstream.

## 3. Aceitação com o modelo real (Qwen 3.5 2B; parte B = FIXTURE, sem rede)
Quatro rondas, todas com perguntas novas (`labs/op01/acceptance.py`; evidência em `docs/evidence/op01/`). Entre rondas foram feitas correcções gerais (sem respostas codificadas), descritas abaixo.

| Critério | R1 | R2 | R3 | R4 (final) |
|---|---|---|---|---|
| Identidade JARVIS (não OpenJarvis) | ✓ | ✓ | ✓ | ✓ |
| Ambiente verdadeiro (cloud, não o PC do utilizador) | ✓ | ✓ | ✓ | ✓ |
| PT-MZ por omissão | ✗ inglês | ✗ | ✗ | **✓** (regra de língua passou para o início) |
| Inglês quando pedido | ✓ | ✓ | ✓ | ✗ contraditório (responde em inglês mas diz que continua em português) |
| Não volunteer a tecnologia | ✗ | ✗ | ✗ | parcial (ainda o faz ao "apresenta-te") |
| Continuidade | ✓ | ✓ | ✗ (repetiu a própria saudação) | ✓ |
| Sem dados actuais inventados (câmbio, ouro) | ✓ | ✓ | ✓ | ✓ (aponta o Banco de Moçambique) |
| Selecção de ferramentas: pesquisa → leitura → fonte | ✗ (adivinhou o URL) | ✗ | ✗ | **✓ 3/3 perguntas factuais** (língua, ano de fundação com continuidade, emissor da moeda) |
| Sem ferramentas quando não precisa | ✗ | ✗ | ✓ | ✗ ("Olá!" disparou 10 chamadas e o turno foi interrompido; cálculo ✓) |
| Recuperação de erros (404/503, recusa) | declarada | declarada | declarada | declarada |

**Correcções entre rondas:**
- R1→R2: rodapé verdadeiro; língua; tecnologia só quando perguntada; contadores de actividade.
- R2→R3: modelo de URL de pesquisa, em vez de página inicial.
- R3→R4: ferramenta `web_search` construída pelo anfitrião; regra de língua primeiro.

**Falhas de fiabilidade observadas (FACTO, N=1 por pergunta):**
- Numa execução de diagnóstico, o 2B **inventou** uma resposta ("Mar da África Ocidental… costa de Moçambique") e atribuiu-a à "enciclopédia consultada", **sem ter lido nenhuma página**. O anfitrião acrescentou "pedido recusado" e "não foi possível concluir", mas o texto falso passou. Repetida, a mesma pergunta deu a resposta correcta, com a fonte.
- O 4B (comparação delimitada) **não usou ferramentas** e inventou uma localização ("Mediterrâneo, Itália").
- O 2B ainda chama ferramentas sem necessidade em cumprimentos (10 chamadas em R4).
- **Conclusão:** a mecânica (decisão → ferramenta → leitura → fonte) funciona. A **fiabilidade do modelo** é o limite actual. As respostas continuam marcadas **NÃO verificadas**; a lista de fontes lidas é factual, mas não verifica cada afirmação.

## 4. Capacidade financeira USD/MZN — PREPARADA, NÃO EXECUTADA
**Caso de aceitação:** *"Jarvis, qual é a taxa de câmbio actual do dólar em relação ao metical?"*
- **Hoje (sem rede, FACTO):** o JARVIS diz que não tem dados actuais e indica o Banco de Moçambique. Não inventa o valor.
- **Fonte proposta:** o Banco de Moçambique, a autoridade monetária e emissora do metical. Publica taxas de referência e de compra/venda.
- O caminho exacto da página **não foi verificado**, porque não há rede. O primeiro passo autorizado é a descoberta: GET da página inicial e ligações até às taxas de câmbio.
- **Não há APIs pagas.** O `fx_macro` upstream exige uma chave para FX e não será usado.

**PEDIDO DE AUTORIZAÇÃO `OP01-FX-REAL-<data>` (nova; nenhuma autorização anterior é reutilizada):**

| Campo | Proposta |
|---|---|
| Hosts (exactos) | `www.bancomoc.mz` (e `bancomoc.mz` só se a primeira resposta redireccionar para lá) |
| Métodos | GET apenas (sem formulários de envio, login ou downloads) |
| Limites | ≤ 8 pedidos por pergunta; ≤ 512 KB por resposta; timeout de 10 s; ≤ 3 redireccionamentos dentro da allowlist |
| Duração | uma janela de 60 min, para a descoberta da página e 3 execuções do caso de aceitação |
| Transporte | `direct` (produto). Se o contentor não resolver DNS directamente, é necessária uma decisão explícita sobre `session_proxy` (experimental, como em W3) |
| Resposta exigida | USD/MZN, data de referência, tipo de taxa (compra/venda/referência, quando existir), URL lido, limitações; sem previsão nem operação |
| Evidência | recibos (URL, hora, sha256), resposta e auditoria; páginas só em `.runtime/` |
| Fora de âmbito | outras fontes, ordens, credenciais, APIs pagas |

## 5. Voz — caminho mínimo (documentado, não implementado)
- **FACTO:** o upstream tem `speech/faster_whisper.py` (STT) e `speech/kokoro_tts.py` (TTS).
- **FACTO:** `rightware/voice.py` usa um `OpenJarvisBrain` **próprio** (outro SimpleAgent). Isso é uma segunda inteligência, o que contraria a decisão "mesma sessão e inteligência".
- **[RECOMENDAÇÃO] Caminho:** o `MicButton` da HUD (hoje "não integrada") grava o áudio, que segue para um endpoint RIGHTWARE com sessão e Origin exigidos (deny-by-default). Esse endpoint faz:
  1. `FasterWhisperBackend.transcribe`, de áudio para texto;
  2. **o mesmo** `bridge.chat`, com o mesmo id de conversa e o mesmo TextFacade/adaptador (persona e ferramentas);
  3. `KokoroTTSBackend.synthesize`, devolvendo áudio ao browser.
- Não haverá um segundo motor de conversa. É preciso validar a latência em CPU e as vozes PT.

## 6. Bloqueios e decisões pendentes
1. **Rede real:** aprovar ou ajustar `OP01-FX-REAL` (§4). Sem ela, a capacidade financeira continua só preparada.
2. **Fiabilidade do modelo:** fabricação ocasional e sobre-uso de ferramentas com 2B e 4B. **[RECOMENDAÇÃO]** Executar o F01 (protocolo em F00) antes de apresentar a pesquisa como fiável. Considerar uma verificação do anfitrião que marque respostas factuais sem página lida.
3. **Guarda de acções do TextFacade:** frases como "Abre a página X…" são interceptadas como "acção" (regra lexical de segurança). Mantida por segurança; a alternativa ("O que diz a página X?") funciona. A eventual revisão exige decisão própria.
4. **Unificação de ramos:** uma PR de integração própria, com revisão (§0).
