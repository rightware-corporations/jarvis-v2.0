# RIGHTWARE Jarvis v2 — continuidade

## Decisão desta sessão

O utilizador forneceu `rightware-corporations/jarvis-v2.0` para concretizar a implementação separada baseada no OpenJarvis. O projecto anterior `rightware-corporations/jarvis` deve ser preservado. Branches: main e develop. Produto independente do Claude no runtime; modelo local ou auto-hospedado, sem API paga obrigatória.

## Evidência anterior, não reexecutada por esta fundação

Ensaio OpenJarvis/Qwen3.5 2B/Ollama 0.40.15 em CPU: conversa, resposta Maputo, recordação parcial de Orion e ferramenta calculator real (137 × 29 = 3973). Personalização de identidade funcionou com agent.default_system_prompt. Houve invenções sobre Orion; fidelidade não aprovada. O ensaio anterior resolveu dependências no momento; esta fundação usa uv.lock upstream com --frozen, pelo que uma nova prova real é necessária.

Mark XXXIX-OR foi investigado: Gemini Live/OpenRouter, sem percurso Ollama encontrado e README com uso não comercial. Não foi importado.

## Implementado

- Upstream fixado em submódulo, atribuição e licença.
- Camada RIGHTWARE de setup/doctor/chat; configuração portuguesa.
- Logs de instalação e remoção de credenciais cloud do ambiente filho.
- Quatro testes dirigidos de configuração/encaminhamento.
- Workflow leve para estes testes; não é CI de inferência nem suite upstream.

## Limites

Sem migração da camada Wyzer. Sem voz, GUI, wake word, acções Windows ou memória persistente validados. Não chamar esta etapa release. OLLAMA_NO_CLOUD no cliente não reconfigura um daemon já existente. O Kaggle é laboratório temporário. Não instalar no PC do destinatário por inferência.

## Próxima execução

1. Clonar develop com submódulos; executar setup e doctor com Ollama local.
2. Executar o corpus curto com modelo real e preservar respostas/tempos por SHA.
3. Comparar uma alternativa de modelo no mesmo ambiente; escolher pelo resultado, não apenas tamanho.
4. Só depois integrar voz e tarefas no Windows autorizado.

Consultar docs/VALIDATION.md para o que foi efectivamente validado nesta entrega. Actualizar este ficheiro após cada resultado material.


## ADENDA — 08/11/2026: execução em 48 horas e disciplina obrigatória de handoff

### Direcção explícita da RIGHTWARE (CONFIRMADA)
- **Prazo e prioridade:** dispor de um Jarvis v2 utilizável dentro de dois dias de trabalho/48 horas de execução. Parar ciclos intermináveis de QA; corrigir bloqueadores do percurso real. O prazo é meta de execução, não declarar sucesso antes do aceite.
- **Handoff contínuo:** após **cada output material** (ensaio, alteração, CI, erro, decisão), actualizar este handoff **no mesmo ciclo de trabalho**, com SHA, ambiente, comando/cenário, resultado observado, PASS/FAIL/REVIEW/NOT RUN, evidência sanitizada, bloqueio, responsável e próxima acção. Não substituir histórico, não inventar resultados; manter PR Draft até critérios cumpridos.
- **Motor em operação:** independente de Claude/serviços pagos obrigatórios. Kaggle é laboratório transitório, não runtime do produto.
- **Repositórios:** desenvolver apenas neste `rightware-corporations/jarvis-v2.0` na `develop`; preservar `rightware-corporations/jarvis` como referência histórica. Apenas `main` e `develop`.

### Estado verificado antes desta adenda
- Base `develop@8d92705c30f965e4e344427604a8500bab45d388`; PR #1 Draft; duas execuções do workflow de fundação em 08/11 PASS (runs `42492070438` e `42492070280`), cada uma contendo apenas testes unitários do launcher no Linux. Não são validação de inferência.
- Upstream fixado em `f21d902f4d3bd7f0f3f138f1a4613019a394b549`; launcher português com `agent=simple` e modelo inicial `qwen3.5:2b`. O agente `simple` do upstream **não aceita ferramentas**, embora aceite histórico de mensagens: a prova da calculadora exige um caminho de agente distinto, com resultados de ferramenta auditados.
- O relato final do Work confirma Ollama 2B descarregado/carregado e conversa real iniciada, mas **não inclui transcrição completa das seis perguntas, resultado da ferramenta na nova base, avaliação do 4B ou ZIP Kaggle**. Esses resultados continuam NOT RUN/NOT VERIFIED para a v2.0.
- `child_environment()` continua a herdar variáveis proxy para o subprocesso da CLI; `doctor()` ignora proxies nas suas próprias consultas. Rever bloqueio proxy na CLI antes da prova de inferência. Não atribuir ao modelo falhas de transporte.
- Consola desta sessão: Linux x86_64/Python 3.13.5, RAM total ~5.8 GiB, sem nvidia-smi nem Ollama instalado. Não tem acesso garantido ao Kaggle do utilizador ou Windows físico.

### Plano de entrega (RECOMENDAÇÃO DE IMPLEMENTAÇÃO; nenhuma fase abaixo foi validada por esta adenda)
| Janela de trabalho | Entrega exigida | Gate e regra de paragem |
|---|---|---|
| H0–H4 | Baseline reprodutível: revisão de SHA, transporte sem proxy indevido, setup/doctor, corpus curto, script/notebook de ensaio e artefactos de prova sanitizados | CI unitário PASS; nenhuma credencial ou transcript pessoal no git. Não apresentar o doctor como prova de inferência. |
| H4–H12 | Teste GPU Kaggle ou host equivalente: 2B vs 4B, **mesmas seis perguntas**, contexto Orion conhecido/desconhecido, identidade e aritmética. Ferramentas **num cenário separado** com agente habilitado | Respostas completas e métricas (modelo, SHA, GPU, tempos, RAM/VRAM); proibir invenção de dados críticos, falsas afirmações de execução ou ferramenta sem autorização. |
| H12–H20 | Escolher modelo e corrigir até **dois bloqueadores de maior impacto** identificados na prova real, com reteste focalizado | Decisão documentada com evidência; não iniciar treino, refactor ou memória vectorial por rotina. |
| H20–H36 | Integrar STT/TTS PT básicos e **duas acções Windows permitidas** (ex.: abrir Bloco de Notas e Calculadora), confirmação e cancelamento, em host autorizado | Provas com microfone/áudio e efeitos Windows reais; sem autorização explícita, reportar BLOQUEADO, nunca PASS. |
| H36–H48 | Integração, regressão limitada, arranque/reinício e empacotamento de instruções; demonstração de ponta a ponta | Entregar comando de arranque, evidência reproduzível, falhas residuais, aceite ou NO-GO. |

