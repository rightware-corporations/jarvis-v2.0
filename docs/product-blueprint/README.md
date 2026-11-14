# RIGHTWARE JARVIS — Product & Systems Blueprint

**Version:** 1.0 (incremental)  
**Created:** 2026-11-14  
**Status:** APPROVED ARCHITECTURAL REFERENCE (operator 2026-11-14), with conditional/open technical decisions; reports JRV-008/WP-01/WP-02 preserve separate states  
**Repository:** rightware-corporations/jarvis-v2.0  
**Branch:** develop

## Purpose

Make RIGHTWARE's intended JARVIS product, behaviours, architecture and engineering evidence the source of truth for planning. The upstream OpenJarvis framework is an implementation dependency, **not** the product specification. Qwen and Ollama are replaceable model/runtime choices. Do not assume that a proposed capability exists in production.

## Publication rules

1. Publish **one complete, reviewable matrix per engineering increment**, never defer all matrices until the end.
2. Each document must state: ID, version, date, owner/approval, status, scope, evidence source, decisions, open questions and next matrix.
3. Distinguish: **OFFICIAL DECISION**, **VERIFIED IMPLEMENTATION**, **ACTIVE WORK**, **PROPOSED ARCHITECTURE**, **HYPOTHESIS**, **RECOMMENDATION**.
4. A proposal does not authorize implementation. No roadmap, technology, feature or release is approved merely by being documented.
5. Append engineering checkpoints to \`docs/HANDOFF.md\`, and preserve historical test results and failures.
6. When a matrix changes, update its version and cross-references. Do not silently rewrite a previously approved decision.
7. Do not introduce a dependency on RIGHTWARE Shared Intelligence Core without separate feasibility, licensing and interface review.
8. Use independent tests, runtime observations and GitHub CI for implementation claims; a diagram or unit test alone does not prove end-to-end readiness.

## Matrix register

| ID | Matrix | Status | Repository file |
|---|---|---|---|
| JRV-001 | Product definition & capability taxonomy | PROPOSED — authored, pending approval | [JRV-001_CAPABILITY_TAXONOMY.md](JRV-001_CAPABILITY_TAXONOMY.md) |
| JRV-002 | Use cases & actor journeys | PROPOSED — authored, pending approval | [JRV-002_USE_CASES.md](JRV-002_USE_CASES.md) |
| JRV-003 | Behaviour contracts & acceptance criteria | PROPOSED — authored, pending approval | [JRV-003_BEHAVIOUR_CONTRACTS.md](JRV-003_BEHAVIOUR_CONTRACTS.md) |
| JRV-004 | System architecture & technical interfaces | PROPOSED — authored, pending approval | [JRV-004_SYSTEM_ARCHITECTURE.md](JRV-004_SYSTEM_ARCHITECTURE.md) |
| JRV-005 | Verified current implementation audit | AUTHORED — read-only evidence audit, review pending | [JRV-005_IMPLEMENTATION_AUDIT.md](JRV-005_IMPLEMENTATION_AUDIT.md) |
| JRV-006 | Gap analysis & dependency graph | PROPOSED — authored, review pending | [JRV-006_GAP_ANALYSIS.md](JRV-006_GAP_ANALYSIS.md) |
| JRV-007 | Engineering roadmap & release gates | PROPOSED — authored, awaiting approval | [JRV-007_ENGINEERING_ROADMAP.md](JRV-007_ENGINEERING_ROADMAP.md) |
| JRV-008 | Formal review & decision register | REVIEWED — recommendations pending operator decision | [JRV-008_BLUEPRINT_REVIEW_AND_DECISION_REGISTER.md](JRV-008_BLUEPRINT_REVIEW_AND_DECISION_REGISTER.md) |

The sequence can be revised with a documented decision; JRV-005 must inspect the **actual repository** at a recorded SHA before claiming implementation.

## Known engineering context at authoring time

- \`develop\` HEAD observed before blueprint publication: \`65dad56f73b872017ef5c2d1c8717909d7c0106e\`.
- A1 trusted task contracts — implemented, opt-in; tested.
- A2 execution receipts — implemented, opt-in; tested.
- Issue #9 stale denial reason — closed and corrected.
- A3 completion gate — implemented, opt-in; 408 pinned-env tests recorded in its CI checkpoint and all three workflows passed at the above HEAD.
- A4 acceptance — not authorized / not implemented as of this register.
- A3 has no trusted original-document identity rule (\`identity_rule=NONE\`): it cannot truthfully report \`COMPLETE_VERIFIED\` for original documents.
- In-person user acceptance, persistent memory, complete Windows/voice product integration and real-Qwen recovery behaviour are **not demonstrated** by A3's FAKE-model tests.

Read [HANDOFF](../HANDOFF.md), [ARCHITECTURE](../ARCHITECTURE.md) and the WORK-07 Milestone A engineering documents for evidence. This register is not a substitute for those sources.

## Working principle

**Product intent → capabilities → use cases → behaviour contracts → architecture → current-code audit → gaps/dependencies → implementation → integrated verification → release acceptance.**

Each capability should be traceable through \`JRV-SYSTEM.CAPABILITY\` identifiers to use cases, tests, code and release gates.

## Blueprint v1.0 formal review

Seven initial matrices (JRV-001–007) are authored. A separate [JRV-008 formal review and decision register](JRV-008_BLUEPRINT_REVIEW_AND_DECISION_REGISTER.md) supplies proposed approval language, narrower E0/E1 scope and open decisions. **No official architecture approval, implementation authority, A4 or release follows automatically from JRV-008.**


## Official operator decision and authorized investigations

- **APPROVED architectural reference:** [Decision JRV-DEC-2026-11-14-001](DECISION_2026-11-14_BLUEPRINT_V1_APPROVAL.md). The operator explicitly approved JRV-001–007 as the RIGHTWARE JARVIS Blueprint v1.0 reference, adopting E0/E1 planning envelopes and separately authorizing only WP-01/WP-02 read-only specification/investigation. The original matrices remain preserved as authored and some of their technical choices remain OPEN.
- **APPROVED read-only work — report delivered:** [WP-01 Release Scope & Device Specification](WP-01_RELEASE_SCOPE_AND_DEVICE_SPECIFICATION.md). Exact UC shortlist remains a proposal; Issa's target device and consent policy are unknown.
- **APPROVED read-only work — report delivered:** [WP-02 Pinned OpenJarvis Reuse & Integration Investigation](WP-02_VENDOR_AND_INTEGRATION_INVESTIGATION.md). Important qualification: upstream has existing persistent memory, GUI, scheduler and file tools; these are not integrated or security-accepted RIGHTWARE product features. **Reuse must be evaluated before building duplicate components.**
- **Historical review:** [JRV-008 — Formal review](JRV-008_BLUEPRINT_REVIEW_AND_DECISION_REGISTER.md) predates the official approval; its "NOT APPROVED" wording remains valid **at its authored time**, not at present.
- **Still not authorized:** any product code, A4, live-Qwen/Windows tests, vendor updates, dependency changes, memory retention rollout or commercial release.

### Status interpretation

The **Blueprint as an architectural reference** is approved, but its contents are not blanket implementation permission; each release scope, integration architecture, technology choice and measurable gate must still be decided within the approved process. When a future report contradicts an earlier proposed assumption (e.g. upstream module availability), attach the explicit follow-up instead of hiding/replacing earlier evidence.


## Subsequent approved specification work (2026-11-14)

Following the operator's instruction to continue WP-03 and **WP-04 interface design only**, the following documents were authored as proposed specifications:

- [WP-03 — Portuguese Intent/Context Evaluation Contract](WP-03_PORTUGUESE_CONTEXT_EVALUATION_CONTRACT.md): 36 manually labeled [synthetic Portuguese test cases](fixtures/WP03_PT_CONTEXT_CORPUS_v1.csv); **not executed against any model**, numerical thresholds pending.
- [WP-04/D01 — Unified Control Plane Interface Design](WP-04_UNIFIED_CONTROL_PLANE_INTERFACE_DESIGN.md): six conceptual contracts, request/route/authorization/result/context/adapters, 14 proposed integration tests and a safe staged migration proposal.

These docs are NOT authorization for source-code changes, an A4 milestone, real-Qwen/Windows tests, vendor upgrades, installing dependencies or enabling persistent memory. The operator's earlier official approval of the JRV architectural reference remains intact.
