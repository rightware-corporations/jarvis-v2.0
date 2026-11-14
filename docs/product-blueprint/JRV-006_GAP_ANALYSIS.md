# JRV-006 — Gap Analysis, Dependency Graph & Engineering Priorities

**Product:** RIGHTWARE JARVIS v2.0  
**Version:** 1.0 — proposal for architecture-to-delivery conversion  
**Date:** 2026-11-14  
**Status:** ANALYSIS AUTHORED / RECOMMENDATIONS PENDING OPERATOR APPROVAL  
**Authority:** Documentation only; no A4, code changes, vendors, deployment, release or model/Windows experiments authorized.  
**Primary input:** [JRV-005 — Source-backed implementation audit](JRV-005_IMPLEMENTATION_AUDIT.md) at code audit SHA \`f4a50e5075d0b94f635b1540885a0f2bd5258bc8\`.  
**Current baseline at start:** \`develop\` HEAD \`12eb60134e6f1664a8e94b9d3eb2da3722e91aaa\`, CI WORK-05 \`43603809652\` and foundations \`43603809583\`, \`43603814332\`: SUCCESS. No new production implementation at that HEAD versus the audited code snapshot; later commits were Blueprint/HANDOFF documentation.  
**Source hierarchy:** JRV-001 (81 target capabilities), JRV-002 (33 use cases), JRV-003 (10 shared contracts, 24 acceptance fixtures), JRV-004 (10 proposed modules and 12 ADR candidates), JRV-005 (verified code paths and test evidence).  
**Next:** JRV-007 — scoped, dependency-based engineering roadmap, acceptance gates and release architecture decisions.

## 1. Executive conclusion

**Finding:** RIGHTWARE has successfully implemented narrow opt-in components for trusted task contracts (A1), runtime-bound execution receipts (A2) and deterministic completion assessment (A3), supported by green CI and FAKE-model regression tests. However, those components do not yet form a coherent end-user JARVIS experience.

Three production entrypoints currently remain separate:

1. \`jarvis.py chat\` — upstream SimpleAgent CLI through Ollama.
2. \`jarvis.py voice\` — RIGHTWARE voice loop with upstream SimpleAgent and narrow WindowsActions.
3. \`jarvis.py agent\` — RIGHTWARE AgentSession, policy, browser, actions and optional A1–A3 **at constructor level**, without A1–A3 flags wired into ordinary CLI.

**Engineering implication:** the next high-value work is **product integration under one trusted control plane**, not simply expanding tool count or adding a new framework. More tools without reliable context, policy, evidence, runtime state and UX would increase risk.

**Crucial boundary:** a missing capability in the *target product* is not necessarily a blocker for a narrowly scoped release. First decide what a release promises; then determine its critical path.

## 2. Status and evaluation method

The following grades are used:

| Grade | Meaning |
|---|---|
| V — VERIFIED_SCOPE | The specific narrow implementation path has inspected tests and CI evidence |
| P — PARTIAL | Some implementation exists but scope, integration or real-environment acceptance is incomplete |
| U — UNVERIFIED | Code/path exists; real target behaviour has not been validated |
| A — ABSENT_IN_AUDITED_PATHS | No corresponding product component was found in the inspected RIGHTWARE paths |
| X — EXTERNAL/UNKNOWN | Depends on vendor, hardware, third-party API or unverified data |
| D — DECISION_REQUIRED | Release/product architecture choice necessary before binding implementation |

**Planning priority bands** are qualitative; not invented risk scores:

- **P0 foundation** — prerequisite to multiple other capabilities, safety or coherent user experience.
- **P1 pilot** — needed for the suggested Issa pilot but may be deferred from a narrower internal alpha.
- **P2 expansion** — improves usefulness after initial core acceptance.
- **P3 research** — optional, uncertain, or long-term exploration.

The labels are **proposed priority**, not an approved backlog or a budget/schedule.

## 3. Proposed release envelopes — to avoid unbounded scope

| Envelope | Intended user | Proposed must-have acceptance boundary | Explicitly not claimed | Status |
|---|---|---|---|---|
| **E0 — Internal text alpha** | RIGHTWARE testers | One coherent local text surface with intent/context repair, strict tool-policy boundary for any enabled action, truthful task states, install diagnostics, deterministic negative tests and real-model smoke | Voice acceptance, durable memory, unattended execution, broad tool portfolio | **RECOMMENDATION** |
| **E1 — Issa personal pilot** | Issa on an identified Windows device | E0 plus Portuguese voice interaction, clearly scoped persistent preferences/memory with deletion, at least one useful approved local action end-to-end, reliable feedback/consent UI, tested restart/install path | General-purpose autonomous OS access, arbitrary shell, all integrations, multi-user SaaS | **RECOMMENDATION** |
| **E2 — Operational assistant** | Repeated personal use | Trusted multi-step tasks, durable task ledger, idempotent recovery, expanded adapters and measured success per task type | Full unsupervised autonomy or verified source authenticity without independent identity rule | **HYPOTHESIS** |
| **E3 — Extensible/commercial platform** | Multiple supported users/devices | Install/update channel, security isolation, supportability, optional sync and reusable component architecture | Licensing and customer scale not yet validated | **STRATEGIC OPTION** |

**Why two early envelopes?** E0 allows a controlled engineering release without pretending that the voice/Windows product is ready. E1 respects the intended personal JARVIS value proposition; it cannot be called accepted before voice, persistent memory and target-device behaviour are actually demonstrated. **The operator must approve/revise E0/E1 scope in JRV-007.**

## 4. Detailed gap register

The IDs **GAP-001–GAP-020** are stable planning identifiers. Origin F-* maps to JRV-005 findings; JRV IDs/UCs map to prior matrices.

| GAP | Area / source | Current evidence | Missing target or proof | Priority / envelope | Key dependency | Acceptance evidence |
|---|---|---|---|---|---|---|
| GAP-001 | Unified control plane; F-001/F-004 | Three separate entrypoints; A1–A3 opt-in only in Python constructor | One trusted request route for chat/voice/tool execution, with opt-in task contracts and no privilege expansion | **P0 / E0** | GAP-002, GAP-003, GAP-005 | A/B no-action + integrated text/tool tests |
| GAP-002 | Intent & context; F-011 | LLM context in SimpleAgent; no RIGHTWARE-specific repair controller found | Routing, ambiguity handling, correction and contextual reference tests | **P0 / E0** | Portuguese corpus, GAP-003 | UC-001–005/AT-001–002 and negative ambiguity cases |
| GAP-003 | User-facing surface; F-012 | CLI + experimental Kaggle chat | Local chat/task-status/approval UI and clear distinction between draft, action, verified, unknown | **P0 / E0; P1 richer E1** | GAP-001, GAP-005 | Usability scenarios incl. partial/denied and actual approval |
| GAP-004 | Product release scope; JRV-001–005 | Requirements proposed; E0/E1 not approved | Choose exact first-release UCs, hardware, limitations, risk and quality gates | **P0 decision** | Operator + baseline | Signed-off scope/ADRs and exit checklist |
| GAP-005 | Policy and receipts on unified path | \`AgentPolicy\`, A1/A2/A3, tests and green CI | Ensure any enabled user-visible side effect is consistently authorized, receipted, verified and not claimed falsely across routes | **P0 / E0** | GAP-001; existing A1–A3 preservation | Tool allow/deny, timeout, duplicate, audit fail and report alignment tests |
| GAP-006 | Durable memory; F-005 | Conversation history transient; no RIGHTWARE durable user memory store identified | Consent-governed preference store, owner scoping, retrieval, edit and delete across process restart | **P1 / E1** | GAP-007, GAP-012 | AT-003/004 restart-delete/cross-owner fixtures |
| GAP-007 | Memory/consent policy; CT-04/05 | Scoped tool confirmation and redacted audit; no general memory policy | Data classification, retention, deletion, redaction, authorization, backups/keys | **P0 design / E1 implementation** | Operator security decision, GAP-004 | Negative privacy tests and consent UI evidence |
| GAP-008 | Target Windows voice; F-010 | \`voice.py\`, STT/TTS wrappers, fake tests | Real mic, STT Portuguese, TTS, wake if in scope, cancellation and latencies on Issa machine | **P1 / E1** | GAP-004 hardware, GAP-001, GAP-003 | Real-device E2E plus acoustic corpus; no FAKE substitute |
| GAP-009 | Local useful actions; F-008/009 | Only Notepad and Calculator; fake process tests | Prioritized real Windows actions and typed adapters with per-action verification | **P1 / E1, P2 expansion** | GAP-004, GAP-005, GAP-010 | Actual Windows observed process + receipt/postcondition |
| GAP-010 | Action-risk approval & trust; CT-08 | Two actions have confirmation and policy | Risk classification for future file/send/delete/calendar actions; exact-argument grants, idempotency | **P0 policy design; P1+ adapter-specific** | Operator, GAP-004 | AT-008/009/014–016 with fail-closed negatives |
| GAP-011 | Durable task ledger; F-006 | A2 receipts + A3 gate in memory | Persist task state/events, reconcile side effects after crash and cancel | **P2 / E2** | GAP-007, GAP-005, GAP-012 | AT-012/013/019 restart/retry idempotency |
| GAP-012 | Durable storage architecture; ADR-004 | No RIGHTWARE user-memory/task DB identified | Transactional schema, owner keys, migration, encryption/backup strategy | **P1 prerequisite E1** | GAP-007, target OS and threat model | DB integration, migration and crash tests |
| GAP-013 | Real Qwen integration with A3; F-013 | Qwen comparisons separate, A3 only FAKE | Real-model agent feedback and recovery on pinned model/runtime | **P0 validation E0** | GAP-001, corpus/tool fixtures | Live Qwen E2E on synthetic non-dangerous tasks; classify outcomes |
| GAP-014 | Trusted document identity; F-007 | Two synthetic presets; identity_rule NONE | Independently trusted identity rules for originals, or explicit UNKNOWN_IDENTITY | **P2 for original-doc use case; not E0/E1 blocker unless promised** | Security decision, source trust anchor | AT-010/011, 0 false claims in negative suite |
| GAP-015 | Broader adapters (files, calendar, mail); F-009 | No corresponding product tool registry adapters | Individually approved schemas, connectors, confirmed side-effects and read-back | **P2 / E2** | GAP-005, GAP-010, per-provider access | UC-014–019 contracts, idempotency and real provider evidence |
| GAP-016 | Packaging/install/update; F-010/F-014 | Python launcher/doctor, Windows script and CI | Reproducible Windows install, model download checks, support/rollback path | **P1 / E1** | GAP-004 hardware, GAP-008 | Fresh Windows installation + recovery check |
| GAP-017 | Acceptance baselines; F-014 | JRV-003 metrics defined, target values TBD | Corpus/sample sizes, p50/p95 latency, memory footprint, safe claims and real device acceptance | **P0 methodology E0; P1 E1 data** | GAP-004, GAP-002, GAP-013 | Versioned datasets and independently reviewed outcomes |
| GAP-018 | Vendor compatibility/licence; F-015 | Pinned \`vendor/openjarvis\`, partial wrapper audit | Boundaries/third-party licences, API stability, replaceability and dependency security | **P0 review E0 before architectural migration** | Pinned vendor tree/code review | API/LICENCE matrix, supported pin decision |
| GAP-019 | Shared Intelligence Core reuse; JRV-004 ADR-009 | Separate RIGHTWARE project referenced | Local reusable interfaces/licensing/coupling, no required external server | **P3 research** | Both repos at pinned SHAs, GAP-018 | Read-only comparison, cost/security trade-off |
| GAP-020 | Documentation/status clarity; F-016 | README and historical architecture lag newer A1–A3 | Clear current/experimental/target status, no false readiness statements | **P0 housekeeping** | Handoff and source evidence | Updated status matrix and verified docs |

### 4.1 Scope-specific non-blockers

For **E0**, the following are *not automatically required*: wake word, durable user memory, calendar/email connectors, a multi-user service, original-document verification \`COMPLETE_VERIFIED\`, persistent task scheduler or Shared Intelligence Core integration. Their omission must be explicit in the E0 capability manifest.

For **E1**, voice, scoped durable memory and actual Windows validation are **proposed core acceptance requirements**. Their readiness cannot be inferred from the success of A1–A3 or the Kaggle demonstration.

## 5. Critical dependency model

~~~mermaid
flowchart TD
  SC["GAP-004 Approve scoped release"]
  VA["GAP-018 Vendor/API review"]
  QA["GAP-017 Acceptance corpus / test harness"]
  CTX["GAP-002 Context/intent"]
  CTRL["GAP-001 Unified control plane"]
  SEC["GAP-005 Unified policy/receipts"]
  UI["GAP-003 Local interaction UI"]
  REAL["GAP-013 Real Qwen agent validation"]
  E0["E0 internal text alpha gate"]
  CONS["GAP-007 Consent + data policy"]
  DB["GAP-012 Transactional local store"]
  MEM["GAP-006 Durable memory"]
  ACT["GAP-009 Useful actions"]
  RISK["GAP-010 Action risk policy"]
  VOICE["GAP-008 Target Windows voice"]
  PKG["GAP-016 Install/packaging"]
  E1["E1 Issa pilot acceptance"]
  LEDGER["GAP-011 Durable task ledger"]
  ADAPT["GAP-015 Extended integrations"]
  ID["GAP-014 Original-doc identity"]
  E2["E2 operational assistant"]
  SC --> VA
  SC --> QA
  VA --> CTRL
  CTX --> CTRL
  CTRL --> SEC
  CTRL --> UI
  SEC --> REAL
  QA --> REAL
  UI --> E0
  REAL --> E0
  SEC --> E0
  SC --> CONS
  CONS --> DB --> MEM
  RISK --> ACT
  SEC --> ACT
  E0 --> VOICE
  E0 --> PKG
  MEM --> E1
  ACT --> E1
  VOICE --> E1
  PKG --> E1
  E0 --> E1
  E1 --> LEDGER
  LEDGER --> E2
  ADAPT --> E2
  ID --> E2
~~~

**Interpretation:** this DAG is a **proposed dependency ordering**. E2's precise gates depend on its approved scope; the illustrative ID and extended-adapter arrows are optional if their associated use cases are not promised. Context design and consent policy can be investigated in parallel; implementation requiring shared interfaces should not begin without the control-plane contract.

## 6. Critical path and workstream parallelism

### 6.1 Immediate common critical path — recommended

1. **Scope gate:** approve/revise E0 and E1 promises, supported Windows hardware, available models, permissions and actions.
2. **Compatibility gate:** confirm OpenJarvis vendor boundary, rights/licensing and the current A1–A3 invariants before refactoring.
3. **Context/router contract:** define route-to-answer vs route-to-task, session referents, correction and failure statuses.
4. **Single user-facing control plane:** add one trusted UI-to-agent execution API without migrating all underlying modules at once.
5. **Policy/receipt parity:** ensure tool effects via every enabled route still pass RIGHTWARE policy and truthful completion checks.
6. **Real-model evidence:** run Qwen in the controlled real-agent path using the same versioned Portuguese corpus and fake-site fixtures; compare against deterministic tests.
7. **E0 acceptance:** manual usability + safety controls, then advance to Windows-specific E1 integration.

**Do not** first implement arbitrary file/email/calendar tools merely to increase the number of features.

### 6.2 Independent or conditionally parallel workstreams

| Stream | Can start independently | Must converge before |
|---|---|---|
| INTELLIGENCE | Corpus for ambiguous Portuguese, context repair, routing tests | Unified control plane E0 |
| AGENT & SECURITY | A1–A3 regression and policy/receipt preservation review | Any feature path with effects |
| MEMORY | Consent design, data model and delete/restart test specification | E1 persistent memory claim |
| VOICE | Hardware preflight, STT/TTS/wake feasibility on Windows | E1 voice acceptance |
| EXPERIENCE | User flows, error states, approval UI and accessibility | E0 integrated usability |
| PLATFORM | Vendor/API/license review, packaging/hardware matrix | E0 migration and E1 installation |
| INTEGRATIONS | Candidate useful actions inventory, risk ratings | E1 real action tests |
| SHARED CORE | Read-only interface reuse study | No gating dependency on E0/E1 |

No workstream is automatically an independent team, repository, service or authorized implementation branch.

## 7. Priority matrix by value, uncertainty and safety

| Candidate work package | User value | Architectural leverage | Integration/safety risk | Recommended order | Reason |
|---|---|---|---|---|---|
| WP-01 Product scope & target-device definition | High | High | Low decision, high uncertainty | **1** | Prevents making every target feature a blocker |
| WP-02 Vendor and A1–A3 boundary audit | Medium direct | High | High if skipped | **2** | Protects functioning security invariants |
| WP-03 Intent/context test corpus | High | High | Medium | **2 in parallel** | Early quality baseline and known failure mode |
| WP-04 Unified control-plane design/integration | Very high | Very high | High | **3** | Closes principal fragmentation gap |
| WP-05 Unified completion/policy user result | High | High | High | **4** | Stops false "done" in user-facing path |
| WP-06 Live Qwen agent E2E benchmark | High | High | Medium | **5** | Distinguishes FAKE success from real model |
| WP-07 Local user experience and approvals | High | High | Medium | **3–5 in slices** | Enables realistic user pilot tests |
| WP-08 Consent and durable memory | High for Issa | High | High privacy/data | **E1, start design early** | Prevents false persistent-memory claims |
| WP-09 Real Windows audio/STT/TTS | High for Issa | Medium | Hardware/performance | **E1, investigate in parallel** | Original product voice requirement |
| WP-10 Useful safe Windows action | High | Medium | OS/safety | **E1 after policy gate** | Demonstrates action, not chatbot only |
| WP-11 Installation/diagnostics | High | Medium | Medium | **Before E1 pilot** | Makes product repeatable |
| WP-12 Durable task event recovery | High for operational use | High | High | **E2 unless E1 scope requires it** | Avoids non-idempotent replay |
| WP-13 Original-doc trust mechanism | Conditional | Medium | High correctness | **Only when research UC in scope** | \`UNKNOWN_IDENTITY\` is correct until proven |
| WP-14 External connectors and automation | Conditional | Medium | High provider/privacy | **After first integrated acceptance** | Expands coverage with clear boundaries |

**Priorities are deliberative, not statistically estimated.** No invented implementation duration, cost, CAC, resource count, percentage completion, or absolute release date is claimed.

## 8. Risk and failure-mode register

| Risk ID | Scenario | Severity if relevant | Exposure | Mitigation / test |
|---|---|---|---|---|
| RSK-01 | Tool action bypasses policy via chat/voice route | Critical | Split paths | Centralize authorization; test every action ingress |
| RSK-02 | False completion after an unexecuted/late call | Critical | Timeout worker + LLM claims | Preserve A2 binding/A3 gate and deny unproven completion |
| RSK-03 | Persistent memory falsely claimed | High | Transient session context | Separate durable confirmation from ephemeral recall |
| RSK-04 | Personal information leak or undeletable memory | High | New persistence | Consent, encryption/key decisions, deletion/cached retrieval tests |
| RSK-05 | Model misunderstands correction | Medium–High | Known Portuguese dialogue failure | Versioned dialogue tests and repair gating |
| RSK-06 | Infinite retries or duplicate external side effects | Critical if integrations added | Tool timeouts and restart | Idempotency and reconcile-before-retry |
| RSK-07 | Vendor API upgrade breaks receipt correlation | High | Pinned executor behavior | Pin validation and A/B regressions |
| RSK-08 | Qwen runs poorly on target hardware | High for local pilot | Kaggle T4 differs from Windows PC | Hardware profiling, fallback and truthful compatibility |
| RSK-09 | Voice falsely activates or mishears action | High | Unvalidated real STT/wake | Confirm risky actions by independent UI/user channel |
| RSK-10 | Original-document identity inferred from URL | High for research UC | identity_rule NONE | Require trusted expected identity; preserve UNKNOWN |
| RSK-11 | Release promises unsupported tools | High product trust | Feature mismatch | Capability manifest, explicit E0/E1 gates |
| RSK-12 | Shared Core creates remote dependency and coupled failure | Medium | Unreviewed reuse | Optional local adapter, explicit interface/licence review |

Risk labels are **qualitative planning judgments**, not evidence of observed vulnerabilities or incidents.

## 9. Reuse / build / adapt choices — provisional

| Component | Current asset | Recommendation | Decision trigger |
|---|---|---|---|
| AgentPolicy | RIGHTWARE existing code | **REUSE and preserve** | A/B+security test compatibility |
| A1 contracts/A2 receipts/A3 completion | RIGHTWARE code, opt-in | **REUSE; integrate through trusted control plane** | Real E2E, bounded scope, typed contracts |
| OpenJarvis OrchestratorAgent | Pinned external vendor | **ADAPT behind interface**, avoid broad fork | Licence/API/timeout review |
| SimpleAgent chat and VoiceBrain | Upstream wrappers | **TRANSITION carefully**, avoid parallel permanent truth paths | Integration equivalence and UX |
| Browser/web reads | RIGHTWARE scoped adapters | **REUSE for public read**; no silent generalization to auth browser | New threat model for higher-risk capabilities |
| WindowsActions | Two fixed actions | **REUSE for narrow pilot actions**; expand with typed adapters only | User need, OS test, authorization |
| Session context | AgentContext and model messages | **KEEP as ephemeral**, do not call durable memory | Approved memory data lifecycle |
| Persistent memory/task ledger | No verified RIGHTWARE implementation | **DESIGN then BUILD/ADAPT** | Consent, retention, storage strategy |
| Voice STT/TTS | Existing wrappers, fake tests | **REUSE subject to real hardware tests** | Portuguese latency/quality/privacy |
| User interface | CLI / notebook | **DESIGN new product surface** or adapt lightweight UI | E0 acceptance, install/security |
| Shared Intelligence Core | Separate RIGHTWARE project | **INVESTIGATE only** | Code/licence/API/availability evidence |
| External calendar/mail/file tools | No verified core adapters | **DEFER until approved UC scope** | Security/idempotency/provider access |

## 10. Explicit decision gates (operator approval required)

| Gate | What is decided | Evidence before decision | Status |
|---|---|---|---|
| DG-01 | E0 alpha must-have use cases and exposed controls | UC/CT shortlist + negative fixtures | OPEN |
| DG-02 | E1 Issa pilot voice/memory/action commitments | Issa needs, Windows hardware, consent | OPEN |
| DG-03 | One shared control-plane strategy and migration order | Path evidence + vendor boundary | OPEN |
| DG-04 | Memory data policy and local storage | Privacy, backup/deletion threat model | OPEN |
| DG-05 | First approved Windows tool action set | Security tier, reversible effects, OS test | OPEN |
| DG-06 | Real-Qwen benchmark and safety corpus | Hardware, model pin, fixture, permissions | OPEN |
| DG-07 | Document identity trust anchor if originals in scope | Publisher/digest trust definition | OPEN |
| DG-08 | Thresholds for E0/E1 acceptance | Measured baselines, negative fixture suite | OPEN |
| DG-09 | External provider / Shared Core integration | API, licence, security and operational costs | OPEN |
| DG-10 | A4 acceptance mission if/when desired | Relevant integration gates and explicit scope | NOT AUTHORIZED |

The user saying "continue the matrices" approves producing **planning documentation**, not the implementation, closing issues, choosing models, changing privacy policy or authorizing A4.

## 11. Recommended engineering control policy

Before authorizing a work package:

1. Associate a \`WP-\` and \`GAP-\` with \`UC-\` and \`CT-\` IDs.
2. Pin the code baseline SHA and document overlapping branches/PRs; do not destructively reset.
3. Name affected trust boundaries and original tests that must remain valid.
4. Define an observable acceptance predicate and its required execution environment.
5. Distinguish \`UNIT\`, \`FAKE\`, \`LIVE_MODEL\`, \`REAL_WINDOWS\`, \`INTEGRATED\` and \`USER_ACCEPTED\` evidence.
6. Demand negative/adversarial tests for side effects and a default-off / A/B regression when adding optional capabilities.
7. Close checkpoints only when exact SHA CI and Handoff show evidence, with explicit remaining risks.
8. A failed gate is \`FAIL\`/\`BLOCKED\`, not silently deferred to a later "success" claim.

## 12. Dependency-oriented proposed execution waves

These are **logical waves**, not dates or automatic permissions:

| Wave | Work packages | Completion condition |
|---|---|---|
| **W0 — Product scope** | WP-01, WP-02, WP-03 kickoff, WP-07 UX research | DG-01/02/03 recorded; source baseline, fixture scope and architecture decisions traceable |
| **W1 — Coherent text agent** | WP-04, WP-05, WP-06, WP-07 thin slice | One user-facing path, policy/receipt parity, Portuguese repair tests and real Qwen smoke |
| **W2 — Issa pilot readiness** | WP-08, WP-09, WP-10, WP-11 | Authorized memory + deletion/restart, Portuguese voice and one real Windows action, install + safe UX |
| **W3 — Operational reliability** | WP-12, WP-13 if promised, WP-14 selected | Durable task recovery, per-action identity/evidence and approved provider adapters |
| **W4 — Productization** | Distribution, wider compatibility, maintenance and expansion | Approved release/cybersecurity and user acceptance gates |

W1 does **not** imply that A1–A3 should be permanently hidden behind test-only constructor flags; it means product wiring must be designed, authorized and regression-checked. W2 is not equivalent to all JRV-001 capabilities.

## 13. Decisions and change control

**FACTS:** A1/A2/A3 documented as opt-in tested components; \`chat\`, \`voice\`, \`agent\` use distinct paths; no verified durable personal memory; Windows actions currently restricted; full real Windows voice and Qwen A3 recovery not yet accepted.

**RECOMMENDATIONS:** E0 text alpha followed by E1 Issa pilot, one control plane, persistent memory with governance, a small real action set, and measurable release gates.

**OPEN:** User-approved E0/E1 requirements, voice hardware envelope, memory policies, exact tool set, vendor upgrade strategy, document identity, model/hardware benchmark targets and A4 scope.

**NOT AUTHORIZED:** Code modifications, release, merge main, external integration, background automations, live model experiments or A4.

## 14. Exit criteria and handoff to JRV-007

JRV-006 is **authored for review**, not a signed-off roadmap. This document contains 20 labelled gaps, 12 strategic risks, 14 work packages, 10 approval gates, a dependency graph, parallel workstreams, scoped release hypotheses and ordered engineering waves. It is grounded in JRV-005 and should be re-audited if code changes alter its evidence.

**JRV-007 must deliver:**

- Approved-or-proposed release scope per E0/E1/E2, with an explicit NOT-IN-SCOPE list.
- Work-package backlog mapping to GAP/UC/CT, dependencies, owners (only roles, not fabricated people), and acceptance tests.
- A deliverable-by-deliverable checklist and evidence templates for Claude/Codex work.
- No unsourced schedules, costs or "percent complete" claims.
- Product security and privacy decisions requiring explicit approval.
- A dedicated integrated test plan, platform-specific checks, and actual user acceptance gate.
- A pathway for A4 authorization independent of architecture documents.
- An explicit place for unresolved Shared Intelligence Core reuse and document identity research.

**Recommendation:** seek operator review of JRV-001–006 and prioritize the *coherent assistant experience* over accumulating disconnected framework features.
