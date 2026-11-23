# JRV-007 — Engineering Roadmap, Release Gates & Execution Governance

**Product:** RIGHTWARE JARVIS v2.0  
**Version:** 1.0 — initial release-planning proposal  
**Date:** 2026-11-14  
**Status:** DOCUMENTED / PROPOSED; review and explicit operator approval required  
**Authority:** Planning only. This file authorizes **no product-code changes, A4, live model runs, Windows execution, installation on a customer's device, external API changes, releases, merges to main, schedules or expenditure.**  
**Source baseline:** JRV-001–006, particularly JRV-005 code audit pinned at \`f4a50e5075d0b94f635b1540885a0f2bd5258bc8\`; JRV-006 source HEAD \`12eb60134e6f1664a8e94b9d3eb2da3722e91aaa\`.  
**Head at roadmap start:** \`bd435a720b1f609d92ac52a59dfcdb19b4038bc5\` (\`develop\`), product/foundation CI success on same SHA.  
**No invented delivery dates:** durations, staffing and costs cannot be responsibly established without target hardware, operator-approved release scope and empirical throughput.

## 1. Objective

Convert the RIGHTWARE JARVIS product definition, 81 proposed capabilities, 33 use cases, 10 behavioural contracts, architectural interfaces, implementation audit, and 20 documented gaps into a **controlled work program** with:

1. Explicit, limited release envelopes and **non-goals**.
2. Ordered milestones and dependency gates.
3. Fourteen stable work packages (\`WP-01\`–\`WP-14\`) mapped to source gaps and use cases.
4. Safe parallelism and a **single authoritative integration plan**.
5. Concrete evidence demanded for every deliverable.
6. User experience, security, memory, voice and model test acceptance.
7. Decision authority, checkpoints, change control and a reusable Claude/Codex mission template.
8. A readiness decision separate from "tests green."

**Most important implementation insight:** current \`chat\`, \`voice\` and \`agent\` are distinct execution experiences. A1/A2/A3 are useful, tested opt-in components on \`AgentSession\`; they are **not** activated through the standard \`agent\` CLI and are not shared by \`chat\` or \`voice\`. Closing this integration gap without weakening the existing policy is the central near-term architectural task.

## 2. Decision vocabulary and approved-vs-proposed boundaries

| Term | Interpretation |
|---|---|
| VERIFIED IMPLEMENTATION | Source exists and applicable recorded tests/CI passed for a bounded behavior |
| EXPERIMENTAL | A limited test harness or prototype exists; not an integrated production feature |
| PROPOSED SCOPE | Product requirement selected in this document but **not approved** |
| RECOMMENDATION | Engineering guidance awaiting decision |
| OFFICIAL DECISION | Explicit operator approval or later approved decision record |
| ACTIVE IMPLEMENTATION | Work separately authorized with branch/HEAD/scope/gates |
| ACCEPTED RELEASE | Approved use-case set passes recorded integration, real-model, hardware and safety gates |

All JRV-001–007 blueprint matrices are **authored but not yet collectively approved**. Publishing them does not automatically turn architectural recommendations into official decisions.

## 3. Release envelopes — proposed roadmap contracts

### E0 — Internal coherent text alpha (proposed)

**User:** RIGHTWARE engineers/testers.

**In scope only if approved:**
- Local-first text conversation in Portuguese through **one coherent user-facing entrypoint**.
- Context handling for ambiguity, corrections, references and missing information, supported by a fixed Portuguese test corpus.
- Real-Qwen text/agent smoke with known, permission-safe synthetic fixtures.
- Expose task status, denied/pending/partial/unknown outcomes distinctly; do **not** claim a side effect from model prose.
- Any enabled tool effect must pass RIGHTWARE authorization and code-verified outcome reporting; no-action mode is default.
- Reproducible setup and diagnostics, published capability limitations and fail-closed safety regression.
- Retain existing A1/A2/A3 opt-in behavior and regression guarantees.

**Explicit E0 non-goals:** persistent personal memory, wake word, voice hardware acceptance, arbitrary shell control, general email/calendar/file modification, cross-restart task resumption, original-document \`COMPLETE_VERIFIED\` without a trust rule, multiuser accounts, scheduled background autonomy, production Windows installer and A4 approval.

**E0 exit:** real-model conversational tests + deterministic negative safety tests + user-visible integrated behavior; target thresholds must be approved before acceptance. Green unit CI alone is insufficient.

### E1 — Issa pilot on target Windows device (proposed)

**In scope only if approved:**
- All accepted E0 functionality on explicitly recorded compatible hardware.
- Speech input and output in Portuguese tested in the target audio environment; wake word is **conditional on explicit scope/measurement**, not automatically required.
- Opt-in durable **limited preference memory**, with provenance, local privacy, correction and deletion; prove restart persistence.
- At least one genuinely useful approved Windows action, beyond a false "done" reply, with a real process/result postcondition and explicit user confirmation.
- Simple user interface for chat, status, consent, memory and cancellation; no developer notebook needed.
- Install/diagnostic and rollback or documented safe recovery tested on target system.
- A documented list of **supported actions**, forbidden actions and model/hardware limitations.

**E1 non-goals unless separately approved:** arbitrary OS autonomy, unsupervised destructive actions, all third-party integrations, multi-device sync, full automation scheduler, commercial subscription platform, automatic recovery of irreversible external operations.

**E1 exit:** user acceptance on a named target device, safety checks, operator-controlled privacy and permissions and measured real usage. A successful Kaggle notebook is not E1 acceptance.

### E2 — Operational assistant (strategic option)

**Conditional scope:** durable task ledger with side-effect reconciliation/idempotency and post-crash resumption; typed adapters for approved file/calendar/mail/browser flows; richer task planner/verifier by objective class; persistent scheduler only if specifically authorized and revocable. Original-document authenticity verification only after trusted identity policy and evidence source exists.

### E3 — Extensible commercial product (strategic option)

Packaging, licensing, multiuser isolation if required, support/update/security operations, future device compatibility and optional local reuse of RIGHTWARE Shared Intelligence Core. None is yet a committed product feature, business model, schedule or pricing decision.

## 4. Release and engineering control gates

| Gate | Trigger | Minimum evidence | Decision type |
|---|---|---|---|
| RG-00 — Architecture approval | Before new roadmap implementation | JRV-001–007 reviewed; approved scope and excluded cases; device/consent constraints resolved or explicitly left open | Operator decision |
| RG-01 — Repository baseline | Before each engineering mission | Exact remote \`develop\` SHA, HANDOFF, CI, current branch, tree and PR safety; rollback plan | Engineering checkpoint |
| RG-02 — Security preservation | Before enabling any action path | Policy grants, exact args, host/SSRF protection, audit fail-closed, timeout/late handling and non-effect tests; no privilege expansion | Security/code review |
| RG-03 — Component quality | After work package | Unit/integration/fake tests, negative fixtures, lint/type gates where available, pinned venv no skips and CI success exact SHA | Technical verification |
| RG-04 — Integration equivalence | Before unified control plane is considered usable | Chat/voice/agent routing matrix, A/B default-off parity, linked receipts and truthful task status through user surface | Cross-component validation |
| RG-05 — Real-model acceptance | Before E0 claim | Fixed Portuguese corpus, pinned Qwen/Ollama/model context, manual evaluation, repeatability and guarded tool tests | Real-model review |
| RG-06 — E0 internal alpha | After RG-01–05 | E0 scope checklist, usability sample, security fixture results, limitations documented, owner sign-off | Internal acceptance |
| RG-07 — Durable memory/privacy | Before E1 memory claim | Owner scoping, consent/revocation, atomic write, restart read, edit/delete, index invalidation, no secret leakage | Privacy/security acceptance |
| RG-08 — Windows/voice acceptance | Before E1 | Real target hardware, STT/TTS recordings or safe metrics, action launch verified, approvals, cancel, install/rollback | Device acceptance |
| RG-09 — E1 Issa pilot acceptance | After RG-06–08 | Pilot scenario transcript with permission, completed task outcomes, operator/user feedback and supported-device manifest | Product/user acceptance |
| RG-10 — Operational recovery | Before E2 durable automation | Crash injection, task journal reconciliation, idempotent retries, duplicate-effect negative cases, policy revocation | Reliability review |
| RG-11 — Release/distribution | Before publish/ship | Dependency/licence review, signed or integrity-checked package, tested install/update, support/rollback and privacy notice | Release approval |
| RG-12 — A4 (separate milestone) | Only after explicit authorization | Dedicated scoped WORK-07 end-to-end acceptance plan and exact code/model/device snapshot | **NOT AUTHORIZED** |

**Pass semantics:** \`PASS\`, \`FAIL\`, \`BLOCKED\`, \`NOT_TESTED\`, \`NOT_APPLICABLE\` must be distinguished. For not-applicable, cite approved scope. No future gate becomes PASS merely by completing another one.

### 4.1 Mandatory negative controls (no release if known controlled fixture fails)

- No unauthorized tool effect or policy bypass.
- No fabricated side-effect success (including unexecuted/late/orphan calls).
- No \`COMPLETE_VERIFIED\` for original documents with \`identity_rule=NONE\`.
- No false permanent-memory claim from session context only.
- No duplicate external write after an uncertain timeout/retry.
- No secret exfiltration through prompt injection.
- No silent execution after cancellation/authorization revocation.
- No skipped tests in the pinned mandatory suite.
- No release claim based exclusively on FAKE model or Kaggle environment results.

A zero count in a bounded fixture set is **not** a statistical guarantee for production. Statistical/latency targets await baseline and sample-size decisions.

## 5. Work-package register — fourteen actionable engineering missions

Each WP below is scoped as a **candidate mission**. Owners are functional roles, **not named employees or assignments**. No WP is authorized to modify code by this document.

| WP | Deliverable and bounds | Origin gaps | Major UC/CT links | Dependencies | Proposed wave | Acceptance/evidence |
|---|---|---|---|---|---|---|
| WP-01 | Approved first-release scope, non-goals, target hardware, risk matrix, UCs and capability manifest | GAP-004,017 | UC-001–005,020,029,030; CT-01,03,08,10 | JRV-001–007 review; operator decisions DG-01/02/08 | W0 | Approved scope table + acceptance corpus/version |
| WP-02 | Vendor/OpenJarvis API, licensing and A1–A3 security boundary audit, migration compatibility | GAP-018,001,005 | UC-022–028; CT-06–09 | Pinned vendor, CI, HANDOFF | W0 | Source/path/pin/API map, threat review, A/B regression plan |
| WP-03 | Portuguese intent/context evaluation corpus and routing decision contract | GAP-002,017 | UC-001–005,013; CT-01–03 | WP-01 labels; model interface | W0 parallel | Reproducible prompts, expected referents, corpus rubric, failure taxonomy |
| WP-04 | Unified application control plane for text/agent and future voice adapters, preserving policy path | GAP-001,003,005 | UC-001–005,012,022,027; CT-01,06–09 | WP-02/03; privacy/security review | W1 | One trusted ingress, parity tests and zero bypass paths |
| WP-05 | User-visible task/result states, opt-in A1–A3 wiring where appropriate, evidence-aware response | GAP-005,007,020 | UC-022–028,033; CT-03,06–09 | WP-04; existing A1–A3 and approved contract IDs | W1 | Proved denial/partial/unknown; A/B default-off; no false verified success |
| WP-06 | Real Qwen end-to-end agent/repair benchmark on bounded safe fixtures | GAP-013,017 | UC-001–005,021–024,032; CT-01–03,07,10 | WP-03/04/05; explicit real-model permission | W1 | Pinned model/hardware/seed/context, transcript, independently adjudicated results |
| WP-07 | Local product interaction shell, task progress, approvals, errors and capability manifest | GAP-003,020 | UC-001–005,016,026,033; CT-01,03,08 | WP-01/04; interface security | W1 + W2 | No-code user flow, exact approval/denial, accessibility/error tests |
| WP-08 | Durable opt-in preference memory with provenance, consent, delete/edit and restart verification | GAP-005,006,007,012 | UC-008–011; CT-04,05 | Privacy policy DG-04; storage decision; WP-07 | W2 | Atomic commit, restart recall, deletion/invalidation, denied-owner tests |
| WP-09 | Real Portuguese STT/TTS and optional wake word integration on target Windows machine | GAP-008 | UC-029; CT-01,03,08,10 | WP-01 hardware; WP-04/07; real audio permission | W2 | Mic/voice measures, safe fallback, false activation, cancel/consent |
| WP-10 | First approved narrow Windows action(s) with typed parameters, confirmation, independent postcondition | GAP-009,010 | UC-014 or 020; UC-026/027; CT-06–08 | DG-05; WP-04/05; target Windows hardware | W2 | Actual action completed/rejected on Windows with receipt/read-back |
| WP-11 | Repeatable install/doctor, local runtime/resource checks, safe upgrade/uninstall plan | GAP-016,017,020 | UC-030; CT-05,10 | Device specification WP-01; voice/model choices | W2 | Clean target-device install, model outage and rollback test |
| WP-12 | Durable task-event ledger and reliable restart recovery with idempotency/cancel | GAP-006,011,012 | UC-022–026,031,032; CT-04,07–09 | WP-08 storage policy; WP-05 receipt semantics | W3 | Restart/timeout/late external-effect fault injection, no duplicate writes |
| WP-13 | Trustworthy original-document identity verification, if research UC committed | GAP-007,014 | UC-021–024; CT-03,07 | DG-07; independent trusted source and negative corpus | W3 conditional | \`UNKNOWN_IDENTITY\` until trust rules proven, no false original |
| WP-14 | Approved file/calendar/mail/recurring adapters one at a time, never blanket OS access | GAP-009,010,015 | UC-007,014–019,031; CT-05–09 | WP-05/10/12; connector access; DG-09 | W3 conditional | Per-adapter policy, exact grants, provider ID/read-back/idempotency |

**Classification:** WP-01 is product decision/design; WP-02/03 are investigations/test artefacts; WP-04–14 require **separate explicit implementation authorization** once gates and evidence are reviewed. The roadmap must not become a blanket instruction to Claude/Codex.

### 5.1 Suggested functional ownership (without inventing staffing)

| Function | Accountabilities |
|---|---|
| Product owner / RIGHTWARE operator | Scope approval, user value, priority, release gates, user consent and external integrations |
| Agent & intelligence architecture | Intent/context, model contracts, orchestration and model reliability |
| Security & privacy engineering | Policy, trust boundaries, secrets, retention, confirmed effects, audit |
| Runtime / Windows engineering | Model lifecycle, device compatibility, audio, OS action adapters |
| Data / reliability engineering | Memory persistence, migrations, task journal, recovery and idempotency |
| UX / frontend | Conversation, notifications, approvals, evidence and user control |
| QA / verification | Scenarios, fixtures, reproducibility, negative tests and release acceptance |

One person or delegated agent may perform several functions; the labels imply neither a staffing plan nor costs.

## 6. Delivery waves and dependencies

~~~mermaid
flowchart TD
    Scope["W0: WP-01 Scope"]
    Vendor["W0: WP-02 Vendor/security audit"]
    Corpus["W0: WP-03 Context corpus"]
    Core["W1: WP-04 Unified control plane"]
    Truth["W1: WP-05 Evidence-aware responses"]
    UX["W1: WP-07 Local user surface"]
    Qwen["W1: WP-06 Real Qwen E2E"]
    E0["RG-06 E0 Internal alpha acceptance"]
    Privacy["W2: Privacy/storage design"]
    Memory["W2: WP-08 Durable memory"]
    Voice["W2: WP-09 Windows voice"]
    Action["W2: WP-10 Real safe action"]
    Install["W2: WP-11 Installer/doctor"]
    E1["RG-09 E1 Issa pilot"]
    Ledger["W3: WP-12 Durable task ledger"]
    Identity["W3: WP-13 Trusted document identity"]
    Adapters["W3: WP-14 Selected integrations"]
    E2["E2 Operational acceptance, if approved"]

    Scope --> Vendor
    Scope --> Corpus
    Vendor --> Core
    Corpus --> Core
    Core --> Truth
    Core --> UX
    Truth --> Qwen
    UX --> Qwen
    Qwen --> E0
    E0 --> Privacy
    Privacy --> Memory
    E0 --> Voice
    E0 --> Action
    E0 --> Install
    Memory --> E1
    Voice --> E1
    Action --> E1
    Install --> E1
    E1 --> Ledger
    E1 --> Identity
    E1 --> Adapters
    Ledger --> E2
    Identity --> E2
    Adapters --> E2
~~~

The graph is a **dependency model**, not a schedule. Privacy policy, hardware investigation and UI research may proceed in parallel with W0/W1 design. Whether E2 actually requires original-document identity depends on its approved feature scope; no unnecessary global blocker should be introduced.

### 6.1 Initial critical path

**Product decision → vendor/security and context contracts → single control plane → verified user-visible result → real-Qwen controlled E2E → E0 approval → Windows/memory/voice validations → E1 approval.**

Do not prioritize email/calendar/OS shell expansion ahead of an integrated and secure control plane.

## 7. Milestone exit criteria (measurable without inventing targets)

### W0 — Scope and engineering readiness

- \`WP-01\`: E0/E1 UC lists approved, plus \`NOT_IN_SCOPE\`, model/device matrix and action risk table.
- \`WP-02\`: pinned source/API and licence matrix, current A1/A2/A3 regression basis and relevant issue/CI state.
- \`WP-03\`: versioned Portuguese dialogue test dataset with explicit expected intent, correction and referent.
- \`RG-00\`: operator has approved or explicitly amended JRV baseline and scope.
- **Fail gate:** unresolved provider, vendor licence, security or missing target environment material to chosen scope.

### W1 — Coherent text alpha

- A single local user-facing route offers knowledge answer and authorized task path.
- No-action requests produce no tool effect; enabled tool requests cannot bypass \`AgentPolicy\`.
- Clear \`INCOMPLETE\`/\`UNKNOWN\`/\`DENIED\` states cannot be overwritten by fluent model claims.
- A1–A3 opt-in default-off invariants remain regression-checked.
- Test results include \`UNIT\`, \`FAKE\`, \`LIVE_MODEL\`, \`INTEGRATED\`; each tagged separately.
- Portuguese correction, reference/ambiguity cases are manually adjudicated on fixed corpus.
- \`RG-03\` pinned env and CI exact SHA green; \`RG-04\` parity; \`RG-05\` real model; \`RG-06\` internal acceptance.
- **Fail gate:** a single enabled side-effect path bypasses authority or misreports completion.

### W2 — Personal Windows pilot

- Limited durable preference record is opt-in; write verified, restart recall correct, correction/delete and cache invalidation pass.
- Voice Portuguese operates on the identified Windows environment; error and cancellation fallback tested, with quantitative evidence recorded.
- One or more explicitly approved Windows operations have real OS postcondition and permission proof.
- No misleading claims about unfitted connectors or generic OS autonomy.
- Fresh device installation/doctor/limited offline runtime tests documented.
- A user can review/cancel tasks and manage permitted memories and approvals in an interface without code.
- \`RG-07\` privacy, \`RG-08\` device, \`RG-09\` user acceptance signed off.
- **Fail gate:** a required voice/memory/action experience is demonstrated only with mocks or Kaggle.

### W3 — Operational reliability and expansion (conditional)

- Durable ledger survives restart and reconciles late/uncertain effects before redoing operations.
- Authoritative per-action verifiers, idempotent external sends and cancellation policy.
- Source authenticity rules before verified original claims.
- Every additional connector passes permission/consent/privacy and negative tests independently.
- Any recurring scheduler is revocable and scope-expiring.
- \`RG-10\` fault injection acceptance and relevant \`RG-11\` release packaging.
- **Fail gate:** automatic duplicate side effects after timeout/restart.

## 8. Test matrix and release-evidence tiers

| Tier | Example | What it proves | Does NOT prove |
|---|---|---|---|
| T0 STATIC | Source inspection and schema check | Design/structure or API presence | Correct execution |
| T1 UNIT | Local function tests with fake dependencies | Narrow deterministic behavior | Integrated tool or model outcome |
| T2 FAKE_INTEGRATION | AgentSession with FAKE model/tools and synthetic site | Policy, tool binding, recovery conditions under fixture | Real Qwen or real Windows |
| T3 LIVE_MODEL | Qwen/Ollama on known corpus and controlled safe tools | Model/provider behavior in specified environment | Actual hardware or external integrations |
| T4 REAL_DEVICE | Windows, microphone, TTS, allowed OS actions | Supported target hardware effects | Commercial reliability across machines |
| T5 FULL_INTEGRATION | Model + UI + policy + receipts + memory/tool + user state | Cross-component result in stated environment | Broad real-world reliability without sufficient samples |
| T6 USER_ACCEPTANCE | Issa accepts recorded pilot scenarios | Scope-specific usefulness and controls | Security certification |
| T7 RELEASE | Install/upgrade/dependency/privacy gates | Repeatable supported delivery | Every future environment or model |

**Every milestone test manifest must contain:** repo SHA, branch, vendor pin, model and digest/version, runtime/OS/GPU, prompt/config/corpus version, test ID, exact expected oracle, run status, number of samples, performance where measured, forbidden effects and reviewer decision.

### 8.1 Proposed traceability coverage

| Release | UC coverage (candidates only) | Primary JRV-003 acceptance fixtures |
|---|---|---|
| E0 | UC-001–005, UC-012/013, UC-022–024, UC-026–028, UC-030, limited UC-033 | AT-001/002/005/010–015/017/021–024 |
| E1 | E0 + UC-008–011, UC-020, UC-029, extended UC-033 | AT-003/004/016/020 plus real-device consent/voice/action suite |
| E2 | UC-007,014/015,017–019,025,031/032 and UC-021 when trusted identity scope approved | AT-006–009/018/019 and fault-injection extensions |

**Important:** E0 target is an internal alpha, so this **selection is not** a contractual promise for Issa or a production customer; operator may narrow further.

## 9. Acceptance scorecards — template for each release

~~~text
RIGHTWARE JARVIS RELEASE ACCEPTANCE
Release envelope: E0 / E1 / E2
Proposed or approved scope revision:
Product/branch/HEAD:
Vendor pin:
Windows/device/GPU/CPU/RAM:
Model/provider/version/context:
UI/voice build:
Data/consent policy revision:
Supported UC IDs:
Explicit excluded UC IDs:
Security-negative test manifest:
Test tiers completed: T0 ... T7
Results: PASS / FAIL / BLOCKED / NOT_TESTED / NOT_APPLICABLE
Known limitations:
Required operator approvals:
User feedback and consent evidence:
Decision: ACCEPT / REJECT / CONDITIONALLY_ACCEPT
Decision-maker/date:
Linked HANDOFF and CI runs:
~~~

**Conditionally accepted** cannot bypass a high-risk security fail gate; it is suitable only for documented noncritical limitations in a specifically limited experimental scope, not mislabeling as a production release.

## 10. Decision backlog — what RIGHTWARE must decide before coding

| Decision ID | Proposal to evaluate | Inputs needed | Status |
|---|---|---|---|
| DEC-01 | Adopt E0 text alpha and E1 Issa pilot as first two envelopes | JRV-001–007 review | OPEN |
| DEC-02 | Define the exact E0 use cases and required UI actions | UC/CT matrix, pilot goals | OPEN |
| DEC-03 | Name the target Windows version, CPU/RAM/VRAM and acceptable offline limits | Device inspection and model tests | OPEN |
| DEC-04 | Approve unified control plane boundary (one trusted dispatch authority) | Vendor/policy source audit | OPEN |
| DEC-05 | Set persistent-memory data classes, consent/retention/deletion rules | Privacy/UX design | OPEN |
| DEC-06 | Choose first one or two useful Windows actions, exact confirmation and permitted scopes | Issa pilot needs and safe adapter review | OPEN |
| DEC-07 | Choose whether voice wake is mandatory in E1 or a later feature | Audio/privacy/quality evidence | OPEN |
| DEC-08 | Define real-model quality thresholds, annotated corpus and test budget | Baseline empirical runs | OPEN |
| DEC-09 | Decide original-document identity policy if research original proof is promised | Threat model/trusted publisher root | OPEN |
| DEC-10 | Determine whether/how local Shared Intelligence Core code may be reused | Both repos source/licence/API audits | OPEN |
| DEC-11 | Define A4 acceptance scope and explicitly authorize it separately | WORK-07 milestone handoff & E0/E1 gates | **NOT AUTHORIZED** |
| DEC-12 | Decide distribution, updates, data backups and support obligations | Device/user/product economics | OPEN |

No DEC becomes official by being listed. Approval requires an operator decision with scope, timestamp and relevant reference.

## 11. Safe engineering mission template

Use this template **only after** authorization for a particular work package.

~~~markdown
# RIGHTWARE JARVIS — WP-XX / GAP-XXX

Type: APPROVED IMPLEMENTATION / APPROVED READ-ONLY INVESTIGATION
Business objective:
Approved UC/CT and JRV refs:
Operator authorization reference:
Exact branch/HEAD and target environment:

## 0. HANDOFF-FIRST
- Confirm remote/local branch HEAD, CI, worktree, PRs, vendor pin.
- Read docs/HANDOFF.md, latest accepted blueprint revisions and related issues.
- Preserve concurrent commits; no destructive reset/rebase.

## 1. Scope
- Files/interfaces permitted:
- Requirements and observable outcomes:
- Exclusions and features that remain OFF:
- Trust and permission boundaries:

## 2. Test contract
- Positive cases:
- Negative/adversarial cases:
- FAKE vs LIVE_MODEL vs REAL_WINDOWS execution tiers:
- A/B compatibility and known historical failure preservation:
- Required CI gates and exact SHA:

## 3. Work and checkpoints
- Begin checkpoint:
- Implementation in small reviewable commits:
- Re-run tests and inspect failures:
- Update append-only HANDOFF with accurate evidence and blocker:
- Do not start follow-up scope without a fresh explicit authorization.

## 4. End report
HEAD, commits, changed files, tests run/skipped, CI refs,
known risks, blocked items, recommended next work package.
~~~

The template does not enable autonomous implementation without permission, and cannot grant broader tool privileges.

## 12. Recommended execution management

### 12.1 Sequential decision, parallel investigation

- Scope review and security/API audit should precede structural code integration.
- A corpus for Portuguese context repair can be prepared alongside vendor investigation.
- The Windows device inventory and consent design can be investigated in parallel, but cannot dictate unsupported release claims.
- UI mockups/flow design may proceed in parallel with control-plane interface design, but should consume approved state/permission contracts.
- Shared Intelligence Core study remains nonblocking read-only research; any adoption requires explicit technical authorization.
- Product implementation should be divided into small commits and observable checkpoints instead of a single enormous code rewrite.

### 12.2 Backlog discipline

For each proposed issue: \`JRV-007/WP-XX/GAP-XXX/UC-XXX/CT-XX\`; owner function; dependencies; environment; acceptance; OFF flags; rollback; security review. Work-in-progress should not silently expand just because the model found an adjacent missing feature.

### 12.3 Documentation as the operating system

- \`docs/product-blueprint/README.md\` — matrix registry and statuses.
- \`JRV-001–007\` — architecture/product intent and planning.
- \`docs/HANDOFF.md\` — live chronological engineering checkpoint.
- \`docs/engineering/\` — specific implemented milestone evidence.
- \`tests/\`, \`qa/\`, \`labs/\` — evidence by tier, never promote FAKE to live product acceptance.
- Future \`docs/decisions/\` or ADR log only if operator approves ownership and schema; do not invent approved decisions.

## 13. Risks and open blockers to resolve during authorization

1. **Hardware is unknown:** Kaggle's Tesla T4 proves little about acceptable local inference latency on Issa's machine.
2. **Memory semantics:** transient conversation history cannot be marketed as cross-session personalization.
3. **Voice:** existing wrapper/mocked tests do not validate full Portuguese speech interaction in real environments.
4. **Vendor boundary:** pinned upstream timeout/thread semantics matter for correct receipts. Any upgrade requires a fresh investigation.
5. **Identity:** \`identity_rule=NONE\` is insufficient for authenticating original documents, and false \`COMPLETE_VERIFIED\` would be unacceptable.
6. **Unification risk:** collapsing chat/voice/agent carelessly could bypass policy or alter A1–A3 default-OFF parity.
7. **External integration risk:** file/email/calendar side effects demand consent, idempotency and trustworthy verification.
8. **Commercial ambiguity:** no pricing, market, staffing, release timeline or multiuser demand has been approved or supported by evidence.

## 14. Blueprint close-out and formal review protocol

All **seven JRV matrices have now been authored** as proposed architecture/evidence/planning documents. This is **DOCUMENTATION COMPLETE**, not **ARCHITECTURE APPROVED** and definitely not **PRODUCT COMPLETE**.

**Proposed approval sequence:**

1. Review JRV-001 product definition and 81 target capabilities.
2. Review JRV-002 33 use cases and provisional actors.
3. Review JRV-003 behavioural/negative test contracts.
4. Review JRV-004 technical options and architectural decision register.
5. Acknowledge JRV-005 implementation evidence and explicit limits.
6. Review JRV-006 first-release gaps, priority rationale and E0/E1 hypotheses.
7. Approve/revise JRV-007 release envelopes, decisions and next work package.
8. Issue **separate authorization** for any implementation, experimental Qwen runs, Windows hardware test or A4.

**Next concrete document after approval:** a small, approved **E0 Release Contract** (\`scope + UC IDs + safety constraints + acceptance oracle\`), followed by a delimited WP-01/WP-02 authorization. That is the bridge from roadmap to controlled coding.

**Critical final distinction:** RIGHTWARE now has a traceable conceptual product architecture and a source-backed implementation audit. The next engineering goal is a coherent assistant demonstrably operating end to end, not an ever-growing list of isolated completed modules.
