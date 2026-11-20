# JRV-008 — Blueprint v1.0 Formal Review & Decision Register

**RIGHTWARE JARVIS v2.0**  
**Version:** Review packet 1.0  
**Date:** 2026-11-14  
**State:** REVIEWED FOR DECISION — recommendations issued; **not an approved baseline**  
**Authority:** No implementation, A4, model execution, vendor upgrade, Windows action, release, privacy policy or paid API authorization.  
**Reference baseline:** \`develop\` \`d664d3ae564bc8fdaddf1d250f5fd171ed653359\` before this review.  
**CI checked:** foundation \`43604910872\` and \`43604914364\`, product \`43604910837\`: SUCCESS on the exact reference SHA.  
**Sources:** JRV-001–007, JRV-005 pinned source audit and \`docs/HANDOFF.md\`.

## 1. Purpose: decision-ready review, not a new specification

The seven Blueprint matrices are authored and source-backed where appropriate. They are NOT automatically official company decisions. This review identifies the elements recommended for adoption as a **provisional engineering reference**, the contentious or incomplete elements requiring explicit operator decisions, and a concrete E0/E1 release contract proposal.

The phrase "vamos então" authorizes continuing this **review process**, not by itself any unlimited implementation, product release, calendar commitment, privacy policy or A4 milestone.

## 2. Review result by matrix

| Matrix | Scope | Review result | Condition before approval |
|---|---|---|---|
| JRV-001 | 81 target capabilities / 10 systems | **ACCEPTABLE AS TAXONOMY PROPOSAL** | Mark capabilities as targets, not mandatory E0 functions; confirm product definition |
| JRV-002 | 33 UCs / actor journeys | **ACCEPTABLE WITH SCOPE QUALIFICATION** | Issa is initial pilot persona; multiuser and recurrent tasks remain hypotheses |
| JRV-003 | Behavior / 24 acceptance fixtures | **ACCEPTABLE AS TEST DESIGN BASIS** | Set test sample sizes and release thresholds later; reconcile proposed states with actual A3 |
| JRV-004 | Modular architecture / interfaces / candidate tech | **CONDITIONALLY ACCEPTABLE** | No new service or DB until a real adapter/threat/reuse analysis; Python/Ollama/SQLite are candidates |
| JRV-005 | GitHub implementation audit | **VALID AS PINNED, SELECTIVE AUDIT** | Does not cover every vendor file/security path; re-pin before implementation |
| JRV-006 | 20 gaps / 14 WPs / dependencies | **ACCEPTABLE AS PRIORITIZATION PROPOSAL** | Severity applies to chosen release; hardware and customer priority remain unvalidated |
| JRV-007 | Release envelopes and engineering gates | **CONDITIONALLY ACCEPTABLE** | Operator must approve E0/E1 promises, target device and first bounded work package |

**Readiness judgment:** DOCUMENTATION READY FOR OPERATOR DECISION; not automatically ARCHITECTURE APPROVED, CODE READY, PRODUCT ACCEPTED or RELEASE READY.

## 3. Proposed baseline decisions — seek explicit operator approval

| Decision | Recommended resolution | Why | State |
|---|---|---|---|
| REV-01 | Define JARVIS as independent RIGHTWARE product; OpenJarvis as selectively reusable implementation dependency | Prevent framework-driven product scope | RECOMMENDED |
| REV-02 | Adopt ten JRV systems/81 capabilities as versioned **target taxonomy**, not mandatory immediate scope | Preserves full product vision without scope explosion | RECOMMENDED |
| REV-03 | Adopt E0 internal text alpha, then E1 Windows voice/personal pilot as **planning envelopes** | Distinguishes tested integration from real user readiness | RECOMMENDED |
| REV-04 | Keep a modular local-first architecture as preferred design; do not mandate microservices | Simpler deployment, lower coupling, security boundaries | RECOMMENDED |
| REV-05 | Make policy + evidence + task truth independent of the LLM; preserve A1–A3 gates | Avoid false action completion and unsafe autonomy | RECOMMENDED |
| REV-06 | Integrate \`chat\`, \`voice\`, \`agent\` gradually behind a trusted control plane; no unsafe one-shot rewrite | Resolves main JRV-005 gap | RECOMMENDED |
| REV-07 | Require real-Qwen and real-target Windows evidence separately from FAKE-model tests | Prevent fake environment proof from becoming release claims | RECOMMENDED |
| REV-08 | Treat memory as opt-in, scoped, durable only if actually persisted; privacy rules require an explicit decision | User trust and safety | RECOMMENDED |
| REV-09 | Preserve \`UNKNOWN_IDENTITY\` for original documents until a trusted publisher/identity rule exists | No identity from HTTP 200 alone | RECOMMENDED |
| REV-10 | Keep Shared Intelligence Core reuse optional and subject to a separate cross-repo interface/licence audit | Avoid forced remote dependencies and hidden complexity | RECOMMENDED |

None of REV-01–10 is recorded as an **OFFICIAL DECISION** yet.

## 4. E0 — Proposed internal text-alpha release contract

### 4.1 Exact candidate use-case scope

**Mandatory candidate UCs**:
- \`UC-001\` factual questions;
- \`UC-002\` ambiguity resolution;
- \`UC-003\` conversational repair;
- \`UC-004\` reference continuity;
- \`UC-005\` honest uncertainty;
- \`UC-012\` bounded planning for a task;
- \`UC-013\` required clarification;
- \`UC-022\` restricted synthetic multi-step task via trusted contract;
- \`UC-023\` independent goal assessment in approved fixtures;
- \`UC-024\` honest partial/unknown status;
- \`UC-026\` cancellation of allowed active work;
- \`UC-027\` authorization refusal;
- \`UC-028\` resistance to untrusted external instructions;
- \`UC-030\` model/runtime doctor.

**Limited UX acceptance for \`UC-033\`:** user can see intent/task status, errors and approval outcomes, not a promise of durable task history. **Original-doc \`UC-021\` remains a synthetic negative test** only; \`COMPLETE_VERIFIED\` must never be claimed without independent identity.

### 4.2 Required interfaces

- One local text entrypoint whose capability manifest shows what is actually implemented and enabled.
- Direct answer route for simple conversation; no tool call for a no-tool question.
- Trusted agent task path with RIGHTWARE policy authorization, bound execution receipts and user-visible evidence classification.
- Clear user-visible distinction between \`ANSWER_ONLY\`, \`PLANNED\`, \`DENIED\`, \`INCOMPLETE\`, \`UNKNOWN\`, \`HALTED\`, \`ERROR\`, and verified operational effects where actually supported; mapping to existing \`AgentReply\` and A3 states must avoid rewriting current enums prematurely.
- Exit/cancel/disable actions and transparent logs without exposing secrets.
- Model/provider identity and supported-resource diagnostics.

### 4.3 E0 excluded features

No promise of durable memory, always-on background work, voice/hotword, arbitrary filesystem write, email/calendar sending, desktop-wide automation, cross-restart execution recovery, production installer, multiuser isolation, full authenticated web browsing or general document original authenticity. No task contract automatically trusted because a model generated it.

### 4.4 E0 gate proposal

| Gate | Acceptance predicate | Evidence tier |
|---|---|---|
| E0-G01 | Pinned \`develop\` HEAD, clean worktree, vendor pin & license/API boundary reviewed | T0 + CI |
| E0-G02 | No-action simple question does not invoke tool; context correction/referents evaluated against approved Portuguese corpus | T2 + T3 |
| E0-G03 | All enabled actions pass the RIGHTWARE policy; denied calls have no side effect | T1/T2, controlled integration |
| E0-G04 | A1/A2/A3 opt-in integration truthful; 404, info-only, orphan, timeout, audit fail do not report full success | T2/T3 |
| E0-G05 | Default-off route retains legacy A/B behaviour where explicitly required and no unsafe permission expansion | T2 + snapshot comparison |
| E0-G06 | Qwen model actually runs through coherent agent path on bounded synthetic fixtures | T3 LIVE_MODEL |
| E0-G07 | User sees status and limitations without reading internal raw traces or code | T5 INTEGRATED + reviewer |
| E0-G08 | Security-negative fixtures and pinned suite PASS at exact SHA, with 0 skipped tests in required venv | T1/T2 + CI |
| E0-G09 | Latency, memory, context-repair and task-correctness measured against versioned corpus; thresholds chosen from real baseline | T3 measurements |
| E0-G10 | Internal scope reviewed and signed off, with unsupported functions explicitly documented | Operator acceptance |

**Safety tests:** zero accepted forbidden effects/false success in the controlled negative fixture set is a release gate, not a statistical zero-risk claim. No invented latency/accuracy percentages before actual baselines.

## 5. E1 — Proposed Issa Windows pilot contract

**Add to accepted E0 only:**

- \`UC-008–011\`: durable *limited preferences* memory with provenance, consent, edit/delete and read-after-restart.
- \`UC-020\`: at least one useful selected Windows action actually verified by OS observation; policy confirmation required.
- \`UC-029\`: real Portuguese STT/TTS on the target machine, fallback when audio fails. **Wake-word activation is a separate decision** and cannot be silently omitted if the operator considers it defining the product.
- \`UC-033\`: interface with readable task status, consent and local memory management.
- \`UC-030\`: repeatable setup/doctor and tested environment recovery.

**E1 exclusions by default:** arbitrary OS control, all third-party integrations, general recurring automation, full durable multi-step task engine, and commercial multiuser product.

**E1 acceptance:** on-record target Windows version/hardware, model and speech engine versions, consent/retention policy approved, live voice/microphone tests, approved actual OS action with positive and denied cases, cross-restart memory retention/deletion, installation/restart and pilot user review. E1 is blocked if essential proof comes only from FAKE or Kaggle.

## 6. Critically unresolved choices

| Code | Topic | Current safe placeholder | Decision needed |
|---|---|---|---|
| OPEN-01 | First-release practical utility | E0 narrow safe tasks; E1 one Windows action | Does user want real file management in first pilot? |
| OPEN-02 | Target device | Unknown; no hardware baseline asserted | CPU/RAM/GPU, OS, mic/speaker, offline requirements |
| OPEN-03 | Mandatory wake word | Voice in E1; wake optional until decision | Is "Jarvis" voice activation a mandatory E1 feature? |
| OPEN-04 | Consent/memory | No persistent memory enabled by this review | Retention period, sensitive categories, encryption, deletion |
| OPEN-05 | Model quality threshold | Unknown until baseline | Approved corpus, latency budget and quality/error tolerances |
| OPEN-06 | UI | Local application shell vs securely bound local web UI | UX/packaging/security decision |
| OPEN-07 | A4 | Explicitly not authorized | Separate bounded end-to-end milestone |
| OPEN-08 | Original-doc identity | \`UNKNOWN_IDENTITY\` | Trust root + verifiable expected identity |
| OPEN-09 | Shared Intelligence Core | No integration dependency | Local code reuse after source audit |
| OPEN-10 | Commercial rollout | No commitment | Licensing/support economics and devices |

These are **gates**, not invitations to infer missing personal/device facts.

## 7. Recommended next engineering mission after approval

**First authorize \`WP-01 + WP-02\` as READ-ONLY/SPECIFICATION work**, never as a blanket code refactor:
- \`WP-01\`: lock E0 scope, explicit exclusions, select target machine baseline and define accepted safe tool surface.
- \`WP-02\`: inspect pinned OpenJarvis API/license and A1/A2/A3 invariants, chart \`chat\` vs \`voice\` vs \`agent\` boundaries, and deliver a non-destructive integration design with test contract.

An implementer can subsequently work on \`WP-03\` Portuguese corpus in parallel, but product-code changes should wait for \`WP-04\` targeted authorization with agreed interface. The existing PR #1 and \`develop\` historical checkpoints remain preserved.

## 8. Operator decision protocol

To approve the proposed conceptual baseline, record an **explicit written decision** covering:
1. \`REV-01–10\` or named exceptions.
2. E0 internal text-alpha candidate UCs/exclusions and E1 pilot minimum promises.
3. Scope of \`WP-01 + WP-02\` read-only work if desired.
4. Material open constraints that are left pending, clearly labelled as pending rather than invented.

**Approval of architecture is not authority to implement all WPs.** \`A4\` still needs a separate decision.

### Suggested decision wording (DRAFT — NOT AN APPROVAL)

> APPROVE JRV-001–007 as RIGHTWARE JARVIS Blueprint v1.0 architectural reference subject to JRV-008 conditions, with E0 and E1 as proposed release envelopes. Authorize WP-01 and WP-02 for read-only specification/investigation, excluding code changes, A4, deployments, real Qwen/Windows tests and new dependencies. Device specifics, memory policy, wake-word requirements, UI technology and numerical acceptance thresholds remain explicitly open pending evidence.

Do not publish this as an actual approval without an operator message explicitly accepting the proposed terms.

## 9. Outcome and next action

**Completed:** formal review packet, recommended decisions, candidate E0/E1 release contracts, pass/fail gates, unresolved decision ledger and a bounded path to the first engineering authorizations.

**Not completed:** formal approval, actual pilot requirements, changes to code/CI, user acceptance or A4.

**Next operator step:** accept/modify the decision wording above. Then stamp the official decision record, update the Blueprint status and authorize WP-01/WP-02 separately.