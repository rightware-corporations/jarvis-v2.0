# RIGHTWARE JARVIS — Official Decision Record: Blueprint v1.0

**Decision ID:** JRV-DEC-2026-11-14-001  
**Date:** 2026-11-14 (Africa/Maputo)  
**Authority:** Explicit operator approval in the ongoing conversation, in response to the proposed JRV-008 approval wording.  
**State:** **OFFICIAL DECISION — APPROVED WITH RECORDED CONDITIONS**  
**Reference:** JRV-001–JRV-007, JRV-008 formal review, `docs/HANDOFF.md`.  
**Reference develop HEAD before decision:** `791f409a2de5268ab074044dc42b2b438c99e6a8`.

## Exact scope authorized

1. **Approve** JRV-001–JRV-007 as the RIGHTWARE JARVIS Blueprint v1.0 **architectural reference**, subject to the qualifications and open choices in JRV-008.
2. **Adopt E0 and E1 as the first two planning release envelopes**: E0 internal text alpha followed by E1 Issa-oriented Windows pilot. This **does not** claim the software, features or release gates are already completed.
3. **Authorize WP-01** — read-only product scope and target-device **specification/investigation**: define E0/E1 use-case candidates, exclusions, compatibility and acceptance requirements; unknown device data remains open.
4. **Authorize WP-02** — read-only pinned OpenJarvis/vendor/API/licence boundary and RIGHTWARE A1–A3 integration **investigation/specification**: inspect source, classify reuse/risks and produce a non-destructive integration proposal.
5. Require staged checkpoints, updated Blueprint/HANDOFF, and new operator authorization before converting proposals into product-code changes.

## Still OPEN — no silent approval

- Exact Windows device specifications; OS, CPU/GPU/RAM, microphone hardware and offline/latency constraints.
- Memory storage classes, consent, retention period, encryption, deletion semantics, backups.
- Whether always-on wake word is mandatory for E1.
- GUI framework, packaging/distribution, exact first useful Windows actions and any external connectors.
- Quantitative model quality/performance thresholds and actual pilot acceptance.
- Trusted identity provenance for original documents; Shared Intelligence Core adoption.
- Full experimental scope for live Qwen runs and real Windows hardware tests.
- Whether to authorize WORK-07 A4 separately.

## Explicit exclusions

**No authorization** for modifications to product code or tests; no vendor update, dependency installation or platform migration; no live Qwen inference/Windows actions, A4, main-branch merge, deployment, user-data upload, paid API, recurring automation, commercial release, memory retention rollout, or any destructive Git operation.

## Governance / traceability

The original JRV-001–JRV-008 documents remain historically intact. This decision record is the **authoritative change of status**, not a retroactive rewrite that would make earlier proposed content appear approved at its original creation date. The Blueprint scope is approved as a reference, but individual technical options and pending product choices remain explicitly conditional.

**Authorized work products now:** WP-01 scope/acceptance investigation and WP-02 architecture/API reuse investigation as separate Markdown artefacts, with source references, verified vs inferred statements, blockers and next bounded actions.

**Evidence status:** existing A1/A2/A3 test success and green CI are not proof of E0/E1 product completion.

**Next:** conduct WP-01 and WP-02 read-only investigations, publish reports and update HANDOFF. Request a separate future operator decision for WP-03 and/or implementation WP-04 after review.
