# RIGHTWARE JARVIS v2.0 — BRANCH GOVERNANCE AND CONSOLIDATION
**Decision:** operator direction, 2026-11-11. **Scope:** version-control organization, not a declaration of product acceptance.

## Permanent branch topology (target: three)
1. `main` — reviewed and approved version/release baseline. **Do not automatically merge all of `develop` into `main`.** Release promotion requires explicit approval, CI and a reviewed PR.
2. `develop` — **single active engineering integration line**, the authoritative working HEAD for JARVIS product development. For routine approved tasks, commit coherent checkpoints directly here with tests and HANDOFF. A short-lived feature branch is justified only by active high-risk experiments or parallel development and must have an owner, base, merge/cleanup plan.
3. `demo/issa-20261111` — temporary demonstration snapshot. No new features are implemented here by default. Its code can be synchronized from a validated `develop` when explicitly approved.

## Verified consolidation operations (2026-11-11)
- WORK-05 R1 product agent and security hardening: PR #4 **merged** into `develop`, merge commit `929fa945166ad4515498aba35a41a6eff3d2b4c9`; last feature-head CI `43105709812` SUCCESS, deterministic suite, no Qwen inference.
- `main` had two unique manual-only workflows (WORK-03/04). PR #5 **merged main → develop**, commit `63986b9a563fa11ca7430e466bdfaceaeecb4645`; **main did not change**. No real-model workflow was dispatched.
- Research-only document `docs/research/RIGHTWARE_AGENT_REUSE_RADAR_20261111.md` copied to `develop` from `research/jarvis-agent-survey-20261111`, commit `671bdb2e733fe47009a28792047e4404afd68065`.
- PR #3 (the parallel WORK-05-A prototype) **closed WITHOUT MERGE**, because its integration would duplicate the selected product agent. The original branch and commits remain available for selective review.

## Temporary branches still physically present; DO NOT DELETE without gates
| Branch | Status | Preservation/closure gate |
|---|---|---|
| `feat/work05-product-agent` | Integrated by PR #4 | Safe to delete after verifying merge ancestry and preserving relevant refs; its code is in `develop`. |
| `research/jarvis-agent-survey-20261111` | Research document copied | Verify no unique needed work remains; then safe to delete. |
| `feat/work05-product-agent-foundation` | Parallel unmerged code, PR #3 closed | Keep until selectively comparing `rightware/agent_tools.py`, `tests/test_agent_tools.py`, and continuity documentation; do not wholesale merge or delete now. |
| `feat/work04-r2-semantic-safety` | Research/lab R2 unmerged, PR #2 draft/conflicted | Preserve full lab evidence and history, repair actual merge conflicts in a reviewable PR before deciding integration. Qwen historical benchmark remains 0/35, NOT ACCEPTED. |

**Important:** The three-branch topology is the **target**, not an already achieved physical count. Do not claim the extra branches were deleted until GitHub confirms. Do not use forced ref updates to conceal history.

## Enforcement
- GitHub branch protection/rulesets for `main` and `develop`: block force pushes/deletion; require appropriate test checks, controlled PR/approval process for releases, and review of changes. Connector access may not support protection-rule mutations; record this as an outstanding manual GitHub administrative action.
- Preserve `docs/HANDOFF.md` append-only. A substantial engineering progress output must follow a pushed, confirmed checkpoint recording phase, branch, commit, tests/CI, limitations and next step. Never persist private messages, secrets, tokens or personal data.
- Do not equate deterministic test success with a real Qwen/voice/Windows acceptance. Running a real-model smoke is an independent explicitly authorized gate.
- Existing OpenJarvis pin stays fixed unless separately authorized.
