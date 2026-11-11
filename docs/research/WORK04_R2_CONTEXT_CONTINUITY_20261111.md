# RIGHTWARE JARVIS v2.0 — WORK-04 R2
## Context continuity and generic report-reasoning guardrails

**Date:** 2026-11-11  
**Status:** ENGINEERING IMPLEMENTED / DETERMINISTIC VALIDATION PASS / **QWEN REAL NOT RETESTED**  
**Branch:** `feat/work04-r2-semantic-safety`, Draft PR #2, targeting `develop`.  
**Pre-change benchmark evidence:** EVOL-4001 real Qwen on GitHub Actions CPU, run `42829191737`, **FAIL**, V2 FAIL, ORACLE FAIL, `false_success=true`. See `WORK04_R2_CPU_EVOL4001_RUN42829191737.md`.

### 1. Evidence-led diagnosis

The independently verified `runs.jsonl` (GitHub artifact 13770527129) contains an initial **unpersisted** model answer that already named both the estimated and approved budget, described their EVOLUÇÃO, and included the two relevant source filenames. The bounded recovery started a **new** `OrchestratorAgent.run()` context rather than retaining previous tool content. The model re-read documents and produced two persistent versions. The final `_v2` correctly included both budget states, but declared a non-existent temporal inconsistency and omitted required `[TIPO]` brackets. The model asserted that the June start preceded the May approval, which is false.

**Interpretation:** initial comprehension is not the same as task completion. Source context was discarded across recovery; the report contract also allowed one-row-per-field ambiguity. A model failure remains possible even when context is preserved.

### 2. Changes — R2 only

**Bounded source replay (`w04lab/recovery_r2.py`, `w04lab/harness_r2.py`)**
- Uses the data **already delivered** by `FaultyReadDocument` after `source_guard.isolate_instructions()`, solely for names recorded as successful `read_document` calls in the same task. No new filesystem access, privileged tools, inferred sources or ground-truth values.
- Explicitly marks every replayed excerpt as **untrusted data**, not instructions; includes immutable filename, content SHA-256 and char count in `continuation_context.replayed_sources` evidence.
- Caps replay at **4,000 characters per document**, **8,000 total** including wrappers; entirely skips overlong documents rather than truncating facts. Documents that exceed the cap remain accessible exclusively via an already-authorized `read_document` tool call, subject to the unchanged 12-call policy.
- Keeps the same **single** bounded continuation, same policy object and sandbox, no extended write/read/verify quotas. Does not reuse the model's self-generated first answer as authoritative source.

**R2-specific report contract and feedback (`w04lab/harness_r2.py`, `w04lab/feedback_r2.py`)**
- Makes clear there is **one row per documented value/state**, not one row per field; a field can appear multiple times.
- Instructs chronological comparisons by year → month → day, and forbids treating a merely later date as earlier.
- Enforces syntax `- [TIPO] campo: descrição`, including square brackets; strengthens the existing generic distinction between EVOLUÇÃO, CONTRADIÇÃO and genuine INCONSISTÊNCIA TEMPORAL.
- Contains **no EVOL-4001 project names, people, dates, budget amounts or ground-truth values** in trusted instructions. Feedback still only names failed rule categories; V2 and independent ORACLE code **unchanged**.

### 3. Deterministic validation

New `labs/work04_cognitive/tests/test_w04_r2_continuity.py` contains **7 tests** covering:
- Replaying only names with prior successful reads; deduplication, no unauthorized names;
- Unsafe name rejection and no replay of unrelated values;
- Per-document and overall length caps; no truncation mid-fact;
- Retaining source_guard quarantine of injected directives;
- Untrusted framing, original authorization and budgets;
- First-shot contract generality (no EVOL-4001 answer contamination);
- Real OrchestratorAgent with FAKE scripted engine creates/verifies a report using replayed context, without new read calls.

New tests are included in the static R2 CI and in the CPU workflow's preflight unit-test gate. The versioned CPU Qwen request file **was not changed**, so no GPU/CPU inference was triggered.

**CI run:** https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43053462119  
**Actual CI result:** **150 WORK-04/R2 + 61 WORK-02 + 56 RIGHTWARE = 267 PASS**.

### 4. Boundaries and remaining risks

1. The new model prompt and replay are a materially different R2 condition. Any future real Qwen result must be labelled as such and **must not be pooled** with historical rev.1 **0/35**, Kaggle R2 **0/3**, or previous CPU EVOL-4001 **0/1** trials.
2. Replay of sanitized source data **is not a proof of resistance to prompt injection**. The same untrusted facts are shown again with data-only framing. Evaluate exposure and contamination on new, pre-registered HOSTILE holdouts before security acceptance.
3. The replay length cap limits prompt budget use but may omit long documents. Model may still call tools repeatedly; the remaining budget is unchanged and the outcome is not assumed.
4. A PASS in FAKE tests only proves the integration and policy behavior, not Qwen's semantic accuracy or that first-shot claims improve.
5. **No new Qwen run is authorized in this engineering step.** The next real run, if authorized, should be **EVOL-4001 only**, with exact commit pinned and full artifact checks, to measure regression against the failed prior CPU run. Subsequently use independent preregistered holdout seeds for claims of generalization.
6. Do not modify `main`, `develop`, frozen WORK-02 policy, rev.1 harness/oracle/assess, or Draft PR status.
