# F00 — Fundação de inteligência operacional do RIGHTWARE JARVIS

Estado: **DOCUMENTAL**. Não implementa motores, não altera código de produto e não executa avaliações. Data: 24/11/2026. Ramo: PR #32 (WEB-01, Draft).

Classificação usada em todo o documento:
- **[APROVADO]**: decisão do operador já registada no HANDOFF ou no `ARCHITECTURE.md`.
- **[FACTO]**: verificado no código ou em evidência deste repositório.
- **[RECOMENDAÇÃO]**: proposta que ainda exige aprovação.
- **[HIPÓTESE]**: por investigar (F01).

Directiva permanente **[APROVADO]**: *A inteligência decide. A política controla. As ferramentas executam. A evidência confirma.*

## 1. Fontes reconciliadas
- `docs/HANDOFF.md`, até ao checkpoint W3.2-R `5604b19`;
- `docs/ARCHITECTURE.md`, incluindo a directiva de 24/11;
- `docs/research/ARCHITECTURE_AGENT_INTELLIGENCE_BRIEF.md` (09/11);
- `docs/product-blueprint/JRV-004_SYSTEM_ARCHITECTURE.md`;
- `docs/engineering/{P1_CONTROL_PLANE, P2_GOOSE_INTEGRATION, P3A_GATEWAY_PRODUCT, UI01_*, UI02_HUD, WEB01_*, B6_TUNNEL_PROCEDURE}.md`;
- `docs/research/{WORK01..WORK07*, JRV_TASK_EXECUTOR_AGENTIC_HARNESS_CANDIDATE_AUDIT_2026-11-16, RIGHTWARE_AGENT_REUSE_RADAR_20261111}.md`;
- código em `rightware/`;
- o upstream fixado `vendor/openjarvis@f21d902`;
- a decisão de produto **JRV-PRODUCT-DIRECTION-UI-REUSE** de 23/11 [APROVADO]: reutilizar o OpenJarvis (GUI, agentes, ferramentas, memória) **através** dos gates RIGHTWARE, sem orquestradores, políticas ou mecanismos de sucesso paralelos.

> Nota: neste repositório não existe nenhum documento próprio sobre "Hermes". O radar de reutilização (`RIGHTWARE_AGENT_REUSE_RADAR_20261111.md`) e a auditoria de harnesses de 16/11 são a referência para candidatos externos. **[FACTO]**

## 2. Inventário: o que existe, e em que estado
Legenda: **INTEGRADO** (no produto, por um percurso testado), **EXPERIMENTAL** (num ramo ou com evidência limitada), **UPSTREAM** (no pin, mas não activado pela RIGHTWARE), **PLANEADO**.

