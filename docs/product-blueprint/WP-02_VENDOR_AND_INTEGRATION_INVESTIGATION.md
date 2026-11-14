# WP-02 — Pinned OpenJarvis Reuse, Licensing & RIGHTWARE Integration Investigation

**RIGHTWARE JARVIS v2.0** · **Report:** WP-02/R01  
**Date:** 2026-11-14 (Africa/Maputo)  
**Authorization:** [Official Blueprint approval](DECISION_2026-11-14_BLUEPRINT_V1_APPROVAL.md); read-only investigation and specification ONLY.  
**Status:** READ-ONLY RESEARCH DELIVERED; no vendor code execution, no implementation, no licence certification.  
**RIGHTWARE observed baseline before authorization:** \`develop\` \`791f409a2de5268ab074044dc42b2b438c99e6a8\`.  
**Pinned upstream revision:** \`open-jarvis/OpenJarvis@f21d902f4d3bd7f0f3f138f1a4613019a394b549\` (2026-11-06).  
**Source evidence:** GitHub API of pinned upstream commit (2,461 tracked entries, \`truncated=false\`), selected upstream source files and RIGHTWARE \`rightware/*\`, \`UPSTREAM_PROVENANCE.md\`, \`.gitmodules\`, \`configs/local.toml\`, tests and milestone specs.  
**Actions NOT performed:** no checkout/reset/rebase, no vendor update, no package installation, no model inference, no Windows actions, no test execution, no code modification.

## 1. Central finding: the pinned upstream already contains candidate building blocks

The previous JRV-005 audit correctly described a lack of integrated **RIGHTWARE product** memory, GUI, scheduler and general file actions. But that must not be interpreted as absence in **OpenJarvis at the pinned revision**.

The checked upstream Git tree at the **same pinned SHA** contains concrete implementations, not merely aspirational README bullet points:

| Reuse domain | Actual upstream path / symbols | Evidence from inspected source | Status for RIGHTWARE |
|---|---|---|---|
| Persistent fact memory | \`src/openjarvis/memory/store.py\`: \`FactStore\`, \`LocalFactStore\`, \`create_fact_store\` | JSONL durable facts, provenance/trust tiers, locking (including Windows path), add/list/clear | **IMPLEMENTED UPSTREAM; NOT INTEGRATED/ACCEPTED for RIGHTWARE E1** |
| Memory service | \`src/openjarvis/memory/service.py\`: \`MemoryService\`, \`build_memory_service\` | Async background fact extraction, trust/injection screening, config-enabled lifecycle | **UPSTREAM CANDIDATE**, privacy/consent mismatch likely |
| Memory CLI | \`src/openjarvis/cli/memory_cmd.py\` | List facts, trust a fact, clear, search/index memory backends | **UPSTREAM CANDIDATE**, not RIGHTWARE E1 user-control proof |
| Search/index memory | \`src/openjarvis/tools/storage/sqlite.py\`, \`connectors/embedding_store.py\` | Indexed/persistent retrieval components exist | **REQUIRES CODE/RETENTION AUDIT**, not automatic user memory |
| Scheduler storage | \`src/openjarvis/scheduler/store.py:SchedulerStore\` | SQLite persistent scheduled-task records and run logs | **UPSTREAM CANDIDATE**, NOT a safe RIGHTWARE task ledger |
| Scheduler agents/CLI | \`src/openjarvis/agents/scheduler.py\`, \`cli/scheduler_cmd.py\` | Scheduler-related orchestration paths exist | **UPSTREAM CANDIDATE**, background authorization/recovery unverified |
| GUI lifecycle | \`src/openjarvis/cli/gui_cmd.py:gui\`, \`_FrontendOwner\` | Starts local frontend/API, manages child processes and port ownership, references npm frontend | **UPSTREAM CANDIDATE**, requires local UI security/deployment audit |
| Tool implementations | \`src/openjarvis/tools/file_read.py:FileReadTool\`, \`file_write.py:FileWriteTool\` | Scoped directories, file sizes, read and write/append modes | **UPSTREAM CANDIDATE**, MUST NOT directly grant tools to model |
| Tool consent | \`src/openjarvis/tools/approval_store.py\` | Approval store exists (not full semantics audited) | **INVESTIGATE**, do not substitute for RIGHTWARE policy without proof |
| Tool orchestration | \`src/openjarvis/agents/orchestrator.py:OrchestratorAgent\` | Tool-calling loop and check-before-execute hooks with possible concurrent execution | **CURRENTLY USED BY RIGHTWARE AgentSession** |
| Simple conversation | \`src/openjarvis/agents/simple.py:SimpleAgent\` | No tool calling, model response from context | **CURRENTLY USED BY RIGHTWARE chat/voice pathways** |
| Server session store | \`src/openjarvis/server/session_store.py\` | Persistent session-store code path present | **UNKNOWN suitability** for durable user facts/task state |
| Security utilities | \`src/openjarvis/security/*\` incl. SSRF and injection | Several security modules in tracked vendor | **SELECTED READ-ONLY INSPECTION**, not a certification |
| Messaging integrations | \`src/openjarvis/channels/*\` and \`tools/*\` | Many provider adapters are in tree | **UPSTREAM CANDIDATES**, not connected/authorized in RIGHTWARE |

**Material conclusion:** Earlier "no durable memory" or "no file adapters" statements must always be qualified as **not identified in the RIGHTWARE audited product path**. The full pinned upstream may substantially reduce implementation cost, but **existence is not readiness**. Avoid implementing duplicate SQLite/fact memory/scheduler/GUI before applying fit-gap and licence/security tests.

## 2. Reconcile upstream capabilities with RIGHTWARE user-facing entrypoints

~~~mermaid
flowchart TD
  User["User / Issa"] --> Chat["RIGHTWARE runtime.chat_command -> upstream CLI simple"]
  User --> Voice["RIGHTWARE voice.VoiceLoop -> SimpleAgent + AgentContext"]
  User --> Agent["RIGHTWARE agent.cli -> AgentSession"]
  Agent --> Orch["Pinned OpenJarvis OrchestratorAgent"]
  Orch --> Policy["RIGHTWARE AgentPolicy and Tool boundary"]
  Agent --> Contract["A1 TaskContract: opt-in synthetic presets"]
  Agent --> Receipts["A2 ReceiptLedger: opt-in"]
  Agent --> Gate["A3 Completion Gate: opt-in"]
  Upstream["Pinned OpenJarvis optional modules"] -.-> Memory["FactStore + MemoryService"]
  Upstream -.-> Gui["GUI + local API"]
  Upstream -.-> Scheduler["SchedulerStore"]
  Upstream -.-> File["FileReadTool / FileWriteTool"]
  Policy -.->|"required boundary if adopted"| File
~~~

**Code-grounded observations:**

1. \`rightware/runtime.py\` pins upstream at the same Git SHA and checks it. \`configs/local.toml\` defaults to \`simple\`, \`qwen3.5:2b\`, Ollama loopback, \`context_from_memory=false\`, analytics/telemetry off.
2. \`rightware/voice.py:OpenJarvisBrain\` instantiates \`SimpleAgent\` and in-memory \`AgentContext\`; the voice loop chooses restricted Windows actions via deterministic Portuguese phrases.
3. \`rightware/agent/cli.py\` constructs \`AgentSession\` and passes \`allow\`, \`confirm\`, \`actions\`, \`audit_path\`, \`sites\`, \`start_url\`. It does **not** pass \`task_preset\`, \`receipts=True\`, \`completion_gate=True\`: ordinary CLI execution does not use the A3 gate.
4. \`rightware/agent/session.py\` implements opt-in A1/A2/A3 and a policy-protected \`OrchestratorAgent\` integration. It must be preserved rather than replaced by less-protected upstream generic tools.
5. \`rightware/windows_actions.py:ACTIONS\` contains only \`notepad\` and \`calculator\`; no arbitrary shell or file write is allowed in this product tool registry.
6. \`rightware/agent/web.py\` and \`browser.py\` use a stricter public read-only path than generic untrusted tool exposure. Upstream generic browser/file tools are not automatically equivalent.

**Critical architectural mismatch to study:** Upstream \`MemoryService\` can extract durable facts automatically from completed exchanges if enabled; the proposed JARVIS E1 requirement is **explicit, owner-controlled limited preference memory**, with consent, correction and deletion guarantees. Those cannot be treated as the same product policy without investigation. \`LocalFactStore.clear()\` does not itself demonstrate an approved user-facing selective deletion and stale-index invalidation process.

## 3. Upstream behaviour and risk details

### 3.1 Memory reuse — do not build from scratch prematurely

- \`LocalFactStore\` is a JSONL store, not the proposed SQLite user memory schema from JRV-004.
- Source records trust/provenance tiers; \`MemoryService\` processes exchanges asynchronously and can quarantine suspicious extracted facts.
- \`build_memory_service\` returns \`None\` when memory is disabled and requires configured extraction model; nothing in RIGHTWARE's observed \`local.toml\` authorizes enabling this service for user data.
- Auto-extraction is not equivalent to "remember this preference with consent". The design must define explicit write/read/edit/delete/expiry, owner binding and handling of sensitive categories; verify whether upstream has safe APIs before adapting.
- Source and tests present under \`tests/memory/*\` at pinned revision, but **their passing status was NOT executed or verified in this WP**.
- **Decision question:** adopt \`FactStore\` storage with a policy wrapper, adopt only selected utilities, or use a separate store if gaps outweigh reuse.

### 3.2 Scheduler and task ledger are not interchangeable

- Upstream \`SchedulerStore\` uses SQLite with \`scheduled_tasks\` and \`task_run_logs\`.
- This is evidence of **recurrence persistence**, not proof of durable A2 execution identity, side-effect idempotency, late-thread reconciliation or authorized post-crash resume.
- Recurrence should remain OUT OF E0/E1 unless separately approved.
- **Decision question:** can scheduler primitives be reused for E2 without inheriting unsafe autonomous execution scopes?

### 3.3 GUI may exist without satisfying product UX/security

- \`cli/gui_cmd.py\` manages API/frontend processes, ports and lifecycle; references a frontend and npm.
- A source-backed GUI candidate exists upstream; do not assert "new UI mandatory" before assessing theming, local auth, permission review, memory panels, task-state presentation, Node bundling and Windows packaging.
- That GUI is not automatically integrated with RIGHTWARE \`AgentSession\`, and no live GUI launch is authorized or proven by this report.
- **Decision question:** wrap/adapt upstream frontend vs a minimal custom local surface; compare coupling, security, packaging and operator experience.

### 3.4 File tools exist upstream; trust scope is the main blocker

- \`FileReadTool\` and \`FileWriteTool\` have path validation and file-size bounds, and \`FileWriteTool\` explicitly supports overwrite and append.
- Path constraints in upstream tools are insufficient alone to show RIGHTWARE's exact-argument confirmation, receipt binding, read-back verification, rollback and duplicate-prevention.
- These must not be exposed to a model by adding registry entries without independent RIGHTWARE policy and tests.
- **Decision question:** use upstream file adapters behind a stricter broker, versus implement limited typed RIGHTWARE adapters for approved operations.

### 3.5 Pinned Orchestrator timeout/concurrency semantics

- \`src/openjarvis/agents/orchestrator.py\` uses \`_check_tool_allowed\` before the executor and supports concurrent execution (ThreadPoolExecutor in function-calling path).
- Worker timeout may leave an in-flight tool active after agent's subsequent step. RIGHTWARE A2 explicitly addresses dispatch/call binding and late completion, and A3 requires admissible bound evidence.
- Any upgrade, middleware change or UI wrapper **MUST** retain these execution-boundary guarantees and test duplicate/orphan/late outcomes.

## 4. Licence and package constraints — evidence and limits

| Topic | Verified static finding | Required next validation |
|---|---|---|
| Upstream repository licence | \`open-jarvis/OpenJarvis\` GitHub repo reports Apache-2.0; pinned \`pyproject.toml\` says Apache-2.0, \`LICENSE\` exists | Read full terms/attribution/NOTICE obligations and all reused subcomponent licences |
| Provenance | RIGHTWARE includes pinned Git submodule \`vendor/openjarvis\` and \`UPSTREAM_PROVENANCE.md\`; no patches claimed there | Confirm current gitlink vs runtime PIN at each future engineering start |
| Python | Pinned upstream \`pyproject.toml\` requires \`>=3.10,<3.14\`; RIGHTWARE README guides 3.11–3.13 | Target Windows compatibility and package wheel availability |
| Core dependency installation | RIGHTWARE \`runtime.py\` uses frozen \`uv sync\` with only core unless voice extras requested | Audit complete lockfile and dependency licence/SBOM/security before distribution |
| Voice extras | Optional speech and voice extras chosen separately | Model/voice weights, redistribution rights, acoustic quality |
| Frontend | GUI uses npm/frontend process | Check frontend's own licence/deps/build and Windows footprint |
| Provider/API | Ollama loopback/default local model | Model weights/serving licences and any hidden cloud paths per enabled feature |

**Not a legal conclusion:** this read-only source examination does not certify RIGHTWARE commercial distribution rights over every included asset, weight, model, dependency or voice.

## 5. Reuse decision matrix — proposals, no approved implementation

| Candidate | Immediate action | E0/E1 relevance | Risk / necessary tests | Decision state |
|---|---|---|---|---|
| RIGHTWARE AgentPolicy | **PRESERVE**, not bypass | Mandatory for effects | A/B deny/batch/quotas/audit tests | RECOMMENDED |
| RIGHTWARE A1/A2/A3 | **PRESERVE/WRAP** in one user route | E0 task truth | Default OFF, FAKE, late/duplicate/orphan and real Qwen tests | RECOMMENDED |
| OpenJarvis OrchestratorAgent | **PIN and ADAPT** | E0 | Hook/executor semantics, timeout/reentrancy review | RECOMMENDED |
| OpenJarvis SimpleAgent | **KEEP for answers during transition** | E0 & E1 | Shared context/UX contract; avoid permanently split truth paths | RECOMMENDED |
| Upstream MemoryService/FactStore | **INVESTIGATE + TEST CONSENT GAP** | E1 | Auto-capture, local storage, expiry/delete, owner isolation | CANDIDATE |
| Upstream memory search/SQLite index | **INVESTIGATE** | E1 optional | Provenance and stale-cache semantics | CANDIDATE |
| Upstream GUI | **INVESTIGATE UX/API integration** | E0/E1 | Auth, process ownership, Node, app shell, task-state UI | CANDIDATE |
| Upstream SchedulerStore | **DEFER adoption** | E2 | Revocation, durable identity/retry safety | INVESTIGATION |
| Upstream FileRead/FileWrite | **DO NOT ENABLE YET** | E1/E2 | Canonical paths, overwrite consent, idempotency, read-back | CANDIDATE |
| Upstream provider connectors | **DO NOT ENABLE YET** | E2 | Credentials, network exposure, precise grants, licence | CANDIDATE |
| RIGHTWARE Shared Intelligence Core | **SEPARATE cross-repo audit** | Optional | API/licence/zero remote-server requirement | NOT AN E0 BLOCKER |

**Key architecture recommendation:** reuse selectively through explicit trust boundaries and small interface adapters. Do not make OpenJarvis the whole product authority; do not duplicate useful upstream modules without a failure-based reason.

## 6. Current code-to-proposed control-plane interface map

~~~mermaid
flowchart LR
  Text["User text UI"] --> Entry["Proposed RIGHTWARE trusted request router"]
  Voice["Future VoiceLoop adapter"] --> Entry
  Entry --> Intent["Proposed intent/context adapter"]
  Intent -->|"Simple answer"| Simple["Pinned SimpleAgent + Ollama"]
  Intent -->|"Allowed task"| Session["Existing RIGHTWARE AgentSession"]
  Session --> Policy["Existing AgentPolicy"]
  Policy --> Tools["Existing broker: web/browser + allowed WindowsActions"]
  Session --> Ledger["Existing A2 opt-in receipts"]
  Ledger --> Complete["Existing A3 opt-in completion gate"]
  Complete --> Reply["Unified user-visible result state"]
  Simple --> Reply
  Memory["Optional upstream fact store + RIGHTWARE consent wrapper (UNAPPROVED)"] -.-> Intent
~~~

**This is a *proposed* migration boundary, not a claim that these components are now connected.**

### Incremental design constraints

1. Introduce **one trusted request ingress/response envelope** without replacing successful A1–A3 code.
2. Route direct answers to a low-cost model path; only activate tool-bearing agent under explicit capability scope.
3. Preserve RIGHTWARE tool authorization and audit at execution boundary; no upstream generic tool self-grants.
4. Expose task-completion evidence only when opt-in contract and receipts are valid, never from text.
5. Test old \`chat\`, \`voice\`, \`agent\` parity, then gradually move product UX to one route; no one-shot destructive refactor.
6. Keep local memory disabled pending consent/data lifecycle approval; optional upstream extraction cannot silently activate.
7. Do not assume frontend and backend can bind to LAN without authentication; require local security review.
8. Plan explicit version adapters, not direct import of unstable internal upstream APIs where feasible.

## 7. Read-only test and evidence requirements before code adaptation

| Test/inspection | Reason | Current proof |
|---|---|---|
| Source snapshot: pin, gitlink, Python imports | Dependency reproducibility | Pin and selected class signatures inspected |
| Full upstream \`LICENSE\` and subdependency attribution review | Commercial distribution boundary | Partial; Apache-2.0 source presence only |
| Upstream \`tests/memory/*\` run on pinned venv | Memory behavior, deletion and locking | NOT RUN |
| New RIGHTWARE opt-in memory consent/sensitivity tests | Prevent silent private data capture | NOT DESIGNED/NOT RUN |
| Upstream GUI local/auth/Node tests | Safe shell reuse | NOT RUN |
| Agent A/B regression test across old/new entrypoints | No silent permission expansion | Existing tests only old paths |
| A2 callback/worker timeout mutation | No late misattribution | Existing A2 scoped tests PASS historically |
| Real Qwen bounded task recovery with model/provider version | LLM actually follows continuation feedback | NOT RUN |
| Real Windows app launch/audio tests | Pilot user-ready evidence | NOT RUN |
| Signed/versioned deployment and privacy model | E1 distribution | NOT DEFINED |

## 8. Revisions to earlier analytical statements

- **JRV-005 remains correct** that **no durable RIGHTWARE personal-memory subsystem was identified as integrated in the product path**; WP-02 adds that the **pinned OpenJarvis upstream has its own durable FactStore/MemoryService and memory CLI**.
- **JRV-005 remains correct** that **no RIGHTWARE calendar/mail/general file adapter is registered in the current \`AgentSession\`**, but the upstream repository has generic adapters that may be adapted with separate policy.
- **JRV-006/WP-08's phrase "design then build durable memory" is now too narrow**: explicitly investigate upstream consent-fit/reuse first.
- **JRV-006/WP-07's new UI recommendation must first compare the pinned upstream GUI**, rather than assume building an interface from scratch.
- **JRV-006/WP-12's durable task ledger need is NOT satisfied simply by upstream SchedulerStore**: recurrence/run logs are separate from A2 execution identity and idempotent recovery.
- Existing blueprints should be annotated/versioned rather than silently rewritten; this report is the additive source-backed correction.

## 9. Blocking design decisions and engineering handoff

### WP-02 findings resolved

- **Vendor pinned and version identified**: \`f21d902f4d3bd7f0f3f138f1a4613019a394b549\`.
- **Licence signal identified**: Apache-2.0 top-level; third-party checks still needed.
- **Three RIGHTWARE entrypoints confirmed**: chat, voice, agent with different controller semantics.
- **A1–A3 integration boundary identified**: opt-in only and absent from normal \`agent.cli\` flags.
- **Upstream reuse candidates confirmed**: memory store/service, GUI, scheduler store and file adapters.
- **Timeout/concurrency risk identified**: vendor orchestrator hook + executor worker behavior.

### Decisions remaining OPEN

1. Upstream GUI vs a new minimal product shell.
2. Upstream FactStore with consent wrapper vs separate RIGHTWARE memory store; privacy and retention obligations.
3. Exactly which upstream tool adapters can pass independent RIGHTWARE authorization and evidence checks.
4. Whether memory automatic extraction is explicitly forbidden, allowed by opt-in, or limited to certain classes.
5. First device and hardware/voice configuration.
6. Product model/router API and compatible request/response schema.
7. Commercial dependency/redistribution and model-weight licences.
8. Separate operator authorization for real Qwen and Windows tests; A4 remains separate.

## 10. Acceptance and next bounded action

**WP-02 R01 completed as read-only source investigation**, not a runtime validation or security certification. Selected upstream code was fetched at the exact pinned revision; no execution or change to vendor occurred.

**Recommended next gate:** approve the WP-01 E0/E1 detailed UC scope plus an **implementation-neutral WP-04 interface/compatibility design**; run separate, expressly authorized upstream GUI/memory focused tests before deciding whether to build replacements. The first code implementation must be a small, independently approved slice with A1–A3 negative-regression requirements.

**No code changes, vendor updates, new agents, memory services or A4 are authorized by this WP.**