### Critérios mínimos de aceitação do MVP (objectivo)
1. Iniciar Jarvis com procedimento documentado, sem API paga; responde em português e identifica-se como Jarvis da RIGHTWARE.
2. Mantém contexto básico durante seis turnos de uma sessão, incluindo mudança de tópico e retorno. Sobre Orion, só afirma factos fornecidos e assume desconhecer orçamento/equipamentos.
3. Executa uma ferramenta **real** com resultado auditável, distingue resposta calculada pelo modelo de `tool_results`.
4. Numa máquina Windows autorizada, STT reconhece um pedido PT, TTS reproduz resposta; duas acções permitidas só ocorrem com pedido/autorização, confirmação e possibilidade de cancelamento; execução observável.
5. Segurança P0: zero operações não solicitadas, zero segredos publicados; rejeita execução não autorizada e nunca diz que executou algo sem `tool_result` verificado.
6. Repetir arranque após reinício e guardar instruções de uso. UI/HUD cinematográfico, wake word, memória durável, treino de pesos, instalação comercial e arquitectura distribuída **fora do escopo** inicial, salvo funcionalidade pronta comprovada.

**Ponto de corte dos testes:** parar depois de uma comparação controlada e de um reteste dirigido por falha, seguido de smoke final. Não repetir baterias completas sem alteração material. Se P0 continuar, reduzir âmbito e registar NO-GO explícito, sem fingir MVP aceite.

### Protocolo de registo para as próximas saídas
```text
[DATA/HORA UTC+02] [WORK-PACKAGE] [SHA] [AMBIENTE]
OBJECTIVO / COMANDO OU CENÁRIO:
RESULTADO OBSERVADO (PASS | FAIL | REVIEW | BLOCKED | NOT RUN):
EVIDÊNCIA (link, run ID, ficheiro sanitizado):
CAUSA/INCERTEZA:
PRÓXIMA ACÇÃO E CRITÉRIO DE ACEITAÇÃO:
```

**Próxima acção:** corrigir/validar transporte e preparar o harness de comparação versionado no repositório. Executar Kaggle somente com artefactos de execução suficientes; usar GPU para teste, não treino de pesos. Priorizar funcionalidade real, não número de testes.


## ADENDA — 08/11/2026: identidade do destinatário (DECISÃO EXPLÍCITA)

**Correcção confirmada pela RIGHTWARE:** o produto é **JARVIS DO ISSA** (Jarvis — Issa Edition), assistente pessoal **destinado ao Issa**. **RIGHTWARE é a organização desenvolvedora**, não a pessoa a quem o assistente se destina. Esta decisão prevalece sobre a frase histórica «Jarvis da RIGHTWARE» presente nos critérios de aceitação anteriores. Não confundir Issa com o operador da RIGHTWARE nem com a entidade empresarial.

- Identidade esperada em todos os ensaios e no produto: «Sou o Jarvis, assistente pessoal do Issa, desenvolvido pela RIGHTWARE», em português natural; outras formulações correctas são permitidas.
- O prompt inicial em `configs/local.toml` foi alinhado nesta mudança. **Limite:** `prepare_config()` só copia a configuração para `.runtime/openjarvis/config.toml` caso ela ainda não exista. Sessões previamente configuradas **não recebem automaticamente o prompt novo**: actualizar o arquivo runtime com preservação de preferências e sem apagar dados do utilizador.
- Actualizar o corpus do benchmark 2B/4B para avaliar especificamente a identidade do Issa. A referência Orion continua sendo **dado sintético de teste**; não afirmar que é um projecto real do Issa.
- Estado: **DECISÃO REGISTADA / CONFIGURAÇÃO DE REPOSITÓRIO ALTERADA / INFERÊNCIA REAL NÃO REEXECUTADA**. Os testes anteriores não provam que o modelo respeitará a identidade.
- Próxima acção: validar o prompt pela sessão real; em seguida prosseguir a comparação de modelos, voz e ferramentas Windows no prazo do MVP.

## ADENDA — 08/11/2026: H0–H4 transporte, comparador e laboratório Kaggle

**Produto:** JARVIS DO ISSA, desenvolvido pela RIGHTWARE.
**Estado:** preparação e testes unitários no GitHub concluídos; execução de modelos na GPU Kaggle AINDA NÃO EFECTUADA.

### Evidências de cada output material (branch develop)

| Marco | Commit | Evidência / status |
|---|---|---|
| H0-01 Transporte loopback sem proxies herdados | 2ef812ff | Código de rightware/runtime.py alterado; CI PASS |
| H0-02 Regressão de proxies | 4218f416 | tests/test_runtime.py com asserts novos; CI PASS |
| H0-03 Corpus + comparador real OpenJarvis | 6929f0b6 | qa/compare_models.py publicado; execução real NOT RUN |
| H0-04 Testes de preflight | af29fe72 | Casos sintéticos, modelo cloud rejeitado, evidências JSON; CI PASS |
| H0-05 Notebook para GPU | 40617014 | qa/JARVIS_ISSA_KAGGLE.ipynb publicado; Kaggle NOT RUN |
| H0-06 Sintaxe e contrato do notebook | bfbfa841 | CI runs 42498924112 e 42498930402 PASS |
| H0-07 Instruções no README | 1aae7109 | Guia de utilização e limitações publicado |
| H0-08 Ambiente realmente saneado no benchmark | 2d3fcd73 | Usar os.environ.clear() + update(), pois só update preservava proxies; CI run 42499026517 PASS |

### Decisões técnicas aplicadas

- Seis perguntas idênticas em sessões separadas por modelo Qwen3.5 2B e 4B. As respostas completas, latência por turno, SHA, ambiente e utilização de GPU entram num JSON escrito progressivamente.
- Os dados Orion são inteiramente fictícios; o orçamento e os equipamentos não são fornecidos. O modelo não pode inventá-los.
- A identidade correcta é Jarvis pessoal do Issa, desenvolvido pela RIGHTWARE. A configuração existente de uma sessão antiga não é sobrescrita sem revisão.
- O agente simple mantém histórico mas não tem ferramentas. A prova da calculadora é feita separadamente por native_react com CalculatorTool original; só se considera execução se tool_results mostrar success=true e 3973.
- O notebook utiliza o upstream fixado, Ollama 0.40.15 com hash oficial do artefacto Linux, GPU do Kaggle, repositório privado via Kaggle Secret GITHUB_TOKEN e ZIP de evidências. Não faz actualização silenciosa de um checkout já existente.
- Não interpretar testes de CI como demonstração com LLM, voz, microfone, Windows ou produto pronto.

### Próximo gate imediato — H4–H12

