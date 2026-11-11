# RIGHTWARE JARVIS v2.0 — WORK-05 continuity checkpoint

Date: 2026-11-11. Status: **ACTIVE PROJECT — WORK-05 INITIALIZATION**, not a release decision.
Source of truth: repository history, `docs/HANDOFF.md`, tests and GitHub CI. This is a condensed technical reconstruction, **not a complete chat transcript**.

## Recovery: where the interrupted work stopped

- Original WORK-04 benchmark: **NOT ACCEPTED, 0/35**, immutable.
- Kaggle R2 smoke: **0/3**; subsequent CPU EVOL-4001 runs also **FAIL**.
- Latest real CPU EVOL-4001: run [43066548100](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43066548100). Seven facts correct, ORACLE PASS, V2 FAIL because of format; 0 sandbox violations. This is **not a task PASS**.
- R2-A lint, R2-B stop when completion is impossible, and R2-C verifier-feedback evidence: implemented and tested. R2-D product structured-output contract: specified only.
- Latest deterministic CI [43070956530](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43070956530): **178 WORK-04/R2 + 61 WORK-02 + 56 RIGHTWARE = 295 PASS**; not a Qwen acceptance run.
- WORK-04 R2 source branch `feat/work04-r2-semantic-safety`, code SHA `b8e4bc0c6aabfdf70781d4ea9c64e39dfb7bb03e`, HANDOFF tip `dd5dbd6be9e839cd50a2f2dbc3468ec7c6cd673f`; Draft PR [#2](https://github.com/rightware-corporations/jarvis-v2.0/pull/2), base `develop`.
- WORK-05 is isolated in `feat/work05-product-agent-foundation` **from `dd5dbd6`** so another agent resuming R2 cannot inadvertently overwrite this work. No merge or modification of `main`/`develop`.

## Product scope (do not reduce to document reports)

JARVIS is a local-first Portuguese personal AI assistant, built with pinned OpenJarvis + local Ollama + Qwen. The desired product supports text, voice, dictation, Windows application control, navigation and later controlled web interaction, work with files, task execution with independent verification, and bounded continuity/recovery. Future shared context comes from an independent RIGHTWARE Shared Intelligence service (Mem0 + local embeddings + PostgreSQL/pgvector), with explicit scoping and authorization. This repository **does not yet have a connected shared-memory integration**.

The real product currently has simple local chat/voice and two allowlisted Windows actions (Notepad/Calculator, session authorization plus per-action confirmation). The WORK-04 advanced agent is mainly in the lab; benchmark components, synthetic ground truth and ORACLE must never be shipped into the runtime.

## Decision versus recommendation

**Already accepted technical constraints:** preserve local/no-paid-API stack, pinned upstream, existing historical test outcomes, controls and boundaries; Qwen real inference only after explicit fresh authorization. No merge into `main`/`develop` as part of this work.

**WORK-05 engineering recommendation, not general product release approval:** implement a small, isolated typed tool-execution boundary and a read-only document capability for deterministic validation; subsequently connect a constrained OpenJarvis agent and safe browser capability. Voice and text should converge on one execution path rather than separate control systems. The memory service remains separate and unconnected until scoped permission tests exist.

## Mandatory continuity protocol

1. Before each work session: inspect `docs/HANDOFF.md`, this checkpoint, the active branch/HEAD, Draft PR, and recent CI.
2. Each **completed engineering checkpoint** must append a dated HANDOFF entry (what changed, branch, commit, tests, blocked gates and next action) before moving to the next work item. Do not overwrite or compress historical evidence.
3. In any interruption, the *last committed HANDOFF* and immutable test evidence outweigh chat summaries or assumptions. Claims of PASS require actual observed results and exact run IDs.
4. No secrets, private conversations, personal data, full chat transcripts or unredacted tool output in this **public** GitHub repository. Save only sanitized project decisions and test evidence.
5. Avoid writing concurrently to R2 while a paused Claude session may auto-resume. WORK-05 is independent; compare branch heads before any update.
6. Do not trigger Qwen, merge, modify main/develop, relax V2/ORACLE, alter historical verdicts, or silently change the upstream pin. Any CI claiming Qwen must actually execute it.
7. Every new tool requires a closed schema, double authorization checks, budgets, fail-closed result handling, untrusted-result framing, audit without conversation, and tests.
8. At each answer, distinguish **CONFIRMED / IMPLEMENTED / TESTED / NOT VERIFIED / RECOMMENDED / NEXT GATE**.

## Next engineering gate

WORK-05-A: build and test product-side C1–C6/C10 skeleton with a read-only, explicit-scope document tool and the existing `WindowsActions` path. No Qwen. Then audit and plan the OpenJarvis integration and browser controls. A deterministic test suite proves boundaries, **not** real-agent generalization.
