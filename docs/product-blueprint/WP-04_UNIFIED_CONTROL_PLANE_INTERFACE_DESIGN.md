# WP-04/D01 — Unified Control Plane: Interface & Compatibility Design

**Product:** RIGHTWARE JARVIS v2.0  
**Version:** Design draft D01 · **Date:** 2026-11-14 (Africa/Maputo)  
**Status:** IMPLEMENTATION-NEUTRAL DESIGN / FOR REVIEW — **no code implementation authorized**  
**Authorization:** Operator requested continuation of WP-03 + WP-04 specification and design after officially approving Blueprint reference and read-only WP-01/WP-02.  
**Source reference:** RIGHTWARE \`develop\` \`721e0ac15d846b44f7be9c0d2676813328de522b\` before this sequence; pinned \`open-jarvis/OpenJarvis@f21d902f4d3bd7f0f3f138f1a4613019a394b549\`.  
**Depends on:** JRV-001–008, WP-01, WP-02, WP-03, existing A1/A2/A3 and issue #9 acceptance constraints.  
**Do not:** modify \`rightware/\`, \`tests/\`, \`vendor/\`, \`configs/\`, CI, PRs, main; do not invoke Qwen/Windows or authorize A4.

## 1. Decision problem

The current RIGHTWARE product exposes three different experiences:

| Entry | Current implementation | Relevant limitations |
|---|---|---|
| \`python jarvis.py chat\` | \`runtime.chat_command()\` launches pinned upstream CLI \`SimpleAgent\` via Ollama | No RIGHTWARE A1/A2/A3 task execution/completion on this path |
| \`python jarvis.py voice\` | \`VoiceLoop\` → \`OpenJarvisBrain\` → upstream \`SimpleAgent\`; special Windows action detection | Separate context, action and completion representation; real hardware not accepted |
| \`python jarvis.py agent "pedido"\` | \`rightware.agent.cli\` → \`AgentSession\` → pinned \`OrchestratorAgent\` → RIGHTWARE policy/tools | Trusted preset/receipts/gate constructor options are default OFF and not exposed by public CLI |

**Architectural goal:** users should perceive **one JARVIS**, while the system internally chooses simple conversational answers, clarification or narrowly authorized task execution, each with consistent status and safety semantics.

**Critical constraint:** the common control plane must **not** pretend all 33 use cases are implemented, remove A1–A3 opt-in gates or cause the low-risk chat route to inherit agentic side effects.

## 2. Recommended minimum topology

~~~mermaid
flowchart TD
  Channel["Text UI (E0) / Voice adapter (E1 candidate)"] --> Ingress["RIGHTWARE Request Ingress"]
  Ingress --> Context["Session context + intent classification"]
  Context --> Choice{"Logical route"}
  Choice -->|"ANSWER / CLARIFY"| Simple["Pinned SimpleAgent / LLM"]
  Choice -->|"PLAN only"| Planner["Plan response, no side effects"]
  Choice -->|"TASK only with explicit capabilities"| Agent["RIGHTWARE AgentSession"]
  Choice -->|"CONTROL"| Control["Cancel / status / capabilities"]
  Choice -->|"MEMORY intent"| Memory["E0: explain unavailable; E1: consent-gated provider only"]
  Agent --> Policy["AgentPolicy / allow / budgets"]
  Policy --> Tool["Exact authorized tool, if any"]
  Tool --> Evidence["A2 receipts if enabled"]
  Evidence --> Gate["A3 evidence-aware completion if trusted contract"]
  Simple --> Normalize["Result projection, not proof minting"]
  Planner --> Normalize
  Control --> Normalize
  Memory --> Normalize
  Gate --> Normalize
  Normalize --> UI["User-visible reply + status/limits"]
~~~

**Implementation recommendation (not approved):** start with a **thin, locally callable facade** and existing engine wrappers; no microservices, remote backend, extra model/agent or separate task database should be introduced just to establish one response contract.

The topology is **logical**, not proof of implemented components, and only the \`AgentSession\` route may invoke the existing protected tools.

## 3. Contract C-01 — trusted request ingress

Illustrative schema (NOT a source API):

~~~json
{
  "schema": "JRV-WP04-REQUEST-1",
  "request_id": "runtime-generated",
  "session_id": "trusted-local-session",
  "channel": "text",
  "principal": "trusted-local-owner",
  "text": "Abre a calculadora",
  "capabilities": {"read_web": false, "browse": false, "windows_actions": false},
  "context_refs": [],
  "task_preset_id": null,
  "deadline_budget": null
}
~~~

**Invariants:**
1. \`request_id\`, \`principal\`, \`capabilities\` and actual grants are established by trusted host/UI, **not the model** or untrusted page.
2. User text cannot opt into a tool or trusted preset merely by naming it.
3. \`task_preset_id\` is either \`null\` or a host-selected existing trusted \`TRUSTED_PRESETS\` ID. A model-generated JSON contract is always untrusted.
4. E0 defaults to no side-effecting capabilities. A cancelled/expired request never grants a new tool call.
5. Session context may include prior user/assistant turns in memory; it must not claim durable history.

## 4. Contract C-02 — route decision (policy-neutral)

Suggested logical routes:

| Route | Entry condition | Executing subsystem | Expected outcome |
|---|---|---|---|
| \`ANSWER\` | Informational question; no action needed | SimpleAgent model response | Answer, uncertainty and no tool effect |
| \`CLARIFY\` | Essential missing referent/field cannot be resolved | Context/router; optionally LLM question | One direct clarification, no tool effect |
| \`PLAN\` | User wants steps/strategy, no execution requested | Model/structured planner | Proposed steps, **not** completion |
| \`TASK\` | User requests explicit operation and relevant trusted tools can be considered | AgentSession only, subject to grants | Authorize/execute/verify or deny/partial |
| \`CONTROL\` | Cancel/status/capability query | Runtime controller | Real state; cancellation stops new grants |
| \`MEMORY_INTENT\` | Save/recall/delete preference | E0 limitation reply; future E1 opt-in store | No fake durable memory claim |

**Security:** route selection is NOT permission. Classifier confidence/LLM output cannot override the policy gate. Quoted content and model hallucination cannot trigger tools.

**Behavioral authority:** if the model proposes a tool but no corresponding approved adapter/grant exists, the result must be \`DENIED\`/\`UNAVAILABLE\`/limited guidance, not executable.

## 5. Contract C-03 — trusted action decision & handoff

All tool-bearing tasks must pass through:
1. A capability registry of **actually exposed** product actions.
2. Approved exact tool name + canonical arguments, allowlist, destination scope and budget.
3. Required human confirmation for consequential action, bound to displayed arguments.
4. Existing \`AgentPolicy.before_tool_call\` and \`authorize_execution\` at real execution boundaries.
5. A2 \`ReceiptLedger\` **only if enabled**, recording actual call and results.
6. A3 completion assessment **only with an allowed trusted task preset and receipts enabled**.
7. No \`TaskContract\` promotion from raw user/LLM/browser text.

**Current implementation restriction:** the only RIGHTWARE Windows actions observed are \`notepad\` and \`calculator\`. Upstream \`FileWriteTool\` must **not** be made accessible by default: its existence and path checks are not equivalent to RIGHTWARE precise approvals, receipt semantics or overwrite-safe UX.

## 6. Contract C-04 — unified result without inventing proof

Proposed user-level response projection:

~~~json
{
  "schema": "JRV-WP04-RESULT-1",
  "request_id": "same-runtime-id",
  "route": "ANSWER|CLARIFY|PLAN|TASK|CONTROL|MEMORY_INTENT",
  "message": "texto visível ao utilizador",
  "operational_state": "ANSWER_ONLY|PLAN_ONLY|WAITING_INPUT|WAITING_APPROVAL|DENIED|INCOMPLETE|UNKNOWN|HALTED|ERROR|VERIFIED_EFFECT|NOT_APPLICABLE",
  "factual_verified": false,
  "effect_claims": [],
  "receipt_refs": [],
  "task_contract_ref": null,
  "objective_assessments": [],
  "limitations": [],
  "follow_up_required": false
}
~~~

These string values are **design-view categories**, NOT a request to rename \`AgentReply.completion\` or \`CompletionResult.state\`. A mapper should preserve the raw source state and mark the certainty of its provenance.

### 6.1 Status projection matrix

| Current source | Existing state / observation | Proposed UX representation | Guardrail |
|---|---|---|---|
| SimpleAgent text | Model message only | \`ANSWER_ONLY\` | No execution evidence |
| Plan text | No approved dispatch | \`PLAN_ONLY\` | Never “feito” |
| AgentPolicy denial | Rejected call | \`DENIED\` | Must reflect current call, not stale denial reason (#9) |
| AgentSession without contract | \`ANSWERED_WITH_SOURCES\` | “Sources observed; task success not assessed” | Source read ≠ completion |
| AgentSession Windows action | \`ACTION_VERIFIED\` only if observed | \`VERIFIED_EFFECT\` **for that specific OS action only** | Acknowledges limited scope, not multi-step success |
| Contracted A3 | \`INCOMPLETE\` | \`INCOMPLETE\` | Missing mandatory objective |
| Contracted A3 | \`UNKNOWN_IDENTITY\` | \`UNKNOWN\` + identity warning | Never \`VERIFIED_EFFECT\` |
| Contracted A3 | \`COMPLETE_VERIFIED\` | \`VERIFIED_EFFECT\` for contracted objectives only | Only if trusted proof exists |
| Any path | Timeout, orphan/duplicate, audit fail | \`UNKNOWN\` or \`ERROR\` as evidenced | Never fabricate clean success |
| Memory without durable store | Conversational response | “Apenas nesta conversa” | No implied persistent storage |

### 6.2 User-visible message rules

- Display source of evidence, not raw internal traces.
- Distinguish \`respondido\` from \`executado\` and \`verificado\`.
- Do not use a success badge for a partial or identity-unknown result.
- A tool receipt proves operation at a scoped boundary, **not factual correctness**.
- Every unavailable capability is visible in a capability manifest and honest message.

## 7. Contract C-05 — session context and correction

- E0 may maintain **bounded in-process conversation history** without calling it persistent memory.
- Context must contain trusted role and turn identity; untrusted retrieved pages should never appear as higher-priority instructions.
- An explicit user correction supersedes the active referent for the current conversation.
- If the referent is irrecoverable after truncation, ask; do not invent missing history.
- Model context window limits must be handled by explicit reduction or constrained retrieval, not silent misrepresentation.
- The 36-case [WP-03 Portuguese corpus](fixtures/WP03_PT_CONTEXT_CORPUS_v1.csv) is the first manually labelled evaluation fixture; it has NOT been executed.

**Design trade-off OPEN:** pass an upstream \`AgentContext\` versus a RIGHTWARE-owned normalized session record. The model, runtime and OS cost of each approach must be evaluated. Neither grants durable memory.

## 8. Contract C-06 — memory, voice and GUI as replaceable adapters

**Memory:** upstream at pinned SHA has \`LocalFactStore\` and \`MemoryService\` (auto-extracting), but E1 requires explicit user consent, deletion and owner scoping. Proposed \`IMemoryAdapter\` must be **default disabled** until those policies are approved; do not enable upstream background extraction as a shortcut.

**Voice:** existing \`VoiceLoop\` + \`OpenJarvisBrain\` can be a future *channel adapter* that passes trusted transcribed user requests into the same facade; do not allow separate voice-only policy bypass. Real STT/TTS/wake evaluation on Issa hardware remains pending.

**GUI:** upstream \`cli/gui_cmd.py\` and frontend exist, but product fit/security, app lifecycle, model UI and consent are untested. UI choice is OPEN. A minimal E0 text surface should first consume the same interface contract even if later UI changes.

**Scheduler/tools:** upstream \`SchedulerStore\`, generic file tools and channels must remain unavailable in the E0/E1 public tool catalog unless individually approved/tested.

## 9. Error handling, cancellation and durable state boundaries

| Scenario | Required response |
|---|---|
| Model unavailable | Explain local model issue without fabricated answer or tool effect |
| Unrecognized intent | Ask focused clarification or provide limited help |
| Permission denied | No dispatch; preserve reason for **this call** |
| Contract untrusted | Reject task-contract opt-in; no unintended tool scope |
| Approved not executed | \`NOT_EXECUTED\` receipt/flag and incomplete result |
| Tool timeout with late thread | Preserve uncertainty, account for pending effects and reject unsafe retry |
| User cancels | Stop new grants; do not promise rollback of already completed effects |
| Missing original identity | \`UNKNOWN_IDENTITY\`; never force \`COMPLETE_VERIFIED\` |
| Audit write fails | Fail closed; no verified completion |
| Process restarts | E0 cannot claim durable task resume; future E2 requires separate ledger |

A1–A3 default-OFF and byte-identical legacy behavior are required on non-opt-in paths where tests specify parity.

## 10. Implementation-neutral migration slices (not authorized)

| Slice | Proposed change after separate approval | Dependencies | Review proof |
|---|---|---|---|
| D01 | Define request/result contracts in an isolated adapter layer | WP-03 corpus; WP-02 interface audit | Pure schema/compatibility tests |
| D02 | Wrap current direct text-answer path without granting actions | D01 | No tool side effects; Portuguese reference tests |
| D03 | Wrap \`AgentSession\` protected tool path; expose existing statuses | D01/02; policy hooks | A/B security/receipt tests |
| D04 | Permit explicit trusted synthetic A1–A3 opt-in via host-selected preset | D03; exact confirmation | A1–A3 FAKE/negative regression; no default-on |
| D05 | Add local E0 user surface consuming facade | D02/03 | Accessible status + denial + limitations |
| D06 | Real Qwen test against versioned corpus and safe synthetic tasks | D04/05 + separate runtime authorization | T3 LIVE_MODEL transcript + reviewed results |
| D07 | Later adapt VoiceLoop to same ingress | E0 acceptance + E1 voice scope | Real Windows mic/voice acceptance |
| D08 | Later adapt consent-gated durable memory | E1 privacy/retention approval | Restart/delete tests, no auto-capture |

**No slice is authorized by this design.** The design should enable a small safe first implementation after the operator approves D01/D02 and its test contract.

## 11. Threat review and A1–A3 preservation matrix

| Security case | Existing evidence path | Must remain true after an eventual integration |
|---|---|---|
| Batch with one invalid tool | \`AgentPolicy.batch_guard\` | Entire invalid batch denied |
| Stale denial reason #9 | Issue #9 regression + \`_denial_reason\` | Current rejection cause reported |
| Tool loop/quotas | \`AgentPolicy\` counters/locks | No silent quota reset across retries |
| Call identifier attribution | \`ReceiptLedger.decide/claim/finish\` | Orphans, duplicates and late calls do not become trusted proof |
| Pending approved call | \`AgentSession._close_pending\` | Report \`NOT_EXECUTED\` rather than success |
| Identity of originals | \`completion.evaluate\` | HTTP 200, exact URL or raw hash alone insufficient |
| Contract authority | \`select_preset\` + validator | Only code-owned trusted preset can enable gate |
| Default OFF parity | \`AgentSession.__init__\`, A3 test | Ordinary sessions unchanged |
| No web privilege by default | Session allow flags | No tool from text or model without grant |
| Voice/tool separation | \`VoiceLoop.handle\` | Eventually same policy; before then disclose split capability |
| External prompt injection | Browser/site model prompt + policy | External instructions cannot elevate trust |

**Risk:** pinned upstream \`OrchestratorAgent\` uses tool scheduling including threads; any wrapper must preserve receipt correlation and bounded continuation. Avoid refactoring internal execution before auditing concurrent callback semantics. Existing RIGHTWARE \`parallel_tools=False\` does not, by itself, prove all late-thread outcomes are harmless.

## 12. Test contract and required evidence

| Test ID | Tier | Oracle | Current status |
|---|---|---|---|
| INT-001 | STATIC / T1 | Trusted request envelope fields not sourced from model output | PROPOSED, NOT RUN |
| INT-002 | T1/T2 | No tools for knowledge query and quoted imperative | PROPOSED, NOT RUN |
| INT-003 | T2 | No tool if capability flags are off, even if model proposes call | PROPOSED, NOT RUN |
| INT-004 | T2 | \`AgentPolicy\` denies invalid mixed batch, no action | Prior tests exist; new integration NOT RUN |
| INT-005 | T2 | A2 bound receipt prevents orphan/duplicate proof | Prior tests exist; new integration NOT RUN |
| INT-006 | T2 | A3 preserves \`UNKNOWN_IDENTITY\` for originals without trust root | Prior tests exist; new integration NOT RUN |
| INT-007 | T2 | Legacy without contract matches expected A/B behavior | Prior A3 tests exist; new integration NOT RUN |
| INT-008 | T2 | Current denial reason not stale; preserves issue #9 correction | Prior issue #9 tests exist; new integration NOT RUN |
| INT-009 | T2/T3 | Context correction and referent samples PTX-001–036 | Corpus authored; NOT RUN |
| INT-010 | T3 | Qwen actually routes one safe contracted task and follows feedback | NOT AUTHORIZED / NOT RUN |
| INT-011 | T5 | User sees correct status/limitations without reading raw logs | NOT IMPLEMENTED / NOT RUN |
| INT-012 | T4/T5 | Real Windows action/voice cannot bypass policy in unified route | E1 conditional; NOT RUN |
| INT-013 | T2 | Cancel stops new grants; late operation not misreported as rolled back | Prior narrow tests exist; new integration NOT RUN |
| INT-014 | T1/T2 | Memory disabled in E0 never claims durability | PROPOSED / NOT RUN |

**Evidence labeling:** \`T0 static\`, \`T1 unit\`, \`T2 fake-integrated\`, \`T3 live-model\`, \`T4 real-device\`, \`T5 integrated user surface\`. A green CI on current code cannot automatically mark INT-001–014 PASS because these tests have not been implemented.

## 13. Open interface decisions — operator/architecture review

| Decision ID | Open choice | Why it matters |
|---|---|---|
| IF-01 | One runtime-owned session store or normalized wrapper around \`AgentContext\` | Context quality and no duplicate state |
| IF-02 | Deterministic routing vs model-assisted routing vs staged combination | Latency, confidence and failure behavior |
| IF-03 | Local CLI/TUI shell first vs upstream GUI integration | E0 usability, security and distribution |
| IF-04 | Method of exposing A1–A3 opt-in to users without untrusted preset IDs | Policy and product UX |
| IF-05 | Exact distinction between response status and task completion status | Prevent false success |
| IF-06 | Which actions count as E0 safe synthetic task vs real E1 action | Release scope |
| IF-07 | Consent-gated upstream memory adapter vs separate storage | E1 privacy/deletion |
| IF-08 | Who owns request cancellation / worker lifetime and late-effects reconciliation | Safety |
| IF-09 | Minimum quality metrics after live Qwen baseline | Future release gate |
| IF-10 | Which upstream APIs are stable enough to wrap vs copy | Maintenance/licensing |

## 14. Recommended first next mission after review

The next implementation authorization should be **narrow**, ideally \`WP-04/D01–D02\` only: define a typed local request/response boundary and wrap the current *no-tool* text answer path; preserve all existing tests and A1–A3 flags. This would give a testable vertical slice **before** adapting dangerous tool pathways or creating new memory storage.

Before that, the operator should approve the proposed interface decisions and identify whether a minimal CLI/TUI text experience is acceptable for E0. Separately authorizing safe upstream memory/GUI **read-only validation** could reduce duplicate build effort.

**This file contains design contracts only. No executable code was changed, no benchmark was run, no A4 started, no new dependency added.**
