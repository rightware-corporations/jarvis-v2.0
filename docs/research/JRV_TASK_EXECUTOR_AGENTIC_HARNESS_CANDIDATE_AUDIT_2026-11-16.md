# JRV-TE-001 — Auditoria de candidatos a Task Execution Agent + Harness

**Data:** 2026-11-16  
**Estado:** INVESTIGACAO READ-ONLY / RECOMENDACAO; nenhuma tecnologia externa aprovada ou integrada.  
**Organizacao:** RIGHTWARE  
**Objectivo:** seleccionar um agente autonomo open source reutilizavel **como modulo novo** do RIGHTWARE JARVIS v2.0, sem retirar OpenJarvis, reconstruir componentes existentes, ou permitir execucao de ferramentas fora do controlo RIGHTWARE.

## 1. Pergunta que esta investigacao responde

A lacuna prioritária nao e simplesmente obter outro modelo conversacional. O utilizador quer que JARVIS receba um objectivo, o transforme em passos, execute com ferramentas autorizadas, observe resultados, recupere de falhas quando possivel e **entregue a tarefa com evidencia**. O Agentic Harness e o controlo de lifecycle, tool boundary, estado, limites e verificacao que deve envolver o agente executor. Importar um agente nao prova por si so a entrega correta.

O handoff externo de 2026-11-14 (RIGHTWARE_JARVIS_V2_AGENTIC_HARNESS_HANDOFF.md, fornecido pelo operador nesta conversa) declara a arquitectura hipotetica e exige AUDIT -> DESIGN -> IMPLEMENTATION. Este relatorio e apenas AUDIT, mais uma proposta de prova minima; nao constitui aceitacao ou autorizacao para executar um agente externo.

## 2. Baseline JARVIS verificado

