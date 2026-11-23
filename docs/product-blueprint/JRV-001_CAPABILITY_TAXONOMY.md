# JRV-001 — Product Definition & Capability Taxonomy

**Product:** RIGHTWARE JARVIS  
**Version:** 1.0 — initial architectural proposal  
**Date:** 2026-11-14  
**Status:** PROPOSED ARCHITECTURE; pending explicit operator approval  
**Implementation authority:** None. This document authorizes no code, dependencies, rollouts or releases.  
**References:** \`docs/HANDOFF.md\`; \`docs/ARCHITECTURE.md\`; WORK-07 A1/A2/A3 engineering records.

## 1. Product definition

> RIGHTWARE JARVIS is a personal intelligent assistant intended to understand requests, retain relevant context, plan and perform authorized actions, use digital tools, verify outcomes, communicate uncertainty and recover safely from incomplete work. The architecture should progressively support durable memory, voice interaction and local operation.

This **proposal** defines the product independently of the upstream OpenJarvis project and of a particular LLM. Qwen/Ollama are tested model/runtime components, not product requirements. The first Issa-oriented implementation is one potential configuration of a reusable RIGHTWARE product architecture, **not** proof of commercial readiness.

### Essential distinctions

- **Answer**: provide knowledge without tool execution.
- **Investigate**: obtain and cite information, disclosing source limitations.
- **Plan**: identify objectives, prerequisites, dependent steps and approval points.
- **Act**: invoke policy-authorized tools; never treat LLM text as authorization.
- **Verify**: prove operational effects using authoritative evidence, not textual claims.
- **Continue**: resume safely, bounded by real budgets and recoverable state.
- **Remember**: persist data only under defined privacy, retention and operator-control rules.

Not every request must traverse every system. Simple factual questions should not require an expensive agentic workflow.

## 2. Logical architecture

\`\`\`mermaid
flowchart TD
    User[User] --> I[JRV-01 Interaction and Perception]
    I --> C[JRV-02 Intent and Context]
    C --> Route{Request type}
    M[JRV-03 Memory and Knowledge] <--> C
    Route -->|Simple answer| Reply[Response]
    Route -->|Investigation or action| P[JRV-04 Planning and Reasoning]
    M <--> P
    P --> E[JRV-05 Task Execution]
    E --> V[JRV-06 Verification and Recovery]
    V -->|Bounded recovery if allowed| P
    V --> Reply
    Sec[JRV-07 Security and Identity] -.-> C
    Sec -.-> E
    Infra[JRV-08 Runtime and Infrastructure] -.-> P
    Infra -.-> E
    Reply --> UX[JRV-09 Experience and Personalization]
    UX --> User
    QA[JRV-10 Engineering and Quality] -.-> V
    QA -.-> Infra
\`\`\`

Arrows describe **logical responsibilities**, not confirmed runtime call chains or a mandated microservices topology.

## 3. Capability taxonomy — 10 systems, 81 capabilities

Every row below is a **target capability**, not an assertion of implementation. The detailed implementation/evidence audit belongs to JRV-005.

### JRV-01 — Interaction & Perception

**Responsibility:** receive and present instructions in supported modalities.

| ID | Capability |
|---|---|
| JRV-01.01 | Text input |
| JRV-01.02 | Speech-to-text (STT) |
| JRV-01.03 | Wake word / name activation |
| JRV-01.04 | Text-to-speech (TTS) |
| JRV-01.05 | Files and document input |
| JRV-01.06 | Images and screen perception |
| JRV-01.07 | Events and notifications |

**Acceptance direction:** preserve the intended request across supported input modalities; report unavailable or uncertain perception.

### JRV-02 — Intent & Context Intelligence

**Responsibility:** understand what the user wants with reference to prior context.

| ID | Capability |
|---|---|
| JRV-02.01 | Intent recognition |
| JRV-02.02 | Question/research/task/conversation routing |
| JRV-02.03 | Ambiguity and reference resolution |
| JRV-02.04 | Conversational repair after correction |
| JRV-02.05 | Session context management |
| JRV-02.06 | Missing-information detection |
| JRV-02.07 | Answer-vs-clarify decision |

**Acceptance direction:** interpret "Como é o mundo?" in context, recover when the user clarifies "planeta Terra", and preserve referents like "essa camada". The observed Kaggle conversation demonstrates some context retention but does not prove a dedicated context subsystem.

### JRV-03 — Memory & Knowledge

**Responsibility:** retain, retrieve and govern information.

| ID | Capability |
|---|---|
| JRV-03.01 | Working memory |
| JRV-03.02 | Conversation history |
| JRV-03.03 | Durable user memory |
| JRV-03.04 | Task and decision memory |
| JRV-03.05 | Knowledge search/retrieval |
| JRV-03.06 | Relevance, provenance and freshness |
| JRV-03.07 | Correction, expiry and deletion |
| JRV-03.08 | Personal-data protection |

**Acceptance direction:** recall an authorized saved fact after restart and honor correction/deletion. Session chat history alone does **not** prove durable memory.

### JRV-04 — Planning & Reasoning

**Responsibility:** translate goals into bounded, testable action plans.

| ID | Capability |
|---|---|
| JRV-04.01 | Request complexity assessment |
| JRV-04.02 | Subtask decomposition |
| JRV-04.03 | Objectives and success criteria |
| JRV-04.04 | Dependencies and sequencing |
| JRV-04.05 | Tool/resource selection |
| JRV-04.06 | Plan revision |
| JRV-04.07 | Planning budgets and limits |
| JRV-04.08 | Human escalation |

**Acceptance direction:** turn "organiza a minha semana" into an explicit plan with dependencies, authorized reads and actions, missing information and outcome checks.

### JRV-05 — Task Execution

**Responsibility:** perform authorized operations using bounded tools.

| ID | Capability |
|---|---|
| JRV-05.01 | Tool registry/discovery |
| JRV-05.02 | Application/API adapters |
| JRV-05.03 | Local Windows actions |
| JRV-05.04 | Browser and web operations |
| JRV-05.05 | File operations |
| JRV-05.06 | Multi-step workflows |
| JRV-05.07 | Approval of sensitive actions |
| JRV-05.08 | Cancellation and control |

**Acceptance direction:** execute authorized actions, deny unauthorized ones, report partial effects and handle failure safely.

### JRV-06 — Verification & Recovery

**Responsibility:** establish what was really done and what remains.

| ID | Capability |
|---|---|
| JRV-06.01 | Task contracts |
| JRV-06.02 | Execution receipts and evidence |
| JRV-06.03 | Objective-specific verification |
| JRV-06.04 | Completion classification |
| JRV-06.05 | Partial-result detection |
| JRV-06.06 | Bounded continuation/recovery |
| JRV-06.07 | Resume interrupted tasks |
| JRV-06.08 | Verified outcome reporting |

**Acceptance direction:** do not report task success from informative pages alone. A1–A3 implement a **limited opt-in subset**, using synthetic presets and FAKE-model evidence, not the full system.

### JRV-07 — Security & Identity

**Responsibility:** independent trust and authorization boundaries.

| ID | Capability |
|---|---|
| JRV-07.01 | Operator identity/authentication |
| JRV-07.02 | Capability- and tool-level permissions |
| JRV-07.03 | Consent management |
| JRV-07.04 | Prompt-injection resistance |
| JRV-07.05 | Isolation/sandboxing |
| JRV-07.06 | Secret management |
| JRV-07.07 | Audit and traceability |
| JRV-07.08 | Privacy and data protection |
| JRV-07.09 | Irreversible-operation controls |

**Acceptance direction:** a model output or untrusted webpage cannot grant execution rights or silently bypass confirmation.

### JRV-08 — Runtime & Infrastructure

**Responsibility:** reliable local or authorized remote operation.

| ID | Capability |
|---|---|
| JRV-08.01 | Agent lifecycle |
| JRV-08.02 | LLM provider interface |
| JRV-08.03 | Model selection/fallback |
| JRV-08.04 | CPU/GPU/RAM management |
| JRV-08.05 | Persistence and migrations |
| JRV-08.06 | Process/service supervision |
| JRV-08.07 | Installation and updates |
| JRV-08.08 | Crash recovery |
| JRV-08.09 | Hardware diagnostics |

**Acceptance direction:** install, restart and update safely on a supported target while preserving authorized persisted state.

### JRV-09 — Experience & Personalization

**Responsibility:** a usable product, not a developer notebook.

| ID | Capability |
|---|---|
| JRV-09.01 | Conversational interface |
| JRV-09.02 | Onboarding |
| JRV-09.03 | Language/behavior preferences |
| JRV-09.04 | Task plan/progress display |
| JRV-09.05 | Action approval interface |
| JRV-09.06 | Notifications and feedback |
| JRV-09.07 | Accessibility |
| JRV-09.08 | User control of memory/tasks |

**Acceptance direction:** operate essential features without manually editing code, logs or Kaggle cells.

### JRV-10 — Engineering & Quality

**Responsibility:** evidence-based engineering and lifecycle management.

| ID | Capability |
|---|---|
| JRV-10.01 | Requirements/contracts/documentation |
| JRV-10.02 | Unit/integration testing |
| JRV-10.03 | Real-model end-to-end testing |
| JRV-10.04 | Regression/compatibility |
| JRV-10.05 | Observability/diagnostics |
| JRV-10.06 | Performance benchmarking |
| JRV-10.07 | Security/dependency review |
| JRV-10.08 | CI/CD and releases |
| JRV-10.09 | Handoff and decision traceability |

**Acceptance direction:** trace each release feature from requirement to tested code, integration evidence and an explicit acceptance decision.

## 4. Request classes and operational behaviour

| Class | Example | Expected response |
|---|---|---|
| Knowledge | "O que é um carro?" | Direct explanation without invented tool use |
| Contextual explanation | "E de que é feito?" | Resolve prior referent |
| Research | "Quais opções existem?" | Search permitted sources; cite uncertainty |
| Planning | "Organiza a minha semana" | Plan, dependencies, missing information |
| Simple action | "Cria uma pasta" | Authorization, execution, verification |
| Sensitive action | "Envia este documento" | Confirm recipient/content and require authorization |
| Continuation | "Continua de onde parámos" | Recover verified task state |
| Memory | "Lembra-te desta preferência" | Apply retention/consent rules |
| Automation | "Verifica todas as manhãs" | Schedule only after explicit scope/control |
| Control | "Cancela a tarefa" | Stop permitted work and report real state |

User text does not grant extra permissions; task classification does not imply authority to execute.

## 5. Proposed logical contracts

These names are **conceptual**, not declarations of implemented Python interfaces. JRV-004 must reconcile them with actual code and avoid redundant replacements.

| Contract | Core information | Owner |
|---|---|---|
| UserRequest | instruction, channel, session ID, request ID | Interaction |
| IntentContext | intent, referents, context, uncertainty | Context |
| TaskPlan | objective IDs, steps, dependencies, conditions | Planning |
| AuthorizationDecision | tool, arguments identity, policy, outcome | Security |
| ExecutionReceipt | bound execution, status, evidence scope | Execution/verification |
| CompletionAssessment | objective states, task state, unknowns | Verification |
| TaskState | recoverable state, checkpoints, limits | Continuity |
| MemoryUpdate | value, source, authorization, retention policy | Memory |

Rules: no LLM-generated authority; no effect claimed from text alone; separate observation of URL, identity of original document, and factual correctness; no persistent memory without a policy; no unlimited retry.

## 6. Dependencies and engineering workstreams

\`\`\`mermaid
flowchart TD
  PD[Product definition] --> UC[Use cases and behaviour contracts]
  UC --> SEC[Runtime and security contracts]
  UC --> CTX[Intent and context]
  UC --> MEM[Memory]
  CTX --> PLAN[Planning]
  PLAN --> EXEC[Execution]
  SEC --> EXEC
  EXEC --> VER[Verification and recovery]
  CTX --> UX[Integrated experience]
  MEM --> UX
  VER --> UX
  UX --> E2E[Real-user and real-model acceptance]
  E2E --> RELEASE[Approved release]
\`\`\`

Suggested engineering workstreams ("factories"): intelligence; memory; planning/task execution; user experience; platform/security/quality. A workstream owns interfaces, tests and dependencies; it is not necessarily a microservice, separate repository or separate team.

## 7. Existing code vs target product — strictly preliminary

**Verified from engineering checkpoints (not an exhaustive audit):**
- A1 opt-in immutable task presets and task contract validation implemented.
- A2 opt-in execution receipts implemented, including dispatch/timeout correlation.
- A3 opt-in deterministic completion gate implemented, with bounded fake-model recovery.
- Issue #9 stale denial reason corrected/closed.
- A3 CI recorded 408 tests with zero skips in pinned environment and green workflows on observed code HEAD.

**Not established by these checks:**
- real-Qwen interaction with A3 recovery feedback;
- durable memory after process restart;
- fully deployed Windows assistant, speech and system integration;
- verified original-document authenticity (\`identity_rule=NONE\`);
- user acceptance of the product;
- A4 completion.

The actual code/component mapping will be produced in **JRV-005**, pinned to an explicitly recorded repository SHA and tests. No readiness percentage should be inferred from the number of subsystems.

## 8. Implementation status vocabulary

- **DEFINED** — responsibility and behavior specified.
- **DESIGNED** — architecture/interfaces reviewed.
- **IMPLEMENTED** — code exists.
- **VERIFIED** — applicable tests pass.
- **INTEGRATED** — end-to-end interaction with adjacent modules demonstrated.
- **ACCEPTED** — approved against explicit user/product criteria.

A unit test pass is **not** the same as an accepted feature or deployable release.

## 9. Suggested release layers (NOT APPROVED)

- **R1 — Usable assistant:** Portuguese chat, session context, local setup, interface, diagnostics and small validated capability set.
- **R2 — Operational assistant:** selected memory, authorized tools, goals, receipts, verification, bounded recovery and real local tasks.
- **R3 — Advanced assistant:** voice end-to-end, rich durable memory, task continuity, automations and extendable integrations.

Scope, hardware, performance and security acceptance thresholds will be determined in JRV-007; there are no committed dates here.

## 10. Open architecture decisions

1. Which capabilities are mandatory in Issa's **first accepted release**, as opposed to later product versions?
2. What is the supported hardware and on-device vs remote compute envelope?
3. Which actions require explicit approval and what constitutes an irreversible operation?
4. What is memory retention, provenance, correction and deletion behavior?
5. How will trusted document identity be established beyond a URL/HTTP 200?
6. How does product-specific local reuse of RIGHTWARE Shared Intelligence Core work without forced remote service dependencies?
7. What are the first measurable success targets for task completion, context repair, false tool-action claims, safety, latency and failure recovery?
8. What is the first distribution/upgrade model and supported OS?

These are **open decisions**, not implicit approvals.

## 11. Exit criteria and follow-up

JRV-001 is **authored but not officially approved** until the operator approves it in the conversation or repository decision log. The first eight structural criteria are covered (product definition, ten systems, capability taxonomy, request categories, logical lifecycle, preliminary contracts, dependencies, distinction between proposal and implementation); formal review remains.

**Next:** JRV-002 — real user roles, actor journeys and comprehensive use cases. For every use case: intent, context, preconditions, main path, alternatives, approvals, tool interactions, memory impact, evidence, recovery, safety and acceptance. JRV-003 then specifies measurable behavior contracts.

**Editorial correction:** The working chat draft described this taxonomy as "79 capabilities"; the actual enumerated matrix contains **81** (7+7+8+8+8+8+9+9+8+9). The versioned count uses the explicit rows as authority.