1. Abrir qa/JARVIS_ISSA_KAGGLE.ipynb no Kaggle com Internet e GPU, definir GITHUB_TOKEN com acesso read-only ao repositório privado em Kaggle Secrets.
2. Executar as três células por ordem; confirmar o SHA impresso antes de comparar.
3. Guardar o ZIP JARVIS_ISSA_QWEN_EVIDENCE_*.zip e analisar separadamente cada resposta e tool_results, sem atribuir percentagem automática.
4. Actualizar este handoff com tempos, recursos, SHA, respostas, falhas e veredicto, imediatamente após receber o output. Modelo definitivo continua PENDENTE.
5. Passar para voz e acções Windows até ao limite H20 para avaliação do motor, salvo falha crítica documentada.

**Bloqueio:** sem acesso à sessão privada Kaggle a partir deste chat, os testes GPU e a comparação real continuam NOT RUN. Ferramentas Windows e áudio continuam NOT RUN.

## ADENDA — 08/11/2026: coordenação ChatGPT + Claude Code + operador (PLANO OPERACIONAL)

**Origem:** o operador confirmou que Claude Code está activo em desktop no mesmo repositório e pediu divisão das tarefas. Captura indica Claude com checkout em develop, submódulo inicializado no pin e sincronizado com a HEAD df772f0; o Claude ainda não apresentou resultados de código adicional. Este plano distingue **atribuição recomendada** de **resultado executado**.

### Responsabilidades exclusivas para evitar conflitos

| Interveniente | Responsável | Ficheiros / fronteira | Entregável |
|---|---|---|---|
| Claude Code — engenheiro de implementação | Inspeccionar e corrigir launcher, comparador e Kaggle notebook; executar testes e CI; avançar para integração STT/TTS e acções Windows autorizadas | Código em rightware/, qa/, tests/, configs/; guardar resultados, actualizar handoff no mesmo commit/série curta | Código testado, SHA, comandos, provas, NEXT |
| ChatGPT — arquitectura, auditoria e QA independente | Rever diffs, detectar riscos/bugs, formular corpus e critérios de aceitação, analisar resultados JSON/ZIP, priorizar P0, avaliar GO/NO-GO | Revisão read-only enquanto Claude escreve; não fazer commits concorrentes nos mesmos ficheiros | Diagnóstico técnico e recomendações verificáveis; pedir ao Claude que registe a revisão no handoff |
| Operador RIGHTWARE — execução/aceitação | Iniciar notebook Kaggle na conta com GPU e secret privado; controlar consentimento no Windows; verificar voz/acções reais | Kaggle e PC Windows autorizado; nenhuma credencial no chat/repo | ZIP de evidências sanitizadas, resultados Windows e aceitação |

### Protocolo obrigatório

1. **Uma única pessoa/agente escreve em develop por vez.** Antes de qualquer commit/push, executar git fetch e sincronizar, validar HEAD. Não executar resets/force push nem abrir branches extra; main intocada, PR #1 Draft.
2. Claude é o **owner de implementação** durante H4–H36; ChatGPT mantém revisão read-only enquanto ele escreve. Se for necessária alteração directa por ChatGPT, o Claude deve terminar a sua transacção e confirmar que deixou o repo sincronizado.
3. **Após cada output material, actualizar este handoff e registar comando, ambiente, commit SHA, PASS/FAIL/REVIEW/BLOCKED, evidência e próxima acção.** Não acumular resultados sem registo. CI PASS não implica inferência PASS.
4. H4–H12: revisão crítica do notebook/harness e **prova GPU real 2B vs 4B**, só com modelos locais; não instalar Claude no runtime, não substituir upstream ou modelo por opinião.
5. H12–H20: escolher o motor e corrigir até dois bloqueadores reais. H20–H36: voz PT e duas acções Windows com confirmação/cancelamento e consentimento. H36–H48: smoke end-to-end, arranque e entrega com GO/NO-GO.
6. Critério de identidade: Jarvis **do Issa**, desenvolvido pela RIGHTWARE; Orion é cenário **sintético**, não um projecto real declarado.
7. Manter actividade já em curso do Claude: a captura relatou fetch/pull e submódulo inicializado, mas **sem evidência de execução de GPU ou voz**. Não atribuir resultados não comprovados.

### Pedido de implementação imediato ao Claude

Prioridade A: reproduzir o preflight do commit df772f0, validar em profundidade qa/JARVIS_ISSA_KAGGLE.ipynb e qa/compare_models.py (token seguro, clone privado, Ollama 0.40.15/digest, modelos, import do upstream, sessão/contexto, calculadora native_react, tempos/VRAM/JSON, reinício do notebook), corrigir P0 sem refactor. Handoff e CI no mesmo ciclo. Depois o operador executa o Kaggle GPU; ChatGPT analisa o ZIP antes de aprovar modelo.

**Estado desta adenda:** coordenação documentada, sem alteração funcional nesta acção. Respeitar a revisão live de develop no momento de cada novo trabalho.

## ADENDA — 08/11/2026: Kaggle sem token / uma célula (DECISÃO DE SEGURANÇA)

**Pedido explícito da RIGHTWARE:** não fornecer um token GitHub ao Kaggle por razões de segurança; executar a comparação de modelos numa sessão com script único. A alternativa com GITHUB_TOKEN em Kaggle Secrets deixa de ser o caminho recomendado. Mantém-se documentada apenas como experiência opcional, não autorizada por omissão.

### Escolha para o próximo ensaio

- **Novo notebook:** `qa/JARVIS_ISSA_KAGGLE_NO_TOKEN.ipynb`, com uma única célula Python, acesso **só** a `open-jarvis/OpenJarvis` público fixado no SHA `f21d902f4d3bd7f0f3f138f1a4613019a394b549`.
- Não clona o repositório privado `rightware-corporations/jarvis-v2.0` e não necessita de `GITHUB_TOKEN`, segredo Kaggle nem upload de código privado.
- Obtém a distribuição Linux Ollama v0.40.15 com SHA-256 oficial `628c018404a4206493efd38e46251c154ede5141b8b8dc85c659b3b027c47379`, activa `OLLAMA_NO_CLOUD=1` ao iniciar serviço novo, usa loopback e uma GPU se disponível.
- Carrega Qwen3.5 2B/4B; seis perguntas sintéticas, contexto de sessão, identidade do Issa e teste separado `NativeReActAgent` com `CalculatorTool`. Outputs JSON progressivos e ZIP sem pesos, tokens ou conversas pessoais.
- **Fronteira de evidência:** compara modelos no upstream público com uma cópia do perfil RIGHTWARE; **não é prova do launcher privado**. A validação da versão RIGHTWARE permanece depois da escolha do motor, num ambiente autorizado.

### Publicação e QA estática

| Item | SHA / evidência | Estado |
|---|---|---|
| Notebook de uma célula, sem credenciais | `18ab40bb` | Publicado, Kaggle GPU NOT RUN |
| Correcção do log de comandos excessivo | `0b81bacf` | Publicado, CI PASS |
| Teste de sintaxe de célula e código interno / ausência de token | `8f986ef3` | CI runs 42500339491 e 42500342970 PASS |
| README alterado para recomendar caminho sem token | `52244c87` | CI runs 42500395444 e 42500401684 PASS |