- Repositorio: `rightware-corporations/jarvis-v2.0`; `develop@fa36b3896de2408c9c98a80d6618469ef7099547`.
- Opt-in D01/D02 em Draft PR #11, `feat/wp04-d01d02-text-facade@bb6a95ec214448c8ff087aca709624b4e67c69f0`; **nao integrado** em develop. PR #1 de release permanece Draft.
- `rightware/agent/session.py`: `AgentSession` usa o pinned `OpenJarvis.OrchestratorAgent`, ferramentas com tipos/budgets e `_GuardedEngine`, web_public/browse e WindowsActions limitadas.
- `rightware/agent/policy.py`: `AgentPolicy` valida nome, argumentos, capabilities, quotas, deadline, cancelamento e sequencias de repeticao; politica de execucao e condicao obrigatoria.
- `rightware/agent/task_contract.py`: A1 tem catalogo de contratos **apenas browser read-only**, por opt-in; nao e parser de objectivos gerais.
- `rightware/agent/receipts.py`: A2 liga decisao/dispatch/execucao com recibos estruturados por tentativa; o upstream pode deixar um worker vivo depois de timeout.
- `rightware/agent/completion.py`: A3 trata conclusao operacional por contratos, tambem com scope limitado; nunca demonstra verdade factual geral.
- `rightware/agent/cli.py`: CLI `agent` tem um percurso separado e flags opt-in; `rightware/voice.py` possui fluxo proprio.
- `rightware/text_facade.py` + `text_adapter.py` (PR #11): D01/D02 disponibilizam sessao/pedido/resposta de texto em RAM, sem ferramentas ou memoria persistente. Bloqueiam reivindicacoes de efeitos. Nao existe ponte D03 nem Task Executor integrado.
- `vendor/openjarvis` continua fixado em `f21d902f4d3bd7f0f3f138f1a4613019a394b549`. Nao alterar gitlink/pin para esta investigacao.

**Conclusao de gap:** falta a ponte confiavel D01/D02 -> task contract de objectivos -> executor agentico -> RIGHTWARE policy/tool receipts -> completion gate -> resultado JARVIS. O executante externo nao pode assumir autoridade para grants nem inventar `completed`.

## 3. Candidatos e evidencias

Todos os projectos foram inspeccionados **em GitHub, sem instalacao e sem executar modelos**. O nivel de evidencia e CODIGO quando existe leitura dos ficheiros indicados, DOCS quando depende da documentacao oficial e NAO TESTADO para comportamento de runtime real.

### A. goose (Agentic AI Foundation)

- Repo: https://github.com/aaif-goose/goose
- Revisao observada: `bf6e1df335a3e0ace08afb4a4c913b94356010ee` (main no momento da consulta).
- Licenca principal: Apache-2.0, ficheiro LICENSE confirmado; licencas de dependencias e empacotamento ainda por auditar.
- **CODIGO:** `crates/goose-agent/src/machine.rs` define `StateMachine`, `step`, `run`, `CancellationToken` e fases `Operation` / `Inference`, com persistencia de efeitos delegada a `EffectHandler`.
- **CODIGO:** `crates/goose-agent/src/tool_approval.rs` define `ToolApproval.check` e `Allow / Deny / Ask`.
- **CODIGO:** `crates/goose-agent/src/max_turns.rs` fixa o budget de turnos autonomos.
- **DOCS:** desktop/CLI/API, Ollama, MCP; `goose run` permite modo nao interactivo; `goose serve` disponibiliza servidor ACP, com secret key documentada e extensoes builtin configuraveis.
- **RISCOS:** Rust e Python nao partilham API in-process simples; o caminho mais claro seria processo sidecar/ACP. Tem de se demonstrar que TODAS as ferramentas reais podem passar por uma unica fronteira RIGHTWARE e que extensoes builtin de execucao arbitraria ficam efectivamente desactivadas. Tool-calling dos Qwen 2B/4B nao foi validado.
- **APTIDAO:** primeiro candidato para prova de conceito de orquestracao isolada, nao candidato aprovado para importar integralmente.

Fontes de codigo:
- https://github.com/aaif-goose/goose/blob/bf6e1df335a3e0ace08afb4a4c913b94356010ee/crates/goose-agent/src/machine.rs
- https://github.com/aaif-goose/goose/blob/bf6e1df335a3e0ace08afb4a4c913b94356010ee/crates/goose-agent/src/tool_approval.rs
- https://github.com/aaif-goose/goose/blob/bf6e1df335a3e0ace08afb4a4c913b94356010ee/crates/goose-agent/src/max_turns.rs
- https://goose-docs.ai/docs/guides/running-tasks/
- https://goose-docs.ai/docs/guides/goose-cli-commands/

### B. Agent Zero

- Repo: https://github.com/agent0ai/agent-zero
- Revisao observada: `ba9b67df0f54ac78106ae85c552ef5d2458f7c9a`.
- Licenca principal: MIT confirmada em LICENSE.
- **CODIGO:** `agent.py` fornece `AgentContext`, `Agent`, `_process_chain`, `process_llm_result_tools` e `_execute_tool_request` com despacho de ferramentas e hooks. `tools/call_subordinate.py` implementa delegacao e binding pai/filho.
- **DOCS:** agente autonomo com browser, terminal e ambiente Linux; instalacao habitual com Docker; modelos locais via Ollama e LM Studio.
- **RISCOS:** o ambiente de execucao e mais largo que a primeira necessidade do JARVIS. O modelo usa ferramentas proprias, extensoes e plugins; sem isolamento e proxy o gate RIGHTWARE e contornavel. Docker->Ollama no anfitriao envolve configuracao de rede e exposicao cautelosa.
- **APTIDAO:** segundo candidato, especialmente para automacao complexa em workspace isolado; menos conveniente como biblioteca simples dentro do runtime Python existente.

Fontes:
- https://github.com/agent0ai/agent-zero/blob/ba9b67df0f54ac78106ae85c552ef5d2458f7c9a/agent.py
- https://github.com/agent0ai/agent-zero/blob/ba9b67df0f54ac78106ae85c552ef5d2458f7c9a/tools/call_subordinate.py
- https://www.agent-zero.ai/p/docs/installation/

### C. Hermes Agent (Nous Research)

- Repo: https://github.com/NousResearch/hermes-agent
- Revisao observada: `f65af53f28ebec14c89b7ae603c701cff5faf6f0`.
- Licenca principal: MIT confirmada em LICENSE.
- **CODIGO:** `agent/conversation_loop.py` implementa etapas de turno e despacho; `agent/turn_tool_round.py` grava o turno de ferramenta no armazenamento de sessao antes da execucao e falha fechado quando a persistencia falha; `agent/iteration_budget.py` fornece limite de iteracoes.
- **DOCS:** utilizacao de modelos locais via endpoint Ollama compatível, ferramentas, sessoes e Windows nativo.
- **RISCOS:** grande superficie de Python/estado/persistencia propria e dependencias; a politica de seguranca do proprio projecto adverte que aprovacoes in-process nao sao isolamento de SO. Nao presumir que o loop e importavel como uma pequena biblioteca independente do resto do runtime.
- **APTIDAO:** terceiro candidato; forte fonte de referencia para durabilidade, mas risco de duplicacao de estado/memoria e alta complexidade de extraccao.

Fontes:
- https://github.com/NousResearch/hermes-agent/blob/f65af53f28ebec14c89b7ae603c701cff5faf6f0/agent/conversation_loop.py
- https://github.com/NousResearch/hermes-agent/blob/f65af53f28ebec14c89b7ae603c701cff5faf6f0/agent/turn_tool_round.py
- https://github.com/NousResearch/hermes-agent/blob/f65af53f28ebec14c89b7ae603c701cff5faf6f0/agent/iteration_budget.py
- https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md

## 4. Matriz de seleccao preliminar

| Criterio | goose | Agent Zero | Hermes |
|---|---|---|---|
| Ciclo agentico identificado no codigo | SIM | SIM | SIM |
| Modelo local documentado | SIM | SIM | SIM |
| Controlo de turnos/iteracoes identificado | SIM | REVER | SIM |
| Aprovacoes ou fronteiras de tool detectadas | SIM | Hooks; politica a auditar | SIM; isolacao SO exige configuracao |
| Integracao com JARVIS Python | Sidecar/ACP proposto | Container/servico proposto | Adaptador Python/processo proposto |
| Registo/recovery operacional demonstrado | PARCIAL/NAO TESTADO | NAO TESTADO | Persist-before-execute no codigo; recovery end-to-end NAO TESTADO |
| Compatibilidade real Qwen3.5 2B/4B (4096 contexto) | NAO TESTADO | NAO TESTADO | NAO TESTADO |
| Tool effects sempre atraves de RIGHTWARE AgentPolicy | NAO PROVADO | NAO PROVADO | NAO PROVADO |
| Licenca principal | Apache-2.0 | MIT | MIT |

**Seleccao:** goose e CANDIDATO PREFERENCIAL PARA INVESTIGAR a fronteira sidecar/controlada, e nao tecnologia aprovada. Agent Zero e contingencia para workspace autonomo em sandbox. Hermes fornece referencias de persistencia e recovery. Nao ha vencedor validado ate demonstrar o controlo total de efeitos no ponto de integracao.

## 5. Arquitectura de integracao proposta — sem implementacao autorizada

```text
Text / Voice / future UI
       |
RIGHTWARE trusted request/identity facade (D01; D02 remains tool-free)
       |
Trusted Task Contract / objective IDs (new, NOT the browser-only A1 catalog)
       |
RIGHTWARE Harness Controller
  - task lifecycle / budgets / cancellations / approval ledger
  - delegates reasoning to external ExecutorAdapter
  - rejects tool grants embedded in LLM text
       |
ExecutorAdapter (goose sidecar candidate, sandboxed)
       |
  [NO DIRECT OS/NETWORK/FS tools]
       |
RIGHTWARE Tool Gateway
  -> AgentPolicy (authorization, arguments, capability, quota)
  -> constrained tool implementations (first: synthetic read-only fixture)
  -> ExecutionReceipt (call/run provenance)
  -> Completion Evaluator (per objective, not model self-report)
       |
Typed TaskResult -> JARVIS reply
```

Necessidades invariantes:
1. As permissoes nascem no host RIGHTWARE, nunca em prompt, LLM ou metadata de projecto externo.
2. O executor so deve ver as ferramentas de uma interface restrita; nenhuma ferramenta builtin pode contornar o Tool Gateway.
3. Um `TaskResult.completed` exige correlacao verificavel de objectivos obrigatorios com receipts efectivamente executados. `answer_factually_verified` continua false sem verificador separado.
4. Conclusao, erro, cancelamento, timeout, operacao desconhecida e aprovacao pendente sao estados distintos.
5. Nunca repetir uma operacao consequencial depois de timeout/restart sem reconciliar o seu estado real.
6. Persistencia de memoria, logs detalhados e acesso a dados privados estao fora do primeiro MVP.
7. OpenJarvis e o motor local Ollama permanecem no produto; o executor novo nao passa a ser a identidade publica do Jarvis.

## 6. Primeira prova de conceito recomendada — apenas depois de autorizacao separada

**TE-P0** — fluxo de entrega verificavel sem efeitos no sistema real:
- Uma tarefa com **dois objectivos predefinidos pelo host**: inspecionar duas fixtures sinteticas independentes e reportar o que cada uma contem.
- Executor em processo isolado, no primeiro ensaio com modelo FAKE controlado, apenas um tool proxy `fixture_read(id)` que nao pode aceder a ficheiros arbitrarios nem rede.
- Simular resultados reais da ferramenta, recusas, 404/ausencia, atrasos, falhas e respostas maliciosas.
- Verificar que duas receipts distintas e validas sao obrigatorias; um resumo convincente ou uma unica leitura nunca passam a COMPLETE.
- Nenhuma operacao de escrita, shell, browser publico, WindowsAction, credenciais ou APIs pagas.
- Depois de fake suite aprovada e autorizacao adicional: experimentar Ollama real com Qwen3.5 2B e 4B sob exactamente o mesmo corpus, medindo chamadas validas de ferramentas, completude por objectivos, latencia, RAM/VRAM e falhas. **Nao realizado.**

Falsificacao / criterios de paragem:
- Se goose mantiver qualquer ferramenta capaz de escapar ao proxy, REJEITAR a integracao actual, nao esconder a brecha com prompts.
- Se nao houver identidade/correlacao de execucao confiavel, nao declarar COMPLETE.
- Se Qwen2B/4B nao tiverem comportamento de tool-calling suficiente, rever modelo/estrategia; nao culpar automaticamente o Harness.
- Se a complexidade de embutir goose ultrapassar os ganhos, reavaliar Agent Zero/Hermes ou executar um loop proprio minimo com componentes ja existentes.

## 7. Riscos e trade-offs

- **Runtime misto:** Rust sidecar acrescenta empacotamento, lifecycle, actualizacoes e monitorizacao ao JARVIS Python.
- **Autoridade duplicada:** politicas/approval internas dos candidatos nao substituem AgentPolicy; confirmar negacao em ambos os caminhos.
- **Sessao versus tarefa:** D01/D02 so guarda contexto em RAM; contratos, checkpoints e task ledger sao outro dominio.
- **Tamanho do modelo:** suporte anunciado a Ollama nao certifica tool calling no Qwen3.5 2B/4B, com `num_ctx=4096`.
- **Durabilidade:** persist-before-execute nao impede execucao dupla apos timeout; reconciliation/idempotency continua obrigatoria.
- **Licenca e supply chain:** verificados os ficheiros de licenca principais, nao transitive licenses, vulnerabilidades nem binarios instalados.
- **Evidencia:** auditoria estatica nao prova eficacia, seguranca runtime, desempenho, Windows, voz ou privacidade.

## 8. Estado, proxima decisao e ligacoes

**OFICIAL:** manter OpenJarvis/Ollama local e garantias RIGHTWARE. `develop` e referencia de produto.  
**CANDIDATO:** investigar goose como modulo ExecutorAdapter; Agent Zero/Hermes como alternativas, nao aprovar instalacao ainda.  
**NAO FEITO:** nenhum clone de candidatos, dependencia instalada, agent tool executed, teste local Windows, Qwen live, alteracao de runtime/vendor ou merge.

**Proxima accao:** emitir missao read-only de desenho do `ExecutorAdapter` / Tool Gateway e plano TE-P0 com teste de impossibilidade de bypass; solicitar autorizacao delimitada para prototipo antes de instalar goose ou alterar `rightware/`.

Fontes RIGHTWARE:
- https://github.com/rightware-corporations/jarvis-v2.0/blob/develop/rightware/agent/session.py
- https://github.com/rightware-corporations/jarvis-v2.0/blob/develop/rightware/agent/policy.py
- https://github.com/rightware-corporations/jarvis-v2.0/blob/develop/rightware/agent/task_contract.py
- https://github.com/rightware-corporations/jarvis-v2.0/pull/11
