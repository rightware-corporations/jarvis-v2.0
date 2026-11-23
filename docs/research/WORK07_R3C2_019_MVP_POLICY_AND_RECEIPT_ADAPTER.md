# WORK-07 R3-C2-019 — MVP objective policy and observed receipt adapter

**Data:** 2026-11-13 (Africa/Maputo).  
**Author/provenance:** ChatGPT, user-authorized continuation of the JARVIS objective/evidence study.  
**Category:** LABORATORY FINDING + RECOMMENDED PRODUCT ARCHITECTURE. **NOT a production patch or authorization to deploy.**  
**Baseline:** JARVIS `develop` `47db3c86a68a0ee272d9e08515f766e5a0eec8fa`; all 3 CI checks of this baseline success.

## 1. First-MVP objective source: selected recommended approach

**Recommendation:** The first production candidate should use **trusted explicit task contracts** (operator-confirmed checklist or approved task preset) as the mandatory source of objectives; model-suggested extra steps may only be optional suggestions, never remove, downgrade, reorder or mark mandatory objectives complete. **Do not** claim universal reliable free-form Portuguese requirement extraction.

An assistant without a trusted task contract must state that task completion is not verifiable: `UNKNOWN/NEEDS_CLARIFICATION` or a truthful informative answer rather than `COMPLETE_VERIFIED`. If using optional deterministic partial extraction (literals/numbered items), mark coverage incomplete unless validated by a user or a trusted preset. Unresolved prohibitions, ordering and conditions also block operational completion until enforcement exists.

A task is eligible for operational COMPLETE only if:
1. Trusted contract exists, with at least one mandatory objective and clear acceptance criteria.
2. Every mandatory objective is satisfied by a permitted, actually executed, objective-specific tool outcome; forbidden actions did not occur and dependencies/order/conditions are honored.
3. Evidence is bound to the same task and run using a verifiable receipt chain, not model narration, memory or untrusted page text.
4. Any failure/ambiguity produces `INCOMPLETE/UNKNOWN/NEEDS_CLARIFICATION`, never an automatic PASS.
5. Factual correctness is separately asserted (usually NOT VERIFIED by mere retrieval).

**Status of the above:** chosen **research/architecture recommendation**, pending explicit approval of a production increment and end-to-end enforcement testing.

## 2. Existing runtime evidence — gap audit

`ToolOutcome(tool,status,content,evidence)` exists in `rightware/agent/session.py`; `TaskTrace` contains optional in-memory proposals, call IDs, decisions, outcomes and truncated result/view hashes. `PublicBrowser.events` contains navigation events with URL, status and page digest. Neither the ToolOutcome nor the browser event supplies a durable universal task/run/call/outcome receipt identifier, and nothing currently binds a trusted objective contract to `AgentSession.run()`.

**Important:** `G2_OBSERVATIONAL` in the laboratory is not a cryptographic/durable attestation. A unique match using a short digest, tool name and status is an observational correlation inside one memory-held run, **not** a universal guarantee of integrity, uniqueness, authority or identity of a referenced document. An unchanged URL/title and HTTP 200 are not sufficient to prove the original. The current `ANSWERED_WITH_SOURCES` product completion status remains unsound for tasks requiring multiple mandatory originals.

## 3. Test-only implementation

- Commit `d19553586714d0314ddcb268163304f73d0619cf`: `labs/work07_r3c2/live_receipt_adapter.py`. Receives the REAL `AgentSession`, `AgentReply`, trace and browser events. Classifies each ToolOutcome:
  - `UNKNOWN` when refused, failed or not executed;
  - `G1` when tool results exist but unique trace/browser correlation is absent or ambiguous;
  - `G2_OBSERVATIONAL` on a unique match of approved trace call with outcome tool+status+hash and, for loads, a unique matching browser event.
- Commit `084e6d85b72b4a2966e80653eba508070ca8e440`: `tests/test_work07_r3c2_live_adapter.py`, 9 deterministic tests. Uses a **real pinned OrchestratorAgent + RIGHTWARE AgentSession + AgentPolicy + PublicBrowser**, with scripted FAKE model and a local synthetic archive. No external navigation or Qwen.
- This adapter only reconstructs observations after the run; does not change authorization, retry, final answer, or product state. No `rightware/`, `vendor/`, workflows or production files changed.

## 4. Executed tests and observed CI

**WORK-05 product suite** [run 43467723493](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43467723493) at commit `084e6d8`: **success**.

The job log explicitly recorded 9/9 `test_work07_r3c2_live_adapter` methods `... ok` under the pinned OpenJarvis virtual environment. Full suite: **Ran 320 tests ... OK**, with no skipped tests in that virtual environment. Plain Python: **Ran 320 ... OK (skipped=146)**: the 9 new OpenJarvis-dependent tests were skipped there as designed, while dependencies are missing.

| Scenario | Result | Evidence boundary |
|---|---|---|
| Incomplete task opens only info pages | PASS | Original URLs remain INCOMPLETE even if product currently says ANSWERED_WITH_SOURCES |
| Complete synthetic browse opens both originals | PASS | G1 or observational G2; never G3 |
| One uniquely correlated live trace/outcome | PASS | Observed call_id preserved, not fabricated |
| Trace disabled | PASS | No G2 promotion |
| Trace result hash tampered | PASS | No G2 promotion |
| Duplicate identical outcome | PASS | No ambiguous G2 |
| Unsupported model claim appended | PASS | No new receipt fabricated |
| NOT_EXECUTED outcome added | PASS | UNKNOWN, not G2 |
| Duplicate browser event | PASS | No ambiguous G2 |

**Scope:** Integration of post-run observations with existing in-memory runtime evidence is demonstrated for these fixture scenarios. **Not** a production-ready objective completion controller or durable execution ledger.

## 5. Remaining unresolved correctness and safety gates

- No auth/identity of the trusted checklist/pre-set has been implemented; no objective schema is passed to the production AgentSession.
- No automatic trusted extraction from unconstrained natural language; no measured E3 recall on unseen Portuguese requests.
- Forbidden actions, ordering and conditions are merely represented in the synthetic Contract, not enforced over actual history.
- Correlation uses 16-character truncated SHA-256 of result text plus unique matches; absence of collisions in tested fixtures does not imply tamper-resistance or strong identity proof.
- Cannot prove real document identity/source authenticity or factual correctness (G3).
- No atomic transaction id linking proposal, approval, execution and outcome; no crash-safe continuity/idempotency (L5–L12).
- `_compose()` still classifies any successful source as ANSWERED_WITH_SOURCES; last-turn wasted continuation and quota/loop constraints remain open from E1/E4.
- No real Qwen test after these changes; historic FAIL/BLOCKED must be preserved.

## 6. Next recommended decision

**Product milestone A (requires new explicit approval):** implement an opt-in, minimal task-contract entrypoint and completion gate for a narrow category of read-only browser objectives, after designing an authenticated/stable runtime receipt correlation. Reject any missing objective or ambiguous evidence. Check fallback UNKNOWN, budget, refusal, cancel, deadline, source identity and flags. Keep all historical trace/quotas/policy invariants.

Do not import Shared Intelligence as a service; reuse proven contracts/invariants only. Local durable continuity and the Shared-integration decision belong to a separate milestone. No Qwen until deterministic product tests pass.