### Próxima execução

1. No browser autenticado do GitHub, descarregar `qa/JARVIS_ISSA_KAGGLE_NO_TOKEN.ipynb`; importar para Kaggle Notebook **privado**.
2. Activar GPU e Internet no Kaggle; executar a **única célula**, sem preencher token GitHub nem carregar código privado.
3. Guardar `JARVIS_ISSA_NO_TOKEN_*.zip` e trazer evidência sanitizada ao chat para avaliação 2B/4B.
4. Após receber evidência, actualizar este handoff com SHA upstream, versão Ollama, GPU/VRAM, respostas e tempo por turno, `tool_results`, erros e decisão de modelo. Sem teste real, manter status NOT RUN.
5. Para validar o launcher da RIGHTWARE depois, executar testes no checkout privado local/Windows, não usar a avaliação do upstream como aceitação final da v2.0.

**Estado desta adenda:** notebook pronto e testes estáticos PASS. Nenhuma inferência GPU, voz ou acção Windows foi executada nesta sessão.


## ADENDA — 08/11/2026: correcção de rumo — teste COMPLETO da v2.0 sem token

**Decisão do operador:** aceita tornar o repositório público caso necessário para teste GPU sem token. **NUNCA partilhar token GitHub no chat/Kaggle.** O notebook anterior `qa/JARVIS_ISSA_KAGGLE_NO_TOKEN.ipynb` só compara o upstream público, portanto não valida a integração RIGHTWARE: mantém-se como ensaio preliminar e NÃO como aceite da v2.0.

**Implementação:** o notebook canónico `qa/JARVIS_ISSA_KAGGLE.ipynb` foi ajustado para `git clone --branch develop --recurse-submodules https://github.com/rightware-corporations/jarvis-v2.0.git` sem credenciais, verificando o SHA real antes de executar `qa.compare_models`. Os testes estáticos foram ajustados para exigir ausência de token e inclusão do wrapper. Commits `40afa387` (notebook) e `178e9ad2` (teste).

**BLOQUEIO:** o repositório **ainda está privado**; o proprietário deve concluir revisão de segredos incluindo **todo histórico Git** e, se aprovar, mudar para público em GitHub Settings. A mudança de visibilidade não foi efectuada nesta sessão. Caso deseje manter privado, usar um ZIP local completo de código + submódulo, carregado manualmente num notebook Kaggle privado, sem autenticação GitHub.

**Gate:** só após código real instalado e modelo GPU executado, obter evidência JSON/ZIP, verificar respostas, `tool_results`, identidade do Issa, recursos, falhas e actualizar handoff. CI estático não equivale a teste real.
## ADENDA — 08/11/2026: H4-A auditoria e preparação da prova GPU (Claude Code, engenharia)

[08/11/2026 ~16:50 UTC] [H4-A] base `80cc0b5` → commit desta adenda [cloud Linux x86_64, Python 3.13.18, 4 vCPU, ~15 GiB RAM, **sem GPU**, proxy de saída; `registry.ollama.ai` bloqueado (403)]

**Objectivo:** auditar runtime, comparador, os dois notebooks Kaggle, configuração e testes; corrigir só problemas identificados; deixar o operador pronto para a comparação real 2B × 4B. Respeita a decisão de segurança acima: **nenhum token GitHub no Kaggle**.

### Evidência executada nesta sessão

| Verificação | Comando / cenário | Resultado |
|---|---|---|
| Sincronização | `git fetch` + `git pull --ff-only` (c0fbbb2 → 80cc0b5; 8 commits do operador chegaram durante a auditoria e foram integrados) | PASS, submódulo no pin `f21d902` |
| Dependências reproduzíveis | `python jarvis.py setup` → `uv sync --frozen --no-dev` | PASS (77 s, Python 3.13; upstream aceita >=3.10,<3.14) |
| Artefacto Ollama | download `v0.40.15/ollama-linux-amd64.tar.zst` + `sha256sum` | PASS: 1 543 547 172 bytes, SHA256 igual ao fixado nos **dois** notebooks |
| Arranque do binário Ollama | extracção + `ollama serve` | **NOT RUN**: execução do binário descarregado recusada pela política de permissões desta sessão |
| Tags Qwen3.5 2b/4b no registo | manifesto `registry.ollama.ai` | **BLOCKED** (proxy 403); confirmar no `ollama pull` do Kaggle |
| Cablagem real ao upstream (sem modelo) | `qa.compare_models` e a string `evaluator` do notebook sem token, contra um **stub HTTP de Ollama** (scratchpad, não versionado), com `HTTPS_PROXY` inválido | PASS de cablagem: prompt do Issa no system; histórico 2→12 mensagens nos 6 turnos; `think=false`, `num_ctx=4096`, `num_predict` 256/320; `CalculatorTool` **real** executou `137 * 29` → `3973.0`; modelos descarregados com `keep_alive=0`. **Não é inferência.** |
| Interrupção / reinício | SIGINT a meio da execução, depois relançamento, nos dois caminhos | PASS: `compare_models` exit 130 e `run_status=INTERRUPTED`; modelo parcial `REVIEW_INTERRUPTED` com os turnos já feitos; relançamento preserva `*.previous-*.json` e termina `FINISHED_REVIEW_REQUIRED` |
| Varredura de segredos (pré-requisito para repo público) | `git log --all -p` com padrões de tokens GitHub/OpenAI/Anthropic/AWS/Google/HF/Slack/chaves privadas + nomes `.env`/`.pem`/pesos/`.runtime` | Nenhuma ocorrência nos 22 commits. **Varredura limitada**, não substitui revisão do dono nem o secret scanning do GitHub |
| Testes unitários | `python -m unittest discover -s tests` | PASS 14/14; os testes novos **falham** contra o código anterior (verificado) |

### Problemas identificados e corrigidos

1. **P0 — contrato do notebook quebrado em `40afa38`** (o teste exigia `GITHUB_TOKEN`; falha reproduzida localmente). O operador corrigiu-o em paralelo em `178e9ad`; esta série junta as duas versões e acrescenta a proibição de `UserSecretsClient`, `GIT_ASKPASS` e `x-access-token`, e a exigência de `GIT_TERMINAL_PROMPT="0"`.
2. **P1 — ZIP perdido em falha** (`JARVIS_ISSA_KAGGLE.ipynb` célula 3): `check=True` lançava excepção antes de criar o ZIP, e um OOM/timeout/interrupção do 4B apagava a prova do 2B. O ZIP passa a ser gerado em `finally`, inclui `ollama_server.log` e o código de saída, e a célula só falha depois. (O notebook sem token já tinha `finally`.)
3. **P1 — evidência sobrescrita após reinício** (nos dois caminhos): o JSON anterior é movido para `*.previous-<UTC>.json`; `run_status` global e `REVIEW_INTERRUPTED` por modelo.
4. **P1 — prompt do notebook sem token divergente** de `configs/local.toml`: faltava «Distingue factos fornecidos de hipóteses. Quando não sabes um detalhe, diz que não sabes.». Alinhado byte a byte; um teste novo compara o prompt e as 6 perguntas com `configs/local.toml` e `QUESTIONS`.
5. **P2 — sem prova de GPU efectiva** (nos dois caminhos): `nvidia-smi` não mostra se o modelo correu em parte na CPU. Passa a registar `/api/ps` após o warm-up (`loaded.offload` = full_gpu / partial_gpu / cpu_only, com aviso), `model_digests` do Ollama e o aviso `empty_answer`.
6. **P2 — reinício do kernel** (notebook do repositório): cada célula redefine `ROOT`/`REPO` (sem NameError); verificação de GPU antes do clone; impressão de `REPO SHA:`; o handle do digest passa a ser fechado.

