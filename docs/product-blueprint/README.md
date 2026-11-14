# RIGHTWARE JARVIS — Product & Systems Blueprint

**Version:** 1.0 (incremental)  
**Created:** 2026-11-14  
**Status:** PROPOSED ARCHITECTURE — pending explicit operator approval  
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
| JRV-005 | Verified current implementation audit | PLANNED — not authored | To be created |
| JRV-006 | Gap analysis & dependency graph | PLANNED — not authored | To be created |
| JRV-007 | Engineering roadmap & release gates | PLANNED — not authored | To be created |

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