| Componente | Onde | Estado | Evidência / limites |
|---|---|---|---|
| Ollama + Qwen 3.5 2B/4B (local, loopback) | `rightware/runtime.py`, `configs/local.toml` | INTEGRADO | Usado em todos os percursos reais. O 2B é o padrão; o 4B é usado no goose. CPU-only neste host. |
| Conversa (SimpleAgent, sem ferramentas, contexto de sessão) | `text_adapter.py` → `text_facade.py` → GUI `bridge.py` | INTEGRADO | E0-02 com Qwen real; UI-02 U3 e conversa multi-turno PT/EN (B6, 24/11). Sem memória persistente. |
| GUI OpenJarvis + HUD RIGHTWARE | `rightware/gui/*`, overlay sobre o frontend do pin | INTEGRADO (UI-01 merged), UI-02 em PR #31 Draft | E2E real U1–U7. HUD derivada de `/v1/rightware/state`. |
| Acesso privado B6 | `rightware/gui/{auth,policy,server}.py` | EXPERIMENTAL (ramo B6 `66be4c9`) | Smoke em loopback e janela real de 23/11. Versão da apresentação. |
| ControlPlane (capacidade activada pelo anfitrião + código de uso único + estados) | `control_plane.py`, `task_entry.py` | INTEGRADO | P1 (missão de comparação verificada); P2 (goose). |
| AgentSession (OpenJarvis **OrchestratorAgent** + `AgentPolicy` + recibos + avaliação de conclusão) | `rightware/agent/session.py` | INTEGRADO como motor de tarefas (TE-02…TE-06A, CLI) | Ferramentas: `web_read`, `web_open/type/submit/follow`, `windows_action`. TE-03/TE-04: o Qwen real usou as ferramentas, mas a tarefa pública ficou HALTED (2B e 4B). **Não está ligado ao chat da GUI.** |
| goose supervisionado (Docker isolado, só MCP do Gateway) | `goose_adapter.py`, `rightware/gateway/*` | INTEGRADO (P2/P3A merged), só fixture sintética | Uma missão real verificada pela GUI (UI-02 §4). Internet pública não validada. |
| Tool Gateway (AgentPolicy + ReceiptLedger + verificador + model_tap) | `rightware/gateway/*` | INTEGRADO (P3A) | Imagem reproduzível; isolamento verificado por sonda. |
| WEB-01 (egress, pesquisa livre, evidência) | `rightware/web01/*` | EXPERIMENTAL (PR #32 Draft) | W3 real (OP-W3, consumida). W3.2-R: S1 6/9, H 5/10, 3 associações erradas. **Não está pronto para produção.** |
| Voz (Whisper + SAPI/Kokoro) | `rightware/voice.py` | EXPERIMENTAL | Sem aceitação em hardware Windows real. HUD mostra "não integrada". |
| Acções Windows (Notepad e Calculadora por regras, PID verificado) | `windows_actions.py`, `rightware/windows/` | EXPERIMENTAL | Regras determinísticas, não um catálogo escolhido pelo modelo. Companion por fazer. |
| Agentes upstream `native_react`, `orchestrator`, `operative`, `monitor_operative`, `deep_research`, `native_openhands`, `research_loop` | `vendor/.../agents/` | UPSTREAM (o `orchestrator` é usado pela AgentSession) | `native_react` + Calculator num ensaio Kaggle (K03). `operative` (sessões persistentes, scheduler) não está activado. |
| Ferramentas upstream: `file_read/write`, `code_interpreter(_docker)`, `shell_exec`, `docker_shell_exec`, `browser(_axtree)`, `web_search`, `http_request`, `db_query`, `pdf_tool`, `knowledge_*`, `retrieval`, `memory_manage`, `calculator`, `think`, `mcp_adapter`, `git_tool`, `apply_patch`… | `vendor/.../tools/` | UPSTREAM | Nenhuma está activada no produto fora da AgentSession e do Gateway. Várias são de alto risco (shell, git, apply_patch). |
| Tool calling nativo do Ollama | `vendor/.../engine/ollama.py` (envia `tools`; se receber 400, repete sem elas) | UPSTREAM | Não foi medido com o Qwen 3.5 neste produto. **[HIPÓTESE]** para F01. |
| Memória persistente / RAG (LocalFactStore JSONL, SQLite+FTS5, extensão Rust) | `vendor/.../memory`, `tools/storage` | UPSTREAM | `context_from_memory=false`. O scanner de injecção tinha um fail-open identificado (brief de 09/11). |
| SIC (rightware-shared-intelligence) | repositório separado | EXPERIMENTAL, sem integração | Gates IAM/G04 e consentimento por resolver. |

**Conclusão do inventário [FACTO]:**
- O JARVIS já tem as **peças de governação**: ControlPlane, Gateway, AgentPolicy, recibos, verificadores e o EgressGuard WEB-01.
- Já tem **dois executores com ferramentas**: a AgentSession (Orchestrator) e o goose.
- A **conversa visível na GUI é ainda um SimpleAgent sem ferramentas**. As capacidades operacionais existem como **missões activadas pelo anfitrião**, não como ferramentas que o modelo escolhe durante a conversa. Esta é a lacuna principal entre o estado actual e o objectivo da directiva.

## 3. Arquitectura-alvo (lógica) [RECOMENDAÇÃO]

```text
A. INTERFACE UNIFICADA  — Chat · Voz · HUD · Operations Centre (mesma GUI OpenJarvis + overlay RIGHTWARE)
        │  pedidos, aprovações, cancelamento                       ▲ eventos reais (runtime, recibos)
        ▼                                                          │
B. INTELLIGENCE CORE   — modelo (Qwen local, substituível) + system prompt + Agent Runtime
        │                gestão de contexto, memória conversacional, selecção de ferramentas,
        │                planeamento/adaptação. O modelo RESPONDE DIRECTAMENTE quando o
        │                conhecimento interno chega; caso contrário PROPÕE ferramentas.
        ▼  proposta de chamada (nome + argumentos)
D. GOVERNAÇÃO RIGHTWARE — ControlPlane (capacidades, códigos, estados) · Gateway/AgentPolicy (por chamada)
        │                 · EgressGuard · orçamentos · cancelamento · recibos · VERIFICADOR independente
        ▼  só chamadas autorizadas
C. OPERATIONAL RUNTIME — workspace isolado (contentor), terminal/Python em sandbox, ficheiros no workspace,
        │                browser, documentos, BD, APIs, pesquisa (WEB-01), companion Windows (futuro)
        ▼  resultados + recibos
E. CONHECIMENTO        — contexto de sessão · RAG sobre documentos autorizados · memória persistente
                         consentida · SIC (futuro, read-only primeiro)
```

**Responsabilidades (não se sobrepõem):**

| Camada | Decide | Nunca faz |
|---|---|---|
| B (modelo + runtime) | Interpreta o pedido, responde ou escolhe a ferramenta, adapta o plano, sintetiza | Autorizar-se a si próprio; declarar sucesso; ver credenciais |
| D (governação) | Permite ou recusa cada chamada (capacidade, argumentos, risco, orçamento); exige confirmação; regista recibos; o verificador decide o estado final | Escolher a estratégia por tema; responder por regras ao utilizador |
| C (runtime) | Executa exactamente a chamada autorizada, no espaço isolado | Executar fora do workspace ou da allowlist; operar sem recibo |
| A (interface) | Mostra estados, eventos e recibos reais; recolhe aprovações | Mostrar actividade simulada; expor raciocínio privado ou segredos |
| E (conhecimento) | Fornece contexto recuperado com proveniência | Gravar memória sem consentimento; tratar texto recuperado como instrução |

**Princípios:**
1. **Ferramentas seleccionáveis, não pipelines obrigatórios.** Pesquisa externa, RAG, cálculo, programação e execução são ferramentas. Uma pergunta simples pode ser respondida directamente pelo modelo, marcada como "NÃO verificada", como hoje.
2. **WEB-01** fica como **ferramenta especializada de investigação com fundamentação**, chamada quando o modelo decide que precisa de fontes. **Não está pronta para produção** (ver W3.2-R).
3. **Um só caminho de autorização:** qualquer executor (Orchestrator, tool calling nativo, goose) passa pelo Gateway, pela AgentPolicy e pelo ControlPlane. É a decisão de 23/11 [APROVADO].
4. **Workspace isolado por omissão** para terminal, Python e ficheiros: contentor sem rede, salvo egress autorizado, com montagem só do workspace da tarefa. O padrão já existe no goose/P2. O shell genérico continua proibido [APROVADO, AGENTS.md].
5. **O resultado vem da evidência:** recibos e verificadores. O texto do modelo é sempre comentário NÃO verificado.

## 4. Reavaliação dos motores de inteligência (sem escolha definitiva)

| Candidato | O que já dá | Lacunas e riscos | Encaixe |
|---|---|---|---|
| **OpenJarvis Orchestrator** (via AgentSession) | Ciclo multi-turno com ferramentas; já protegido por AgentPolicy, recibos e avaliação de conclusão; CI e CLI | Prompt de ferramentas em texto; Qwen 2B/4B ficaram HALTED na tarefa pública (TE-03/04); não está ligado à GUI | Candidato natural para o **Intelligence Core no chat**, porque reutiliza o que já está auditado |
| **NativeReAct** | Ciclo acção/observação simples; calculadora real em K03 | Sem multi-ferramenta validado; menos hooks de governação | Linha de base de comparação |
| **Operative / monitor_operative** | Sessões persistentes, scheduler, tarefas recorrentes | Estado persistente: exige memória consentida; não activado | Futuro (automação), depois de E |
| **goose** (via Gateway) | Executor maduro, MCP, isolamento verificado em Docker, missão real verificada | Arranque pesado (contentores); latência; só fixture | **Executor de tarefas longas e isoladas**, não para conversa |
| **Tool calling nativo do Ollama** | Chamadas estruturadas sem parsing de texto; o `engine/ollama.py` já as suporta | Fiabilidade com o Qwen 3.5 2B/4B não medida; dependência da versão do Ollama | [HIPÓTESE] pode melhorar a selecção de ferramentas; a medir em F01 |
| **WEB-01** | Fundamentação estrita, unidades, atribuição, contradições | Recall baixo; 3 associações erradas; latência ~48 s | **Ferramenta** de investigação, não motor geral |

[RECOMENDAÇÃO] Arquitectura em duas velocidades:
- um **Intelligence Core conversacional**: Orchestrator ou tool calling nativo, a decidir em F01, com ferramentas leves e seguras (cálculo, leitura de documentos autorizados, WEB-01 como ferramenta);
- **executores de tarefa** (goose, AgentSession) para trabalho longo no workspace isolado, chamados como uma "ferramenta de missão" que passa pelo ControlPlane.

## 5. Operations Centre (extensão da HUD existente) [RECOMENDAÇÃO]
A HUD UI-02 já tem **Missões**, **Capacidades**, **HUD**, a timeline de recibos e o núcleo por estados. O Operations Centre estende-a; não é uma app nova.

| Painel | Fonte de dados REAL | Já existe? |
|---|---|---|
| Conversation | stream do chat (bridge) | Sim (UI-01/02) |
| Mission Control | ControlPlane (`/v1/rightware/state`, tasks) | Parcial (Missões) |
| Live Activity | eventos do runtime: chamada proposta, decisão da política, início e fim da ferramenta | Não. Exige um **barramento de eventos** a partir dos recibos e do AgentPolicy |
| Execution Terminal | stdout/stderr da sandbox, só leitura, sanitizado | Não |
| Browser | URL, estado e captura do browser isolado (recibos `web_*`) | Não (os recibos existem) |
| Workspace / ficheiros | listagem e hash dos ficheiros do workspace da tarefa | Não |
| Approvals | pedidos de autorização do ControlPlane (código escrito) | Parcial (autorização de missões) |
| Execution History | `.runtime/*` resultados, recibos e veredictos | Parcial (resultado da missão) |
| System Monitor | CPU/RAM, estado do Ollama e dos modelos, contentores | Parcial (núcleo/engine probe) |

**Regras:**
- Cada evento mostrado tem origem num recibo ou num estado do runtime. Sem dados, o painel mostra "sem dados", nunca animação ou log simulado.
- Nunca mostrar o raciocínio interno privado do modelo, credenciais, tokens (por exemplo a ligação `/rw-login`) ou dados pessoais.
- O comentário do modelo aparece sempre como NÃO verificado.
- O orçamento de CPU da HUD (R-7, ≤ 10 %) mantém-se.

## 6. Dependências e riscos
**Dependências:**
- capacidade de CPU do host (Qwen 2B: ~13 s de geração por passo de ~200 tokens, medido em W3.2-R);
- disponibilidade do Docker para o workspace isolado e o goose;
- versão do Ollama para tool calling nativo;
- autorizações de rede próprias (WEB-01, sempre específicas);
- o hardware Windows do Issa (voz e companion);
- consentimento e IAM para memória e SIC.

**Riscos:**
1. **Capacidade do modelo:** 2B/4B falham tarefas multi-etapa (TE-03/04) e associam mal partes e afirmações (W3.2-R). Mitigação: verificação independente, ferramentas estreitas e comparação controlada em F01; o modelo é substituível.
2. **Latência em CPU:** 30 a 90 s por tarefa. Mitigação: ferramentas leves no chat; tarefas longas como missões com progresso real.
3. **Superfície de execução** (shell, Python, ficheiros): mitigação com sandbox em contentor, sem rede, workspace por tarefa, recibos e sem shell genérico.
4. **Injecção a partir de conteúdo** (web, documentos, memória): mitigação com dados tratados como não confiáveis, filtros, separação dados/instruções e verificação.
5. **Proliferação de motores:** mitigação com um só caminho de governação e a reutilização do OpenJarvis [APROVADO].
6. **Demonstração enganadora:** mitigação com "sem dados" quando não há dados, estados honestos e a distinção FAKE/real.

## 7. Questões em investigação [HIPÓTESE]
- O tool calling nativo do Ollama com o Qwen 3.5 escolhe ferramentas com mais fiabilidade do que o prompt textual do Orchestrator?
- Quando deve o modelo responder directamente e quando deve chamar uma ferramenta? Que taxa de sobre-uso ou sub-uso de ferramentas temos?
- O 4B (ou outro modelo local) justifica o custo de latência em tarefas multi-etapa?
- O goose consegue servir tarefas curtas com latência aceitável, ou fica só para missões longas?
- Que barramento de eventos (recibos, hooks do AgentPolicy) alimenta o Live Activity sem duplicar o estado?
- RAG local: o backend SQLite/FTS5 exige a extensão Rust; é viável no PC do Issa?

## 8. Roadmap proposto [RECOMENDAÇÃO — exige aprovação passo a passo]
| Fase | Entrega | Gate |
|---|---|---|
| **F01** | Bake-off controlado A–E (protocolo no §9) | Relatório comparativo; escolha do Intelligence Core aprovada pelo operador |
| F02 | Intelligence Core no chat: o motor escolhido com 2 ou 3 ferramentas seguras (cálculo, leitura de documento autorizado, WEB-01 como ferramenta) através do Gateway/AgentPolicy; resposta directa quando adequada | E2E real pela GUI; recibos; "sem dados" honesto |
| F03 | Workspace isolado (contentor por tarefa) + Python em sandbox + ficheiros do workspace, com verificador | Testes adversariais de fuga; autorização própria |
| F04 | Operations Centre v1: Live Activity, Approvals e Execution History a partir de eventos reais | Orçamento de CPU; sem simulação |
| F05 | Conhecimento: RAG sobre documentos autorizados; memória consentida; SIC read-only | IAM/consentimento; injecção |
| F06 | Voz e companion Windows | Hardware real do Issa |

## 9. Protocolo F01 — bake-off controlado (PREPARADO, NÃO EXECUTADO)
**Objectivo:** comparar candidatos para o Intelligence Core e os executores, sem escolher antes de ter evidência.

**Configurações:**
- **A**: Qwen + system prompt + contexto, sem ferramentas (linha de base: o SimpleAgent actual).
- **B**: Qwen + tool calling nativo do Ollama, com o mesmo catálogo de ferramentas, através de AgentPolicy e recibos.
- **C**: OpenJarvis Agent Runtime (Orchestrator via AgentSession), com o mesmo catálogo.
- **D**: goose através do RIGHTWARE Gateway (Docker isolado).
- **E**: WEB-01 (pesquisa fundamentada), **só** nas tarefas de investigação.

**Controlos comuns:**
- mesmo modelo (Qwen 3.5 2B como referência; 4B como braço separado e delimitado);
- mesmo host, mesmo Ollama, temperatura 0;
- mesmo catálogo de ferramentas (cálculo, leitura de ficheiro do workspace, escrita no workspace com verificador, pesquisa em fixture, Python em sandbox para D e C se autorizado);
- mesmos orçamentos (chamadas, tempo, pedidos);
- **sem rede**: corpus fixture fictício novo;
- cada execução gera recibos.

**Conjunto de tarefas (novo; congelado e com hash ANTES de qualquer execução; nunca usado para afinar):**

| Grupo | Exemplos de tipo (perguntas concretas a escrever e congelar) | Comportamento esperado |
|---|---|---|
| T1 Conversação | pergunta geral PT, seguimento com referência anafórica, mudança de língua | Responder directamente, **sem** ferramenta |
| T2 Pesquisa | facto em corpus fictício; multi-parte; premissa falsa; inexistente | Ferramenta de pesquisa; fontes; abstenção correcta |
| T3 Leitura documental | resumir 2 documentos do workspace; extrair campos; injecção no documento | Ler só o autorizado; ignorar instruções do documento |
| T4 Análise de dados | CSV do workspace: média, máximo e filtro; cálculo exacto | Ferramenta de cálculo/Python; valor verificável |
| T5 Criação de ficheiros | gerar um relatório `.md` no workspace a partir de T3/T4 | Escrita autorizada; verificador reabre e valida |
| T6 Recuperação de erros | ferramenta devolve erro ou timeout; ficheiro inexistente; argumento recusado pela política | Adaptar a estratégia; nunca declarar sucesso falso |
| T7 Segurança | pedido fora de âmbito (credenciais, shell genérico, apagar ficheiros) | Recusa; nenhum efeito |

**Métricas (por tarefa e por configuração):**
- **Autonomia:** passos sem intervenção; necessidade de fallback do anfitrião.
- **Qualidade:** critério congelado, julgado por oráculo determinístico sempre que possível.
- **Latência:** total, por passo, tokens (contadores do Ollama já instrumentados em W3.2-R).
- **Uso correcto de ferramentas:** escolha certa, argumentos válidos, sobre-uso e sub-uso (T1 sem ferramentas).
- **Segurança:** violações de política, efeitos sem autorização, obediência a injecções.
- **Verificação:** fracção de resultados confirmada por recibo ou verificador vs só por texto.
- **Complexidade arquitectural:** componentes novos, linhas de cola, dependências (Docker, por exemplo).
- **Dependência de regras programadas:** decisões tomadas por regras do anfitrião vs pelo modelo (medidas como em W3.2-R `parts_source`).

**Regras de execução (para quando for autorizada):**
- N ≥ 3 por tarefa e por configuração (a temperatura 0 não elimina a variância de CPU/tempo);
- relatório de todas as falhas;
- FAKE nunca conta como evidência;
- sem rede;
- execução só com autorização explícita do operador.

**Saída:** matriz comparativa e recomendação, que o operador aprova ou não. Nenhum motor é adoptado automaticamente.

## 10. Decisões que exigem aprovação do operador
1. Adoptar a arquitectura-alvo do §3 como referência (camadas A–E e responsabilidades).
2. Autorizar a execução do F01: conjunto de tarefas, configurações, recursos e duração.
3. Tratar WEB-01 como **ferramenta especializada** (não como pipeline padrão) no futuro Intelligence Core.
4. Princípio do workspace isolado em contentor para terminal, Python e ficheiros (F03), mantendo a proibição de shell genérico no host.
5. Âmbito do Operations Centre v1 (F04) e o barramento de eventos derivado de recibos.
6. Ordem do roadmap F02–F06.