Sem alterações em `rightware/runtime.py`, `configs/local.toml` nem no upstream: a auditoria não encontrou defeitos nesses ficheiros (o transporte sem proxy foi confirmado pelo ensaio com proxy inválido).

### Limitações (não interpretar como PASS)

- **Inferência real, GPU, identidade e contexto: NOT RUN.** O stub só prova a cablagem do harness ao upstream.
- O corpus está duplicado (o notebook sem token embute-o numa string); a coerência é agora garantida por teste, não por fonte única.
- `JARVIS_ISSA_KAGGLE.ipynb` (wrapper RIGHTWARE completo) **só funciona depois de o dono tornar o repositório público**. Essa decisão é do dono e não foi tomada por esta sessão.

### Procedimento para o operador (Kaggle, sem token)

**Canónico (decisão do operador acima): `qa/JARVIS_ISSA_KAGGLE.ipynb`**, depois de o dono rever o histórico e tornar o repositório público: células 1→2→3; confirmar `GPU:` e `REPO SHA:` igual à `develop`; ZIP `JARVIS_ISSA_QWEN_EVIDENCE_*.zip`. Valida o wrapper RIGHTWARE. Após reinício/queda, executar de novo 1→2→3 (checkout, Ollama e modelos reutilizados; relatório anterior em `comparison_2b_4b.previous-*.json`).

**Ensaio preliminar enquanto o repositório for privado (não é aceite da v2.0):** `qa/JARVIS_ISSA_KAGGLE_NO_TOKEN.ipynb` (upstream público + perfil do Issa idêntico ao `configs/local.toml`).
1. Descarregar o `.ipynb` no browser autenticado; Kaggle → *File → Import Notebook*; notebook **privado**; *Session options*: GPU T4, Internet ON. Não configurar Secrets.
2. Executar a única célula. Confirmar `GPU:` com T4, `[PASS] Ollama 0.40.15` e os dois `ollama pull`.
3. Se a sessão cair: executar de novo a célula; o upstream, o Ollama e os modelos são reutilizados, e o relatório anterior fica em `QWEN3_2B_VS_4B.previous-*.json`.
4. Descarregar `JARVIS_ISSA_NO_TOKEN_*.zip`.

**Critério para aceitar a evidência (os dois caminhos):** `run_status=FINISHED_REVIEW_REQUIRED`; `loaded.offload=full_gpu` nos dois modelos; 6 turnos com resposta e sem `empty_answer`; `tool_results` com calculator `success=true` e `3973`. Depois, revisão humana de identidade (Issa/RIGHTWARE), recordação de Orion, recusa de inventar orçamento/equipamentos e não afirmar ter aberto o Bloco de Notas.

**Próxima acção exacta:** o dono decide a visibilidade; com repositório público, o operador executa o notebook canónico (senão, o ensaio preliminar) e entrega o ZIP; a análise regista aqui SHA, tempos, VRAM/offload e respostas. A escolha do modelo continua PENDENTE até essa revisão.

