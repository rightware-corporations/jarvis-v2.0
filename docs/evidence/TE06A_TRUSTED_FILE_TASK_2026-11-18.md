# TE-06A — Trusted file task execution, first practical agentic MVP (18/11/2026)

**Nature:** deterministic tests and a demo with a FAKE model and synthetic fixtures created in temporary
directories. No Ollama, no real Qwen, no personal files, no network. Linux secure-open semantics only;
**no Windows support is claimed**. This is not product or model acceptance.

Branch `feat/te06a-trusted-file-task-execution`, from TE-05E head `322b4d8` (PR #18 unchanged).
OpenJarvis pin `f21d902` unchanged; `develop` / `main` untouched.

## 1. Cycle demonstrated (through the real executor)

TASK → PLAN → TOOLS → RESULTS → VERIFICATION → REPORT:

* `TaskEntry.run_trusted_file_compare` (host) → `AgentSession` (pinned `OrchestratorAgent`, function calling).
* The FAKE model chooses the tools: `fixture_read(A)`, `fixture_read(B)`, `fixture_compare()`, then its answer.
* Each call goes through `AgentPolicy`: schema/enum, capability, quotas, loop guard, mandatory audit.
* The `ReceiptLedger` binds decide → dispatch → claim → finish.
* `evaluate_file_task` re-reads the files and recomputes the diff, independently of the model.
* `FileTaskEntryResult`, the JSON record and the text report carry the outcome.

The model is not required to follow that order; the contract and the verifier decide.
`python -m labs.te06a_files.demo` prints the JSON and text report: COMPARISON_VERIFIED, 1 added, 1 removed, 1 modified.

## 2. Design

| Element | Decision |
|---|---|
| Contract | `FileTaskContract` in the code-owned catalog `TRUSTED_FILE_PRESETS`: `fixture-two-versions-compare`, ids exactly A/B, operations `fixture_read`/`fixture_compare`, 16 KiB per file, objectives READ_A/READ_B/COMPARE, ≤1 continuation. Separate from `BrowserObjective` / `TaskContract`. |
| Authority | The host chooses the `files` capability, the contract id and the `FixtureWorkspace`. The model only names `A` or `B` (JSON-schema enum, `maxLength` 1). No path ever reaches the model. |
| Secure reads | Directory opened once with `O_DIRECTORY|O_NOFOLLOW`; files opened with `dir_fd` + `O_NOFOLLOW`; regular files only, `st_nlink == 1`, size limit enforced on `fstat` and while reading, NUL bytes rejected, strict UTF-8. Bindings are plain names (no `/`, no `..`). Read-only; never writes. Without `O_NOFOLLOW`/`dir_fd` (e.g. Windows) it raises `FileTaskError` (fail closed). |
| Tools | Two `ToolDef`s in a separate `FILE_TOOLS` registry, merged into the policy registry only when the session has a host file contract. Default sessions keep the identical registry and prompt (A/B verified). The model sees file text inside an untrusted-data frame. |
| Compare | Refused (`READS_REQUIRED`) until A and B were read in this run. Re-reads both and refuses `FILE_CHANGED` if a hash differs from the one read. Diff by `difflib` (no autojunk); `replace` blocks pair as modified, the surplus counts as added/removed. |
| Verifier | Re-reads the files (current hashes) and recomputes the diff. READ_x is VERIFIED only from a receipt that is bound, `SUPPLIED`, authorised, executed, OK, audited, not late, with a hash equal to the current file. COMPARE is VERIFIED only after both verified reads, with input hashes and diff digest equal to the recomputation. Priority of states: ERROR > HALTED > INCOMPLETE > UNKNOWN (ambiguous or integrity failure) > COMPARISON_VERIFIED. `COMPLETE_VERIFIED` is not reused. |
| Narrative | Never evidence. The change counts it states are compared with the code result: `COUNTS_CONSISTENT` / `COUNTS_DISCREPANCY` / `NO_COUNTS_STATED` / `NOT_CHECKABLE`. `narrative_verified` is always false. The report's `changes` come only from code, and only when the comparison was verified. |
| Continuation | The existing `_CompletionEngine`, with an injectable assessment (missing ids + code-generated feedback). Quotas and permissions are never reset. |
| Diagnostics | Finite file refusal codes added to the TE-05 vocabulary. TE-05E error preservation applies (an error after a valid read keeps READ_A VERIFIED, receipts and metrics, with `error_code`). |

## 3. Tests actually run (this environment, pinned venv)

* New `tests/test_te06a_file_task.py`: **35 OK**. It covers all 20 required cases plus:
  * capability isolation (text path, default sessions, envelope);
  * result invariants;
  * vocabulary alignment;
  * the fail-closed platform check.
* Relevant modules OK:
  * TE-05E 16, TE-05 18, TE-04 3, TE-03 9, TE-02 10;
  * A1 15+16, A2 21, A3 29, issue #9 7;
  * AgentPolicy 12+21, text facade WP-04 23;
  * browser 23 (inside the full suite).
* Full suite, pinned venv: **522 OK, 0 skipped** (baseline 487 + 35). Plain Python: 522 OK (252 vendor-dependent tests not run there).
* A/B against TE-05E `322b4d8` on the R3-C1 browser scenarios: identical.
* Mutation check: 10 deliberate regressions are all detected: digest unchecked, symlinks followed, hard links allowed, compare without reads, swap undetected, file tools in every session, narrative never flagged, order ignored, binary accepted, changes on unverified.

## 4. Defects found and fixed during implementation

* The verifier initially accepted a comparison issued before the reads. Fixed; tested.
* One unreadable file made the other read unverifiable. Each file is now re-read independently, and missing objectives take priority over integrity.

## 5. Limitations / risks

* Linux secure-open only (`O_NOFOLLOW`, `dir_fd`); Windows is untested and fails closed.
* Between the compare and the verifier's re-read, a file can change. The verifier then reports UNKNOWN (safe), but cannot say which version the model reasoned over beyond the receipt hashes.
* Narrative checking covers stated counts in Portuguese only; quoted line contents are not checked. Such quotes cannot enter the report, which uses code results.
* The file text reaches the model inside an untrusted frame. A real model may still be influenced in its narrative (prompt injection), but it cannot gain tools or change the verdict.
* Denials consume the shared proposal budget (unchanged policy semantics).
* `max_bytes` is 16 KiB; larger documents need a separate decision.

## 6. Next (requires separate authorisation)

TE-06B: one real Qwen 2B run of this file task, with the same contract and limits, measured with the TE-05E diagnostics and a truthful-verdict workflow.
