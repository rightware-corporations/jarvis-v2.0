# JRV-004 — System Architecture, Interfaces & Deployment Options

**Product:** RIGHTWARE JARVIS  
**Version:** 1.0 — proposed architecture  
**Date:** 2026-11-14  
**Status:** PROPOSED ARCHITECTURE — operator approval pending  
**Authoring basis:** JRV-001 capability taxonomy, JRV-002 use cases, JRV-003 behaviour contracts; engineering HANDOFF and historical docs/ARCHITECTURE.md  
**Scope:** Logical components, responsibility boundaries, contract catalog, data/storage design, operating modes, security and reliability, technology choices and ADRs.  
**Authority:** Documentation only; no code implementation, A4, model run, deployment, procurement or migration authorized.  
**Next:** JRV-005 — pin actual repository HEAD and audit architecture-to-code/test coverage.

## 1. Architecture drivers

| Driver | Requirement | Relevant reference |
|---|---|---|
| D-01 | Assist conversationally in Portuguese without unnecessary orchestration | UC-001–005; CT-01–03 |
| D-02 | Distinguish conversation state from deliberately persisted memory | UC-008–011; CT-04/05 |
| D-03 | Convert actionable intent into bounded, auditable plans | UC-012/013, UC-022; CT-06 |
| D-04 | Enforce authorization independent of model or retrieved content | UC-014–028; CT-05/08 |
| D-05 | Link real tool outcomes to individual requests; never invent effects | UC-021–024; CT-07 |
| D-06 | Recover after interruption without duplicating side effects | UC-025/032; CT-09 |
| D-07 | Work on supported local hardware and degrade gracefully | UC-029/030; CT-10 |
| D-08 | Expose usable UI, progress, consent and uncertainty | UC-016/033; CT-03/08 |
| D-09 | Support replaceable model and tool providers | JRV-08, JRV-05 |
| D-10 | Allow future reusability without making Shared Intelligence Core a required network service | Strategic hypothesis; independent review required |

**Preferred architectural hypothesis:** local-first **modular monolith** with explicit ports/adapters and a separated trust/authorization boundary. It is an engineering recommendation, not an approved technology decision. Do not add microservices or hosted dependencies solely to match this picture.

## 2. Context and external boundaries

~~~mermaid
flowchart LR
  User["Primary user (Issa pilot)"] --> UI["JARVIS UI and Voice"]
  Owner["Device owner / setup operator"] --> Admin["Local configuration & consent"]
  UI --> Core["RIGHTWARE JARVIS application"]
  Admin --> Core
  Core <-->|"Model API over loopback / approved runtime"| Model["Local LLM Runtime (candidate: Ollama)"]
  Core <-->|"Scoped calls"| OS["Windows / local filesystem"]
  Core <-->|"Scoped calls"| APIs["Opt-in calendar, mail, websites, service APIs"]
  Core <-->|"Local authorized data"| DB["Private local persistent store(s)"]
  Core --> Audit["Local diagnostics and audit"]
  Maint["RIGHTWARE maintainer"] -.->|"Release packages, not default private-data access"| Core
~~~

**Trust boundaries:** User input, LLM output, model tool-call proposals, third-party pages/documents, external APIs and downloaded software are individually untrusted until the relevant authenticated controller validates them. No upstream plugin may silently grant itself additional privileges.

## 3. Modular architecture

~~~mermaid
flowchart TD
  T["JRV-01 Input channels"] --> Router["JRV-02 Intent / Context Router"]
  Router <--> Session["JRV-03 Session context"]
  Router --> Answer["Direct answer path"]
  Router --> Planner["JRV-04 Planner / Objective graph"]
  Planner --> Broker["JRV-05 Tool broker / adapters"]
  Broker --> Receipt["JRV-06 Execution receipts"]
  Receipt --> Gate["JRV-06 Objective verification / completion"]
  Gate -->|"Bounded safe continuation"| Planner
  Answer --> Render["JRV-09 User result / speech / controls"]
  Gate --> Render
  Policy["JRV-07 Authorization and consent"] --> Broker
  Policy -.-> Planner
  State["JRV-03 Persistent task ledger and memory"] <--> Planner
  State <--> Gate
  Runtime["JRV-08 Model/runtime host"] --> Router
  Runtime --> Planner
  QA["JRV-10 Audit / traces / test instrumentation"] -.-> Broker
  QA -.-> Gate
