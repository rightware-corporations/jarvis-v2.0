# RIGHTWARE JARVIS — WP-04/D01–D02: Claude Implementation Mission

**Date:** 2026-11-14 (Africa/Maputo)  
**Status:** BOUNDED IMPLEMENTATION MISSION — prepared for Claude; **not yet executed**  
**Operator instruction:** Continue working after WP-03 Portuguese context corpus and WP-04 interface design. In conversational context, the next proposed implementation was precisely D01–D02. This mission **only** covers those increments; no A4, wider refactor, vendor changes or high-risk tool activation.  
**Repository:** \`rightware-corporations/jarvis-v2.0\`  
**Starting reviewed HEAD:** \`fbff501644621162fa0ec56059426f8d8506d00e\` (\`develop\`), reconfirm before any changes.  
**CI at reviewed HEAD:** 3/3 SUCCESS (WORK-05 + foundation, run IDs 43607237831, 43607232190, 43607232182).  
**Active release PR:** #1 \`develop → main\` remains DRAFT / DO NOT MERGE.  
**Execution owner:** Claude for coding; ChatGPT for specification, evidence review and next acceptance.  
**Canonical references:** \`docs/HANDOFF.md\`, \`docs/product-blueprint/README.md\`, \`JRV-001–008\`, \`WP-01\`, \`WP-02\`, \`WP-03\` and \`WP-04_UNIFIED_CONTROL_PLANE_INTERFACE_DESIGN.md\`, including \`fixtures/WP03_PT_CONTEXT_CORPUS_v1.csv\`.

## Objective

Deliver a thin, tested **trusted in-process request/result facade** for the JARVIS **text-only no-tool conversation route**, without changing the existing \`AgentSession\` enforcement, A1/A2/A3 gating, Windows effects or upstream vendor.

**D01:** typed/validated request envelope, session ownership, route/result projection with no authorization minted by model or user text.  
**D02:** adapter to the already pinned local SimpleAgent/Ollama text-only path; bounded ephemeral session context, meaningful errors and status. No tools in this slice.

The implementation must help future D03 policy/agent integration without pretending that D03 has been implemented.

## Required preflight (non-destructive)

1. Reconfirm remote \`develop\` HEAD, worktree cleanliness/branches, outstanding PRs, CI, current HANDOFF tail, and pinned \`vendor/openjarvis\` gitlink + \`rightware/runtime.py:PIN\`.
2. Preserve all concurrent code and checkpoints. Do not reset/rebase/force-push or delete existing files; if newer work conflicts, stop and report before editing.
3. Read \`rightware/runtime.py\`, \`rightware/voice.py\`, \`rightware/agent/cli.py\`, \`rightware/agent/session.py\`, \`rightware/agent/policy.py\`, \`rightware/agent/receipts.py\`, \`rightware/agent/completion.py\`, \`tests/test_runtime.py\` and \`tests/test_work07_milestone_a3_completion.py\`.
4. Confirm where upstream \`SimpleAgent\` and \`AgentContext\` can be wrapped without starting an extra process or unexpectedly writing memory, and whether Ollama is required at **runtime only** rather than module import.
5. Create a small topic branch from the verified current baseline (suggested \`feat/wp04-d01d02-text-facade\`). Keep \`develop\` and draft PR #1 untouched until normal review.

## Architecture boundaries

~~~mermaid
flowchart LR
    Input["Trusted host text input"] --> Req["D01 Request envelope"]
    Req --> Router["D01 route validation"]
    Router -->|"ANSWER only"| Adapter["D02 existing SimpleAgent adapter"]
    Adapter --> Response["D01 result projection"]
    Response --> User["Text UI / caller"]
    Router -->|"TASK etc unavailable"| Limit["Explicit unavailable/plan/clarify, never a tool effect"]
    Limit --> Response
    Existing["AgentSession + A1/A2/A3"] -.->|"not modified/invoked by D01–D02"| Router
~~~

*Technical recommendation:* small Python types and adapter with narrow dependency injection for model invocations. The mission permits Claude to select file names consistent with repository style; do not add a new framework, service, database or frontend just for this.

## D01 — contract specification

**Inputs produced by trusted host code (not user/LLM):**
- generated request ID;
- session ID bound to local session (ephemeral);
- channel = \`text\` only;
- authenticated/locally trusted owner identity (a placeholder current local principal; do not claim multiuser auth);
- raw user text;
- effective capabilities = **empty**;
- deadline/context budget and model selection constrained by existing local runtime.

**Routing decision:**
- \`ANSWER\`, \`CLARIFY\`, \`PLAN\` supported in no-tool mode;
- \`TASK\`, \`CONTROL\` (beyond safe stop/status), \`MEMORY_INTENT\` can be classified/represented but **must not** execute tools or store durable user facts;
- avoid brittle keyword-only execution assumptions; lack of certainty -> focused clarification or nonexecuting assistance.

**Outputs:**
- response text;
- route used;
- status differentiating \`ANSWER_ONLY\`, \`PLAN_ONLY\`, \`WAITING_INPUT\`, \`UNAVAILABLE\`, \`ERROR\`;
- \`factual_verified=false\` unless independent fact verification actually exists (not in this scope);
- empty execution receipts/effects;
- explicit limitations for any unavailable feature;
- bounded diagnostics without transcript/secret logging.

**Forbidden in D01:**
- accepting principal/capabilities/approved tool IDs from model output or user JSON;
- dynamically generating a trusted A1 preset;
- reporting \`VERIFIED_EFFECT\`, \`COMPLETE_VERIFIED\`, \`memory_persisted\` or \`task_completed\` from mere text;
- adding tools or changing permissions.

## D02 — local text adapter specification

- Reuse the existing pinned OpenJarvis \`SimpleAgent\` / \`OllamaEngine\` **in a narrow, injectable adapter**, not another unrelated model client or remote paid API.
- Constructor/import of the new facade must be deterministic **without** Ollama server; dependency initialization should be lazy/injected for unit tests.
- Default no-tool path must never construct an \`AgentSession\` with \`allow={"actions"}\` or touch \`WindowsActions\`, public browser or filesystem.
- Ephemeral per-session context is allowed and should not leak across session IDs; respect bounded message/context length. Context corrections follow WP-03 or explicitly return clarification if uncertain.
- Handle model unavailable, timeout, malformed response and cancellation without invented execution.
- Keep old \`python jarvis.py chat\`, \`voice\` and \`agent\` behaviour intact; do not silently replace them as part of the first slice.
- A small opt-in entrypoint for unit/manual probing MAY be included only if it does not alter the existing defaults or require model download at install.
- Do NOT add automatic fact extraction or enable \`MemoryService\`.

## Must not touch without new authorization

- \`vendor/openjarvis\` gitlink/pin, lockfiles or dependency versions;
- policy, receipts, completion implementation or A1–A3 semantics;
- Windows actions and voice pipeline;
- external API providers, file write/delete/shell, mail/calendar, scheduler, persistent memory;
- commercial release flow, \`main\`, draft PR #1 or WORK-07 A4;
- integration D03–D08.

## Required test plan

| Test | Objective | Deterministic oracle |
|---|---|---|
| D01-T01 | Validation rejects empty/invalid request text/invalid channel | Fail-closed, no side effects |
| D01-T02 | User text cannot supply principal or capability grants | Trusted host fields unchanged |
| D01-T03 | No-tool result cannot claim verified execution | Empty receipts and effects |
| D01-T04 | Absent model error | \`ERROR\` with useful message, no tool activity |
| D01-T05 | Per-session context isolation | Two session IDs do not share facts |
| D02-T01 | Direct knowledge answer uses only injected fake text model | No AgentSession/WindowsAction/browse invocation |
| D02-T02 | Asked to launch calculator with capability disabled | Explicit unavailable/plan-only, zero tool effects |
| D02-T03 | Memory save request with no store | Explicit session-only limitation, no persistent claim |
| D02-T04 | Correction and anaphora from 36-case WP03 corpus | Versioned rubric and representative subset with human-review markers |
| D02-T05 | Model refuses, errors or times out | Honest status and controlled exception path |
| REG-T01 | Previously passing runtime/voice/agent tests | No regression or new skip |
| REG-T02 | A1/A2/A3 opt-in, issue #9, wrong original identity, late call | Scope-accurate negative results preserved |
| REG-T03 | Existing CLI routes unchanged | Snapshot/parity for default no-opt-in |
| SEC-T01 | Quoted malicious text attempting tool call | Data only, never execution |

All new tests must run **without Ollama** using fakes. The full pinned venv test suite and CI should run as normal, but **real Qwen benchmarking is a separately authorized mission**. Do not mark INT-001–014 as PASS merely because tests with similar names exist.

## Delivery evidence contract

Claude's response must contain:
1. Starting baseline vs final HEAD and topic branch; exact changed paths; commits.
2. Which D01 and D02 requirements are implemented and which remain excluded.
3. Exact test commands, PASS/FAIL/SKIP counts and operating system/container.
4. Pinned venv CI links and A1–A3 regression evidence; if unavailable mark BLOCKED/NOT_TESTED.
5. Confirmation of **no code changes to vendor/A1/A2/A3/Windows/voice**, or explain any unavoidable attempted deviation and stop before committing it.
6. Negative test demonstration: an instruction to send email/open calculator can only produce no-effect result.
7. Updated \`docs/HANDOFF.md\` (append-only checkpoint) with progress/risks/next mission and a Draft PR for the *topic branch only*, if repository policy supports it. Never merge or mark ready.
8. Any issue in upstream SimpleAgent API or context quality must be an explicit blocker with an investigation plan; do not expand to D03 or replace provider without approval.

## Done criterion

**Candidate \`D01–D02\` complete** only when: code follows the host-trusted request contract; no-tool model path works with injected fake, no real effect or durable memory can be claimed/executed, existing agent behaviour remains stable, all relevant tests and exact-SHA CI pass, and the result is reviewed. This is **not E0 accepted**; real Qwen and unified protected agent D03 remain separate acceptance steps.

## Next after Claude delivery

ChatGPT/RIGHTWARE reviews the PR and source/test evidence, compares output against WP03 corpus and JRV-003 CTs, then determines whether to authorize D03 (policy-protected AgentSession path) and separate live-Qwen validation. No automatic follow-up coding scope.