**CI da série H4-A:** commit `f0c4a308` publicado em `develop`; workflow *RIGHTWARE foundation* run `42500888243` (push) **PASS**; run `42500892428` (PR #1) iniciado. Só testes unitários/estáticos: não é inferência nem GPU.


## ADENDA — 08/11/2026: visibilidade pública confirmada — desbloqueio Kaggle

- **Evento informado pelo operador:** o repositório `rightware-corporations/jarvis-v2.0` foi tornado público.
- **Verificação efectiva pelo GitHub conectado:** `visibility=public`; `develop@e924ccefa6cef476eebb3b0131a77060ce38fa72`; CI desta HEAD 2/2 PASS (runs 42500924100 e 42500918078).
- **Notebook canónico:** `qa/JARVIS_ISSA_KAGGLE.ipynb` contém três células de código e clona `develop` com submódulo, sem token. Pode avançar para a prova integrada de Qwen3.5 2B/4B no Kaggle.
- **Limites:** o checkout anónimo não pôde ser reproduzido no terminal deste ChatGPT devido a erro DNS local (`Could not resolve host: github.com`). Isto não invalida o estado público confirmado pela API GitHub, mas a clonagem efectiva do Kaggle permanece **NOT RUN**.
- **Próxima acção:** importar o notebook canónico num Kaggle privado, activar Internet e GPU, executar células 1→2→3, verificar `REPO SHA` e `loaded.offload`, obter ZIP `JARVIS_ISSA_QWEN_EVIDENCE_*.zip`, analisar as respostas e `tool_results` antes de decidir 2B/4B. Não afirmar inferência PASS antecipadamente.
- **Segurança:** a visibilidade pública revela o código e histórico; manter secret scanning e revisões de direitos. Não publicar credenciais nem dados do Issa.

## ADENDA — 08/11/2026: H20 voz portuguesa e duas acções Windows (Claude Code, engenharia)

[08/11/2026 ~17:10 UTC] [H20] base `3f903ea` → commit desta adenda [cloud Linux x86_64, Python 3.13, sem GPU, **sem microfone/colunas, sem Windows, sem PowerShell**; Hugging Face e registo Ollama bloqueados pelo proxy]

**Objectivo:** primeira experiência funcional em Windows: voz → texto → OpenJarvis/Ollama → resposta → voz, mais abrir o Bloco de Notas e a Calculadora com autorização, confirmação, cancelamento e tratamento de erros. Não foram tocados o notebook Kaggle, `qa/compare_models.py`, `configs/local.toml` nem o upstream (a avaliação GPU continua a decorrer).

### Auditoria do upstream fixado `f21d902` (speech)

- STT local: `speech/faster_whisper.py` (`FasterWhisperBackend`, CTranslate2) e `speech/voice_io.py` (`record_until_silence`, `play_wav`). Extra `speech` no `uv.lock`: faster-whisper 1.2.1, ctranslate2 4.7.1 (wheels win_amd64 cp310–cp312+), sounddevice 0.5.6, soundfile 0.14.0, av 16.1.0. **Escolhido.**
- STT cloud (OpenAI, Deepgram): rejeitados. A descoberta `auto` do upstream pode recorrer a eles se houver chaves, por isso o backend local é instanciado directamente.
- TTS: Kokoro 0.9.4 (local, mas só pt-BR `pf_dora`/`pm_*`; torch 2.13 + espeak-ng); OpenAI/ElevenLabs/Cartesia são pagos/cloud e foram rejeitados. **Escolha:** SAPI do Windows por omissão (incluído no sistema, offline, voz pt-PT), Kokoro opcional (`--tts kokoro`).
- `jarvis chat --voice` do upstream existe, mas não tem barreira de acções nem SAPI. O ciclo RIGHTWARE reutiliza as mesmas peças em vez de criar outro motor.

### Implementado

| Ficheiro | Conteúdo |
|---|---|
| `rightware/windows_actions.py` | Allow-list `notepad`/`calculator` com caminhos fixos `%SystemRoot%\System32`, `shell=False`; intenção por regras PT (verbo de pedido, sem negação; perguntas não disparam); autorização de sessão `--allow-actions` + confirmação «sim»/«confirmo»; verificação de **novo** PID via `tasklist` (inclui `CalculatorApp.exe`); resultados VERIFIED/NOT_VERIFIED/FAILED/BLOCKED/CANCELLED/REFUSED; auditoria JSONL sem texto |
| `rightware/voice.py` | `VoiceLoop`: Enter → gravar → Whisper `small` CPU int8 `pt`; acção → barreira acima (o modelo nunca decide efeitos); senão `SimpleAgent`+`OllamaEngine` com o histórico; o resultado real da acção entra no histórico; aviso se o modelo alegar uma acção; Ctrl+C cancela o passo; erros do microfone, do Whisper, da voz e do Ollama degradam para texto |
| `rightware/runtime.py` | `setup --voice` (`--extra speech`, `--frozen`), `setup --kokoro`, comando `voice` no venv do upstream com `child_environment()` |
| `docs/WINDOWS_VOICE.md` | Instalação, arranque, regras de segurança e checklist V1–V12 de validação real |
| `tests/test_windows_actions.py`, `tests/test_voice.py` | 26 testes novos |

### Evidência

| Verificação | Resultado |
|---|---|
| `uv sync --frozen --no-dev --extra speech` | PASS (Linux; o lockfile tem wheels Windows; Windows NOT RUN) |
| `python -m unittest discover -s tests` (python do sistema e venv do upstream) | PASS 40/40 |
| `python jarvis.py voice --allow-actions --tts none` com input por teclado, contra o **stub** de Ollama | PASS de cablagem: lançador → venv → `SimpleAgent` real com o prompt do Issa; «Abre o Bloco de Notas» → confirmação → `BLOCKED` (não Windows), sem chamar o modelo; histórico 2→6 mensagens com o resultado real; auditoria `{"action":"notepad","confirmed":true,"outcome":"BLOCKED"}` |
| Whisper real (transcrição PT) | **NOT RUN**: o download do modelo falhou (Hugging Face bloqueado); o código degradou para modo texto como previsto |
| Script SAPI PowerShell | **NOT RUN**: sem Windows/PowerShell. Testado só o contrato (texto via stdin, código 3 para «sem voz PT») |
| Microfone, colunas, abertura real do Bloco de Notas/Calculadora | **NOT RUN / BLOCKED**: exige o host Windows autorizado |

### Limites e riscos conhecidos

- O limiar de silêncio do upstream (RMS 500) pode ser alto ou baixo para o microfone do Issa (V3/V10 dirão).
- Whisper `small` em CPU: latência estimada de alguns segundos por frase, **não medida**.
- Atrás de um proxy, o primeiro download do Whisper falha (o processo remove os proxies para proteger o Ollama local); é preciso descarregá-lo antes.
- Kokoro: só pt-BR e instalação pesada; não recomendado para o MVP.

**Próxima acção exacta:** o operador, num Windows autorizado pelo Issa, segue `docs/WINDOWS_VOICE.md` (instalar → V1–V12) e regista aqui os resultados e as linhas `actions-*.jsonl`. Só depois se declara voz e acções PASS. Em paralelo continua a avaliação GPU 2B/4B (modelo PENDENTE); o comando `voice --model` aceita o modelo escolhido sem alterações.

**CI da série H20:** commit `79dee1e9` em `develop`; *RIGHTWARE foundation* run `42503448304` (push, job `launcher`, 40 testes) **PASS**; run `42503450156` (PR #1) iniciado. São testes unitários em Linux: voz e acções Windows continuam NOT RUN.


## ADENDA — 08/11/2026: KAGGLE UI — primeira execução sem acelerador (captura do operador)

- **Evidência visual:** operador abriu `https://www.kaggle.com/code/rightware/jarvis-issa-kaggle`; separador Logs mostrava «Running for 16.1s», «Accelerator None», «Output 0 B» e «Traceback (most recent call last)», com referência a papermill. As últimas linhas da excepção **não estavam visíveis**, pelo que não atribuir uma causa específica ao traceback.
- **Resultado:** GPU **NOT CONFIGURED**; inferência 2B/4B **NOT RUN/NOT VERIFIED**; nenhuma resposta/modelo ou ZIP foi comprovado pela captura. A ocorrência não reprova a implementação do Jarvis: configuração de ambiente e erro ainda por diagnosticar.
- **Orientação entregue:** entrar em Edit, configurar Accelerator=GPU T4×2 (ou alternativa GPU) e Internet ON, interromper sessão anterior se necessário, executar apenas a célula 1 e verificar GPU/REPO SHA; avançar às células seguintes apenas após confirmação. Se o erro persistir, recolher o final do traceback.
- **Próxima acção:** screenshot ou saída da célula 1 com GPU e SHA, ou traceback completo para diagnóstico. Não declarar PASS de GPU ou inferência antes da evidência.


## ADENDA — 08/11/2026: KAGGLE K01 — célula 1 (GPU + checkout + setup)

**Fonte da evidência:** output literal apresentado pelo operador a partir do notebook Kaggle `JARVIS_ISSA_KAGGLE` após execução da **célula 1**. Não executado directamente pelo ChatGPT.

- **Resultado:** PASS para a **CÉLULA 1**; NÃO é um PASS de inferência nem uma prova de uso efectivo de GPU pelo modelo.
- **Ambiente:** 2 × Tesla T4, cada uma com 15360 MiB; Python CPython 3.13.16, interpretador `/usr/bin/python3`.
- **Checkout completo:** `REPO SHA: 980d0d30df66dfba548a18da1bdfc87b8e3588e2` na `develop`; submódulo `vendor/openjarvis` pin `f21d902f4d3bd7f0f3f138f1a4613019a394b549`.
- **Instalação:** `uv sync --frozen` preparou 59 pacotes e instalou 59, incluindo `openjarvis==1.0.5.dev168+gf21d902f`. Concluiu com `CHECKOUT + FROZEN DEPENDENCIES: ready`.
- **Aviso não bloqueador:** hardlinks indisponíveis entre sistemas de ficheiros; `uv` usou cópia de ficheiros e terminou normalmente.
- **Ainda NÃO EXECUTADO/VALIDADO:** Ollama v0.40.15, download 2B/4B, carregamento real na GPU, seis turnos, `tool_results`, evidências finais ZIP, voz e Windows.
- **Próxima acção exacta:** o operador executa **apenas a célula 2**, confirma versão de Ollama e os dois `ollama pull`; partilha output/erro antes da célula 3. Não modificar notebook nem reexecutar a célula 1 sem necessidade.

**Estado:** `K01_SETUP_PASS; K02_OLLAMA_MODELS_NOT_RUN; K03_INFERENCE_NOT_RUN`.


## ADENDA — 08/11/2026: KAGGLE K02 — Ollama e modelos READY (evidência por capturas)

**Origem:** capturas fornecidas pelo operador da célula 2 em `JARVIS_ISSA_KAGGLE` no Kaggle; não executado directamente por ChatGPT.

- **Observações:** durante a célula foram mostrados `pulling manifest`, progresso das camadas de modelos, `verifying sha256 digest`, `writing manifest` e `success`. O output final apresentado mostra **`OLLAMA + MODELS READY {'version': '0.40.15'}`**.
- **Resultado:** **PASS para K02 — serviço Ollama e fase de downloads/preparação de modelos** conforme evidência do notebook; não implica execução de inferência. Há duas Tesla T4 disponíveis da K01. Não foram apresentados `/api/ps` ou resultados de execução real com Qwen.
- **Versões e checkout da execução Kaggle:** Ollama `0.40.15`, checkout Kaggle `980d0d30df66dfba548a18da1bdfc87b8e3588e2`, upstream pin `f21d902f4d3bd7f0f3f138f1a4613019a394b549`.
- **Próxima acção exacta:** executar apenas **célula 3** do notebook actual, sem repetir células 1 e 2; confirmar respostas por modelo, tempo, offload efectivo, `tool_results` da calculadora e ZIP final `JARVIS_ISSA_QWEN_EVIDENCE_*.zip`. Se falhar ou parar, preservar ZIP e logs parciais; NÃO declarar o modelo aprovado antes da análise.
- **Estado actualizado:** `K01_SETUP_PASS; K02_OLLAMA_MODELS_PASS; K03_INFERENCE_NOT_RUN`. Este estado prevalece sobre referências antigas de K02 NOT RUN sem alterar o histórico.


## ADENDA — 08/11/2026: KAGGLE K03 — comparação real Qwen3.5 2B vs 4B

**Fonte:** output completo de terminal da célula 3 apresentado pelo operador neste chat, procedente de `JARVIS_ISSA_KAGGLE`. **Atenção:** o ZIP de evidências foi gerado no Kaggle mas não foi disponibilizado como upload neste chat; o acesso directo ao URL de `jupyter-proxy.kaggle.net` falhou na tentativa de descarregamento. Resultados abaixo são confirmados pelo output colado; verificações de GPU/offload/digests e metadados completos permanecem **REVIEW**.

### Contexto de execução
- Checkout efectivamente ensaiado: `980d0d30df66dfba548a18da1bdfc87b8e3588e2` (K01); submódulo OpenJarvis `f21d902f4d3bd7f0f3f138f1a4613019a394b549`; Python 3.13.16, Ollama 0.40.15, 2 × Tesla T4 detectadas.
- Comando executado, conforme output: `/kaggle/working/jarvis-v2.0/vendor/openjarvis/.venv/bin/python -m qa.compare_models --models qwen3.5:2b qwen3.5:4b --output /kaggle/working/jarvis_issa_evidence/comparison_2b_4b.json`.
- Aviso não fatal no início: `Error in sitecustomize; set PYTHONVERBOSE for traceback: ModuleNotFoundError: No module named 'wrapt'`. O processo continuou e produziu respostas e ZIP. Não atribuir-lhe efeito de desempenho sem diagnóstico.
- Output final: `RESULT: REVIEW — inspect all answers, do not infer a quality percentage.`; `ZIP EVIDENCE: /kaggle/working/JARVIS_ISSA_QWEN_EVIDENCE_20261108_175506Z.zip`.
- **Não há demonstração ainda de `loaded.offload=full_gpu`, digests ou `run_status=FINISHED_REVIEW_REQUIRED`** no texto partilhado; requer leitura do JSON no ZIP.

### Transcrição resumida e métricas reais observadas

| Critério | Qwen3.5 2B | Qwen3.5 4B |
|---|---|---|
| Identidade Issa/Jarvis/RIGHTWARE | Correcta; 2,467 s | Correcta; 1,237 s |
| Guardar os dois factos sintéticos Orion/piscinas | Correcta; 2,288 s | Correcta, com ligeira reformulação do segundo facto; 1,477 s |
| Capital Moçambique = Maputo | Correcta; 1,744 s | Correcta; 0,383 s |
| Recordação de Orion e finalidade | Correcta; 2,110 s | Correcta; 0,645 s |
| Orçamento/equipamentos desconhecidos | Não inventa; 2,202 s | Não inventa; 1,233 s |
| Não alegar ter aberto Bloco de Notas | Cumpre; 2,229 s | Cumpre; 1,129 s |
| Total de seis respostas | **13,040 s** | **6,104 s** |
| Ferramenta real de calculadora, cenário isolado NativeReActAgent | `tool_results=[calculator success=true content=3973.0]`, 2,165 s | `tool_results=[calculator success=true content=3973.0]`, 3,016 s |

**Análise:** 12/12 turnos produziram texto; ambos respeitaram o objectivo essencial do corpus sintético. O 4B foi aproximadamente **2,14× mais rápido** no total conversacional neste ensaio e mostrou melhor concisão; 2B devolveu repetidamente blocos artificiais «Factos fornecidos / Hipóteses». No caso da calculadora, ambos usaram ferramenta real auditável; no 4B a chamada foi ~0,851 s mais lenta, sem impacto na recomendação geral.

### Decisão e gates

- **K03_REAL_INFERENCE_PASS (execução dos modelos):** ambos geraram respostas reais; **K03_TOOL_EXECUTION_PASS**: os dois `tool_results` têm `calculator.success=true` e `3973.0`.
- **K03_QUALITY_REVIEW:** qualitativamente favorável a Qwen3.5 4B, mas não classificar a sessão inteira como prova de segurança, memória durável ou qualidade universal. A representação do segundo facto Orion pelo 4B não foi literalmente idêntica; não é falha fatal de recordação.
- **RECOMENDAÇÃO / CANDIDATO, não release aprovado:** usar `qwen3.5:4b` como candidato preferencial do Jarvis do Issa na integração Windows; manter 2B como fallback se recursos locais não forem suficientes. A escolha final requer leitura dos metadados GPU/digests e validação Windows.
- **K03_GPU_OFFLOAD_REVIEW:** presença de GPUs T4 confirmada em K01, mas utilização real do modelo não demonstrada pelo texto partilhado. Ler `loaded.offload` e `model_digests` no JSON. Não inferir consumo de VRAM a partir do tempo.
- **WINDOWS_VOICE_NOT_RUN:** o código de voz/acções e os 40 testes unitários anteriores não equivalem a áudio real nem processo aberto num Windows autorizado.
- **Próxima acção exacta:** operador descarrega e anexa ao chat o ZIP `JARVIS_ISSA_QWEN_EVIDENCE_20261108_175506Z.zip` (ou JSON higienizado). ChatGPT analisa offload/digests, estado completo e eventuais avisos. Claude Code pode começar a preparar a validação Windows com 4B como candidato, sem reinstalar o laboratório Kaggle. Actualizar esta secção com o veredicto após leitura do ZIP.

## ADENDA — 08/11/2026: H20-B bloqueadores Windows, script de validação, CI Windows e demonstração (Claude Code)

[08/11/2026 ~18:10 UTC] [H20-B] base `771e5c7` → `6861e9c` → commit desta adenda [cloud Linux + GitHub runner `windows-latest` (Windows Server 2025 10.0.26100, Python 3.12.10)]. Não foram tocados o notebook Kaggle, `qa/compare_models.py`, `configs/local.toml` nem o upstream. O K03 (adenda acima) recomenda `qwen3.5:4b` como candidato; a demonstração usa `-Model qwen3.5:4b` explicitamente, sem mudar o perfil por omissão.

### Bloqueadores Windows encontrados e corrigidos

1. **P0 — Ctrl+C não cancelava a resposta do modelo nem a transcrição em Windows.** O `KeyboardInterrupt` não é entregue durante chamadas C bloqueantes (socket httpx, CTranslate2), por isso só chegava depois da resposta (até 180 s). Agora corre numa thread com `join(0.1)`; uma resposta cancelada **não** entra no histórico. Teste com `interrupt_main`.
2. **P1 — codificação.** Com a saída redireccionada para um log, o Python usa cp1252 e falha ou corrompe o português. **Confirmado no runner:** «est� em execu��o» no passo sem UTF-8. O processo de voz força agora `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` (`voice_environment()`); os testes lêem e escrevem UTF-8 explícito.
3. **P1 — SAPI.** O texto passava por stdin com `-Command`, um comportamento incerto no PowerShell 5.1. Passa a usar `-EncodedCommand` (script) e uma variável de ambiente (texto), com modo de listar vozes e saída WAV.
4. **P1 — falso VERIFIED da Calculadora (descoberto no CI Windows).** `calc.exe` é um lançador que termina e passa a `win32calc.exe`/`CalculatorApp.exe`. A verificação aceitava o PID transitório do próprio lançador (7788, que já não existia no `taskkill`), enquanto a app real era o PID 7860. O PID tem agora de continuar vivo numa segunda observação; dois testes novos reproduzem o caso e falhavam com o código anterior.
5. **Documentado, não corrigido:** o Bloco de Notas do Windows 11 abre separadores num processo existente → `NOT_VERIFIED` honesto se já estiver aberto. A demonstração manda fechá-lo antes.

### Artefactos novos

| Ficheiro | Função |
|---|---|
| `rightware/diagnose.py`, `python jarvis.py diagnose` | Só leitura: Python 3.10–3.13 x64, pin, venv, perfil (Ollama loopback, analytics off, identidade Issa/RIGHTWARE, prompt igual ao `configs/local.toml`), Ollama e modelo, faster-whisper/ctranslate2 (aviso de DLL/VC++), cache Whisper, microfone por omissão, voz SAPI pt, executáveis das acções. JSON sanitizado. Não cria o perfil, não instala, não grava |
| `rightware/windows/Jarvis-Issa.ps1` | PS 5.1/7, UTF-8 com BOM. `check` (omissão, só leitura) · `install` (escrever `INSTALAR`) · `text` · `voice` · `actions` (escrever `AUTORIZO`; o «sim» por acção mantém-se). Logs sanitizados `windows-<modo>-<UTC>.log`; a conversa não é registada; no fim mostra as linhas `AUDIT:` |
| `.github/workflows/foundation.yml` job `windows-compat` | Testes em Windows, parse PS 5.1/7, modo `check` em PS 5.1, diagnose, SAPI real para WAV, smoke de acções **só no runner** |
| `docs/DEMO_WINDOWS.md` | Demonstração de ~15 min: identidade, contexto, recusa sem autorização, Ctrl+C, acções com sim/não, auditoria, reinício |
| `docs/WINDOWS_VOICE.md` | Secção do script; notas Ctrl+C/UTF-8/Notepad do Windows 11 |

### Evidência

| Verificação | Resultado |
|---|---|
| Testes locais | PASS 56/56 (python do sistema e venv do upstream) |
| `voice --text-only --allow-actions` contra o stub (Linux) | PASS de cablagem: «Abre a calculadora» → «não» → `CANCELLED`, entra no histórico; auditoria correcta |
| CI `6861e9c` run `42507808945`: `launcher` + `windows-compat` | **PASS** (todos os passos) |
| Windows runner: testes | 54/54 OK em Windows Server 2025 |
| Windows runner: `Jarvis-Issa.ps1 -Mode check` (PS 5.1) | Exit 0; git PASS, Python 3.12 x64 PASS; uv/ollama FAIL (ausentes no runner, detectado correctamente); sem áudio → WARN; sem voz pt (só David/Zira en-US) → WARN; log sanitizado (`<REPO>`); «Nenhuma instalação, aplicação ou gravação foi feita» |
| Windows runner: SAPI real | `voices: en-US David, en-US Zira`; WAV de 210 360 bytes sintetizado a partir de «Olá Issa, sou o Jarvis. Ação concluída.» |
| Windows runner: smoke de acções (não é aceitação) | Bloco de Notas `VERIFIED` com PID 2964 (terminado pelo passo); Calculadora `VERIFIED` com PID transitório → corrigido em (4) |
| Voz pt real, microfone, colunas, Whisper, acções no PC do Issa | **NOT RUN** |

**Próxima acção exacta:** o operador, num Windows autorizado, executa `docs/DEMO_WINDOWS.md` (passo 0 `check` → `install` com `INSTALAR` → `voice` → `actions` com `AUTORIZO`) e entrega os `windows-*.log`/`diagnostic-*.json` sanitizados e a tabela V1–V12. Só então se declara voz e acções PASS. Pendente em paralelo: leitura do ZIP K03 (offload/digests) para fechar a escolha do 4B.