~~~

These are **logical modules**. In the current repository, some related code is already integrated into \`AgentSession\`; JRV-005 must inspect actual boundaries before any suggested extraction. Separate diagrams do not require separate OS processes or Python packages.

### 3.1 Responsibilities, inputs/outputs and authority

| Module ID | Logical subsystem | Owns | Must not own | Input → output |
|---|---|---|---|---|
| MOD-01 | Channel adapters | Chat, optional wake/STT/TTS, attachment decoding | Permission grants, long-term memory policy | User modality → RequestEnvelope |
| MOD-02 | Context/intent router | Context resolution, ambiguity, task class, clarification | Direct OS privileges | Request + session → IntentAssessment |
| MOD-03 | Memory service | Working context, opt-in durable memories, provenance, deletion | Tool execution, policy grants | Authorized facts → MemoryRecord or missing |
| MOD-04 | Planner/objective engine | Goal decomposition, dependency graph, budgets and progress | Receipt fabrication, unauthorized writes | Intent + goals → TaskSpecification |
| MOD-05 | Tool registry/broker | Adapter discovery, parameter validation, dispatch | User approval decisions, completion claims | Approved call → Result/ExecutionEvidence |
| MOD-06 | Evidence/completion engine | Receipts, objective predicates, uncertainty, recovery suggestions | Grant escalation, untrusted identity assumptions | Contract + evidence → CompletionAssessment |
| MOD-07 | Policy/identity/consent | Principal, scope, grants, risk tiers, expiration, audit enforcement | Model-generated authority | Call + principal + policy → GrantDecision |
| MOD-08 | Runtime/orchestration | Model connection, task lifecycle, timeouts, startup, resource control | User data sharing without authorization | Config + request → bounded execution |
| MOD-09 | Experience/application shell | Onboarding, task UI, confirmation dialogs, history presentation | Truth state independent of evidence engine | State and assessment → understandable UX |
| MOD-10 | QA/observability | Test fixtures, metrics, diagnostics, safe logs, release gates | Private transcript collection by default | Events/build context → inspectable evidence |

### 3.2 Routing rules

- **Knowledge request:** MOD-02 may route directly through a model answer and MOD-09, with no plan/tool invocation. Mark freshness limits where material.
- **Ambiguous request:** MOD-02 must first apply available context and user corrections; ask only for material missing facts.
- **Read-only investigation:** MOD-04 generates bounded objectives; MOD-07 authorizes; MOD-05 reads; MOD-06 checks provenance sufficiency.
- **Side-effecting task:** explicit objective + exact scope + necessary confirmation + executable adapter + postcondition check.
- **Ongoing/recurring task:** do not promise autonomous execution without durable scheduler and revocation controls.
- **Failure:** classify operational uncertainty independently from answer text; stop unsafe retries and preserve what is known.

## 4. Interface contracts — proposal, not source-code APIs

### 4.1 Standard envelope

~~~json
{
  "schema_version": "1.0-proposed",
  "request_id": "opaque-runtime-id",
  "session_id": "opaque-session-id",
  "principal_id": "local-authenticated-principal",
  "channel": "text",
  "input": {"kind": "text", "value": "Abre a aplicação"},
  "received_at": "ISO-8601 UTC timestamp",
  "capability_scope": ["chat"]
}
~~~

All fields are **illustrative**; values are not verified repository schemas. The principal and capability scope must be supplied by trusted host code, not by LLM-generated JSON.

### 4.2 Proposed ports

| Port | Request concept | Response concept | Rules |
|---|---|---|---|
| IContextResolver | RequestEnvelope + session references | IntentAssessment | Respects explicit correction and relevance; no automatic durable write |
| IModelProvider | Prompt/context with budget limits | Structured model response and usage | No model-independent guarantee of tool execution |
| IMemoryRepository | Owner + query/write/update/delete + retention | Versioned MemoryRecord/result | Ownership, consent, persistence confirmation, deletion propagation |
| IPlanner | IntentAssessment + allowed capabilities | TaskSpecification | Objectives immutable once trusted; no tool grants |
| IPolicyAuthority | Principal + canonical tool/arguments + state | GrantDecision | Deny by default, audit required when policy dictates |
| IToolAdapter | Validated canonical inputs + authorization token | ToolOutcome + resource evidence | Adapter cannot self-authorize or mint trusted outcomes for other calls |
| IReceiptJournal | Runtime-generated run/sequence/call identity + actual event | Immutable receipt / audit status | Handles timeout, late completion, orphan and duplicates fail-closed |
| ICompletionVerifier | Trusted task contract + admissible evidence | Objective and task states | LLM prose never used as proof; original identity independently verified |
| ITaskRepository | Task ID + optimistic version + checkpoint | Durable TaskSnapshot | Replay safety and reconciliation before retry |
| IUserSurface | Progress/results/approval requests | User interaction/consent | Approval bound to displayed exact operation; errors visible |
| IScheduler | Durable schedule + recurrence + permission expiry | Trigger and occurrence record | User can revoke; no duplicate irreversible effects |

### 4.3 Data flow: normal answer vs action

~~~mermaid
sequenceDiagram
  actor U as User
  participant UI as Interaction
  participant C as Intent/Context
  participant M as LLM Provider
  participant P as Policy
  participant T as Tool Adapter
  participant V as Verifier
  U->>UI: Request
  UI->>C: Request envelope
  C->>M: Resolve / answer if simple
  alt Informational
    M-->>UI: Answer with uncertainty
    UI-->>U: Reply
  else Action
    C->>P: Proposed exact call and context
    P-->>C: Grant / deny
    alt Denied
      C-->>UI: Refusal state
    else Authorized
      C->>T: Dispatch bound call
      T-->>V: Observed tool outcome + receipt
      V-->>UI: Completion/partial/unknown + evidence
    end
    UI-->>U: Verified outcome or clear limitation
  end
~~~

The sequence is **normative design**, not proof that the pinned vendor uses this call chain. An implementation must reconcile its executor thread/timeout and callback behavior before treating event order as authoritative.

## 5. Persistent data architecture — proposed

### 5.1 Data separation and privacy

| Data family | Minimum conceptual fields | Purpose | Persistence proposal |
|---|---|---|---|
| SessionContext | session ID, turns, reference links, context budget | Short-term coherent conversation | Ephemeral; optional local session history |
| UserMemory | principal, memory ID, value/reference, source, consent, validity, expiry, version | Durable user preferences/facts | Encrypted-at-rest where feasible; scoped local DB |
| TaskSpec | task ID, objectives, trusted origin, budget, state/version | Track required work | Durable transactional record for resumable tasks |
| TaskEvent | task ID, event ID, run ID, sequence, transition, timestamp | Reconstruct lifecycle | Append-only journal |
| ExecutionReceipt | call binding, tool, approval, executed/status, audit/evidence refs, late flag | Operational proof | Durable when recovery or audit needs it |
| ApprovalGrant | principal, exact args digest, capability, expiry, revocation | Authorization | Durable/expiring only for appropriate scope |
| EvidenceArtifact | source identity, resource reference, digest algorithm/scope, retrieval metadata | Verify objective-specific claims | Bounded storage with retention policy |
| ScheduledTask | recurrence rule, timezone, next trigger, permission lease, dedup key | Optional periodic work | Durable, revocable |
| RuntimeConfig | models, providers, hardware envelope, permitted adapters | Launch/compatibility | Local config, no credentials in plain logs |

**Key constraint:** A2/A3 currently hold receipts/gate state only in memory, according to the verified checkpoint. JRV-004 does not assert that this proposed durable schema exists.

### 5.2 Persistence candidate

A local transactional store (e.g., **SQLite** for a single-device instance) is a **candidate**, not an approved implementation. Transaction integrity, migrations, backups, encryption/key management and concurrency must be tested on the target machine. An embeddings/vector index is **optional** and should be adopted only if measured retrieval needs justify it; do not treat one as memory itself.

### 5.3 Memory pipeline

~~~mermaid
flowchart LR
  Msg["User statement"] --> Class["Classify: context / memory candidate / secret"]
  Class --> Consent{"Authorized to persist?"}
  Consent -->|"No"| Context["Session context only"]
  Consent -->|"Yes"| Validate["Validate provenance, retention, ownership"]
  Validate --> Commit["Transactional durable write"]
  Commit --> Readback["Verify commit/readback"]
  Readback --> Ack["Acknowledge durable memory"]
  Commit --> Delete["Correction, expiry, deletion"]
  Delete --> Index["Propagate to indexes/caches and verify"]
~~~

A phrase such as "está registado na minha memória" must not be presented as a durable claim when only an in-memory conversation list exists.

### 5.4 State transitions and consistency

- Task and action identifiers generated by the runtime, separate from model-provided call IDs.
- Monotonic sequence per run and unique event IDs; append-only journal where needed.
- Versioned task updates or transactional compare-and-swap; avoid concurrent blind overwrites.
- Idempotency key for external sends, calendar updates and destructive operations; provider reconciliation before replay.
- Cancellation stops **new grants**; a late external side effect cannot be assumed rolled back.
- Memory deletion should invalidate caches/indexes and follow a defined retention policy.
- Audit failures and unknown source identity must remain explicit uncertainty, not success.

## 6. Security and trust model

### 6.1 Threats and mitigating controls

| Threat | Trust boundary | Required defense / verification |
|---|---|---|
| Prompt injection in web or document content | External data → agent | Data cannot override trusted system policy; tool grant stays independent |
| JSON tool parameters malformed or mutated | LLM → broker | Canonical validation, source-of-decision denials, fail-closed |
| Duplicate/late/orphan execution attribution | Executor → receipt | Runtime-bound tokens, explicit late flags, no proof from ambiguous correlation |
| SSRF / internal-network navigation | Browser → network | Host allowlists, canonical URLs, redirect checks, non-public IP refusal where applicable |
| Privilege escalation by model text | Model → OS tools | Separate operator authority, least privilege, exact action scope |
| Local data exfiltration | Memory/files → network | Connector permission scopes, redaction, explicit external-transfer consent |
| Duplicate external side effects after retry | Worker → external API | Idempotency, status reconciliation and durable task state |
| Unauthorized memory read | User identity → store | Owner-scoped queries, isolation and audited access |
| Secret leakage through logs/receipts | Tools → diagnostics | Sensitive argument/content redaction and retention limits |
| Unsafe installed update or dependency | Build → device | Pinned packages, provenance, test gates, recoverable upgrade |

### 6.2 Permissions / risk levels (proposed)

- **R0** informational: no side effect.
- **R1** read-only permitted: bounded read and provenance.
- **R2** reversible write: exact-scope grant, read-back verification.
- **R3** external visibility: pre-send preview and explicit approval, idempotency/reconciliation.
- **R4** destructive or privileged: strong confirmation, narrow sandbox or refusal when guarantees unavailable.

These risk tiers require actual adapter mapping and security review in JRV-005/JRV-007. They do not grant any new action to current code.

### 6.3 Separation of responsibility

Only trusted host/runtime code can create principals, approved contracts, policy grants, receipt authority and verified objective state. An LLM can propose but cannot self-certify. Third-party content cannot amend a contract. RIGHTWARE maintainers do not automatically gain access to a customer's local data.

## 7. Runtime, model and provider design

### 7.1 Replaceable LLM provider interface

Candidate provider contract: \`generate(messages, tool_schemas, limits) -> model_response + usage + provider_diagnostics\`. Model responses are untrusted. A provider may support function-calling or only text, and capability negotiation should select compatible action paths rather than silently fabricating tool calls.

Possible providers: local **Ollama + Qwen**, other local inference engines/models subject to licence, support and measured quality. No dependency on commercial paid API should be assumed. The observed Kaggle success for Qwen 2B/4B does not establish target Windows device readiness.

### 7.2 Runtime modes

| Mode | Purpose | Dependencies | Limitation |
|---|---|---|---|
| DEV/FAKE | Deterministic tests of policy, task state and receipts | Test fixtures, no real model | Cannot validate semantic quality |
| KAGGLE-LAB | GPU-based model experiments | Remote notebook, temporary sessions | Not a reliable always-on product or Windows action environment |
| LOCAL-TEXT | Text assistant on supported device | Local model runtime and UI | Hardware/context/latency envelope unproven |
| LOCAL-VOICE | Spoken interaction and optional wake word | STT/TTS/audio services + local runtime | Requires microphone/privacy and real target tests |
| LOCAL-ACTION | Scoped Windows tools and persistence | Policy adapters, auditable execution | Elevated risk and integration testing |
| OPTIONAL-REMOTE | Approved remote provider/services | Secure network, contracts and consent | Must not be a hidden default paid dependency |

**Deployment topology hypothesis:** single-user Windows process + optional local inference process listening on loopback + user-scoped private storage. If UI and backend are separate processes, use authenticated local IPC and bind to loopback by default; avoid exposing unauthenticated services on LAN. GPU availability must be probed and tested; fallback behavior declared.

### 7.3 Component reuse policy

**Already known (engineering checkpoints):** repository has a Python launcher, \`rightware.runtime\`, pinned OpenJarvis dependency, locally oriented model experiments, an existing \`AgentSession\` with policy, A1 contract, A2 receipts, A3 gate and 408 tests recorded at the A3 code SHA. This does not prove coverage of proposed ports.

**Candidate reuse decisions:** Keep existing tested policy/agent boundary rather than duplicating it; inspect upstream licensing and pin; compare memory, voice, embeddings and scheduling options on measurable criteria. Reuse RIGHTWARE Shared Intelligence Core locally only if versioning, licence, interface, security and operational needs justify it. No dependency introduced by this document.

## 8. Failure handling and recovery architecture

~~~mermaid
flowchart TD
  Call["Approved tool call"] --> Dispatch["Dispatch with runtime identity"]
  Dispatch --> Result{"Observed outcome?"}
  Result -->|"OK and auditable"| Verify["Postcondition & source identity check"]
  Result -->|"No / timeout"| Uncertain["Record timeout/late/unknown"]
  Result -->|"Denied / failed"| Failure["Record refusal / failed effect"]
  Verify --> Done{"Objectives proven?"}
  Done -->|"Yes"| Success["VERIFIED only with sufficient trusted proof"]
  Done -->|"Not all"| Incomplete["INCOMPLETE / UNKNOWN_IDENTITY"]
  Uncertain --> Reconcile["Reconcile before retry"]
  Failure --> Reconcile
  Incomplete --> Reconcile
  Reconcile --> Allowed{"Safe, authorized, budget and turn left?"}
  Allowed -->|"Yes"| Call
  Allowed -->|"No"| Stop["Report partial / unknown / halted"]
~~~

A3 recovery is limited and verified using FAKE model tests; no assumption of automatic post-restart continuation or real Qwen cooperation. Any architecture that introduces a new thread or worker must reconsider timeout/late completion and receipt attribution.

## 9. Proposed deployment and technology decision register

| ADR | Decision or question | Candidate / rationale | Status | Evidence needed |
|---|---|---|---|---|
| ADR-001 | Modular monolith vs distributed services | Modular local first for one device, lower operational burden | RECOMMENDED, not approved | Resource/use-case validation |
| ADR-002 | Primary agent language/runtime | Python to reuse tested modules | CANDIDATE | Repository code/dependency audit |
| ADR-003 | Model provider | Ollama + local Qwen, provider interface abstracted | CANDIDATE | Target-device quality/latency and licence tests |
| ADR-004 | Durable store | SQLite transactions for single device | CANDIDATE | Concurrency, encryption, backup/migration review |
| ADR-005 | Semantic retrieval | Start with lexical/structured retrieval; vector only if useful | CANDIDATE | Retrieval benchmark |
| ADR-006 | User interface | Native/lightweight desktop shell or local web UI; compare options | OPEN | Accessibility, deployment/security/performance |
| ADR-007 | Voice components | Local STT + TTS + wake word as interchangeable ports | OPEN | Portuguese quality, CPU use, privacy/false wake |
| ADR-008 | Task lifecycle | Durable journal and idempotent recovery design | RECOMMENDED | Crash-injection/end-to-end test |
| ADR-009 | Shared Intelligence Core reuse | Optional in-process/local adapter, no forced external server | INVESTIGATE | Code, licence, API and security review |
| ADR-010 | Model/tool sandboxing | Least-privilege per-adapter isolation | RECOMMENDED | Windows security boundary proof |
| ADR-011 | Distribution/update | Signed builds and safe rollback strategy | OPEN | Packaging pipeline and compatibility |
| ADR-012 | Original document identity | Trusted expected digest/signed publisher metadata/approved registry | OPEN | Threat model, trust root and negative fixtures |

No architecture choice becomes an **OFFICIAL DECISION** merely because it appears in this register.

## 10. Non-functional requirements and evidence plan

| NFR ID | Dimension | Design obligation | Test evidence for later matrices |
|---|---|---|---|
| NFR-01 | Correctness | Explicit task objectives and evidence predicates | JRV-003 AT cases, real task corpus |
| NFR-02 | Safety | Zero accepted unauthorized effects on controlled negative fixtures | Adversarial suite with OS/network isolation |
| NFR-03 | Recoverability | No blind replay of uncertain external effects | Fault injection, task restart/idempotency |
| NFR-04 | Privacy | No sensitive data in default logs, memory owner isolation | Log scanning, cross-user tests |
| NFR-05 | Performance | Measured latency p50/p95, RAM/VRAM by mode | Target hardware benchmark |
| NFR-06 | Availability | Explicit degraded state when runtime/model unavailable | Model outage/recovery tests |
| NFR-07 | Observability | Every side effect either auditable or denied | Bound receipt, trace/audit failure tests |
| NFR-08 | Portability | Provider/model interfaces not tightly tied to one vendor | Alternate provider smoke test |
| NFR-09 | Installability | Reproducible setup and safe upgrades on supported Windows | Fresh OS/device installation run |
| NFR-10 | User experience | Consent, task status, uncertainty understandable without code | Pilot usability scenarios |
| NFR-11 | Speech | False wake, transcription accuracy and cancellation measured | Real Portuguese audio corpus |
| NFR-12 | Data lifecycle | Memory/ledger correction, backup and deletion demonstrated | Restart, migration, delete/retrieve tests |

Do not invent numeric latency, memory or success-rate targets before baselining a real target machine and approved corpus. JRV-003 defines candidate KPIs and strict negative test oracles; JRV-007 will set release gates.

## 11. Integration slices and proposed architectural checkpoints

| Slice | End-to-end objective | Dependencies | Acceptance form |
|---|---|---|---|
| S-01 | Simple Portuguese answer with context correction | UI, model, intent/context | UC-001–005 dialogue corpus |
| S-02 | Explicit authorized memory survives restart | Consent, repository, retrieval | UC-008–011 restart/delete |
| S-03 | Local create-folder with receipt and read-back | Policy, tool broker, verifier | UC-014 exact path and denial |
| S-04 | Multi-step original-document search stays UNKNOWN_IDENTITY until trust established | Task contracts, browser, receipts, verification | UC-021–024 negative corpus |
| S-05 | Confirmed external message with duplicate-prevention | Connector, consent, provider reconcile | UC-017 external side-effect tests |
| S-06 | Crash/resume without duplicate side effects | Durable task ledger, reconcile, scheduler | UC-025/032 fault injection |
| S-07 | Portuguese voice -> understood request -> verified result | Audio, model, context, tools, UI | UC-029 real hardware tests |
| S-08 | Approvals and evidence visible in product UI | Identity, audit, progress, history | UC-033 usability + security |

Slices are **candidates**, not authorized development milestones.

## 12. Explicitly unresolved decisions and risks

1. **Memory:** what exactly is durable, with which consent, retention, encryption, migration and deletion semantics?
2. **Device:** Issa's minimum CPU/RAM/VRAM/Windows version and offline requirement are not confirmed by this Blueprint.
3. **Tool scope:** exact first-release operations, risk classes, confirmations, permitted directories and connected services.
4. **Identity:** reliable document-origin or content authenticity trust root; bare raw SHA-256 merely records bytes unless compared with trusted expectation.
5. **Architecture reuse:** inspect actual Shared Intelligence Core and OpenJarvis code/compatibility/licence before selecting modules.
6. **Voice:** wake word, Portuguese STT/TTS, microphone privacy, performance and false activation.
7. **State:** crash-consistent task journal, idempotency and audit integrity may require redesign around existing in-memory A2/A3.
8. **Commercialization:** multiple profiles, tenancy, licensing and ongoing support are hypotheses; the initial product must not assume multi-tenancy.
9. **Secure UI:** choice of local desktop shell vs local web frontend affects packaging and security; decide with evidence.
10. **Test policy:** software cannot be called integrated/accepted based only on deterministic FAKE tests, even with green CI.

## 13. Architecture-to-acceptance traceability

| JRV subsystem | Main ports | Use cases | Cross-contracts |
|---|---|---|---|
| JRV-01 | Channel adapters | 001–005, 029 | CT-01, CT-02, CT-10 |
| JRV-02 | ContextResolver | 001–005, 012–013 | CT-01, CT-02, CT-03 |
| JRV-03 | MemoryRepository, TaskRepository | 008–011,025,031 | CT-04, CT-05, CT-09 |
| JRV-04 | Planner, ModelProvider | 012–013,022,032 | CT-01, CT-06, CT-09 |
| JRV-05 | ToolBroker, ToolAdapters | 014–022,027–028 | CT-06, CT-08 |
| JRV-06 | ReceiptJournal, CompletionVerifier | 021–026,032–033 | CT-07, CT-09 |
| JRV-07 | PolicyAuthority, ApprovalGrant | 011,014–020,026–028 | CT-05, CT-08 |
| JRV-08 | Runtime, Provider, Scheduler | 025,029–032 | CT-09, CT-10 |
| JRV-09 | UserSurface | 001–005,016–019,029,033 | CT-01, CT-03, CT-08 |
| JRV-10 | Observability, QA fixtures | All use cases | CT-01–CT-10 |

All IDs refer to the *proposed taxonomy*; this is not a claim that matching classes or files already exist.

## 14. JRV-005 handoff: code audit evidence requirements

The next matrix MUST inspect the real remote \`develop\` HEAD, PRs, CI and \`docs/HANDOFF.md\`, recording a single audit SHA and avoiding destructive checkout. For each MOD-01–10 / port / UC/CT identify:

1. Actual repository path, class/function, version/pin and ownership.
2. Implementation class: **VERIFIED / IMPLEMENTED_UNVERIFIED / PARTIAL / ABSENT / UNKNOWN**.
3. Test files and whether they are unit, synthetic FAKE, live local, Kaggle model or integrated Windows.
4. Exact tested outcomes/conditions and untested failure branches.
5. External upstream dependencies and ability to swap them.
6. Security/trust boundary and data persistence characteristics.
7. Known blockers, feature gaps, duplication and dependency impacts.
8. What is proposed architecture, as opposed to implemented product.
9. Risk of changing working A1–A3 behavior; byte-identical default-off regression.
10. A traceability line back to JRV-001–003.

No code changes, A4, new memory store or model experiment are authorized by conducting the JRV-005 audit.

## 15. Governance and next action

**Written but NOT APPROVED:** modular monolith topology, ports, data schema, candidate stack, runtime modes, ADRs, deployment and test slices. The exact present implementation is limited to evidence already recorded in HANDOFF; this file is primarily a target architecture.

**Recommended review:** approve or revise JRV-001–004 conceptually, especially identity, first release scope, memory policy and Windows target. Without operator acceptance, these remain labelled PROPOSED.

**Next:** JRV-005 — evidence-led implementation inventory using the actual GitHub code tree, tests, CI, HANDOFF and pinned vendor. Then JRV-006 gap/dependency analysis and JRV-007 implementation roadmap with explicit release acceptance gates.
