# TE-05E — Error-path evidence preservation & truthful CI (18/11/2026)

**Nature:** deterministic tests only (FAKE model, mocked HTTP, injected clocks, simulated engine
exceptions). No Ollama, no real Qwen, no real network. Not task-acceptance evidence.

Branch `feat/te05e-error-evidence-preservation`, from TE-05 head `0ae3383` (PR #16 unchanged).
OpenJarvis pin `f21d902` unchanged. `develop`/`main` untouched.

## 1. Defect confirmed in code (before changing it)

Path for the TE-05 Qwen 4B run (ERROR, 181.4 s):

1. The vendor `Agent._generate` calls `engine.generate` with no handler.
2. The pinned `OllamaEngine` maps `httpx.ConnectError` / `httpx.TimeoutException` to `EngineConnectionError`
   using `raise … from exc`, so the original exception type survives in `__cause__`.
3. `AgentSession.run` catches it and builds an ERROR reply. The exception type was used only to choose the user message text.
4. `_apply_completion_gate` replaced every ERROR by a CompletionResult with **zero objectives**.
5. `TaskEntry._run_trusted` saw 0 ≠ 2 objectives and returned `INCOMPLETE_OBJECTIVE_EVIDENCE` with **no**
   receipt events, reason codes, metrics or halt code.
6. The workflow verdict step never failed, so the job was green while the task had failed.

Result: the same diagnostics that TE-05 added were discarded exactly when they were needed.

## 2. Changes

| Area | Change | File |
|---|---|---|
| Error codes | `ERROR_CODES` = NONE, ENGINE_TIMEOUT, ENGINE_CONNECTION, ENGINE_FAILURE, AGENT_FAILURE, AUDIT_FAILURE, EVIDENCE_INCOMPLETE, OTHER. `engine_error_code(exc)` classifies by **exception type** along the cause chain; message text is never read | `rightware/agent/diagnostics.py` |
| Failed generation | Recorded with `engine_error`; token and timing fields stay `None` (unavailable, never invented) | `diagnostics.py`, `session.py` (`_GuardedEngine`) |
| Session | `AgentSession.error_code` (last run). On ERROR the completion gate evaluates the receipts as usual, keeps each objective's receipt-backed verdict, and forces the task state to ERROR | `rightware/agent/session.py` |
| TaskEntry | Receipts, reason codes, metrics and halt code are collected **before** any error branch. Untrusted or missing evidence → every objective `UNKNOWN` (never observed). An unexpected failure outside the engine still produces a safe record (`AGENT_FAILURE`, limitation `EXECUTION_FAILED`). Invariant: `operational_state == ERROR` ⇔ `error_code != NONE` | `rightware/task_entry.py` |
| CLI JSON | Adds `error_code`; `generations[*].engine_error`; `generation_totals.engine_errors` | `rightware/task_cli.py` |
| Workflow | New experimental `te05e-live-qwen.yml`, triggered only by a request file on `exp/te05e-live-qwen` (no such branch or request exists). The task step records the exit code; a **verdict step fails the job unless PASS_LIMITED**; summary and sanitized upload run `if: always()` | `.github/workflows/te05e-live-qwen.yml`, `labs/te05e_live/verdict.py` |

**Not changed:** AgentPolicy, quotas, `max_calls=10`, `max_turns=10`, deadline 115 s, engine timeout 120 s,
tools, hosts, completion-gate evidence rules, `reply_json`, the TE-03/TE-04/TE-05 historical workflows, vendor/pin.
Sessions without the gate: A/B against `0ae3383` on the R3-C1 scenarios is identical (reply_json, text, nonce-normalized model messages).

## 3. Tests actually run (this environment)

* New `tests/test_te05e_error_evidence.py`: 16 tests OK, covering:
  1. engine error before any tool;
  2. error after a successful tool, with receipts preserved;
  3. simulated engine timeout reproducing the 4B shape (2 pages observed, then a 120 s cut → ERROR/ENGINE_TIMEOUT, both objectives PAGE_OBSERVED, overrun 66 s);
  4. generation past the deadline → HALTED/DEADLINE, not an error;
  5. one objective observed and one missing;
  6. receipts present before an error;
  7. missing engine metrics → `None`;
  8. premature answer;
  9. false completion claim followed by an engine failure;
  10. unauthorised tool → `CAPABILITY_NOT_AUTHORIZED` preserved through an error;
  11. unexpected failure without leaking exception text;
  12. workflow verdicts ERROR / INCOMPLETE / REVIEW / BLOCKED all fail the job; only PASS_LIMITED is green.

  It also checks that the gate-less reply shape is unchanged.
* Relevant modules OK: TE-02 10, TE-03 9, TE-04 3, TE-05 18, A1 15+16, A2 21, A3 29, issue #9 7,
  AgentPolicy 12+21. Browser 23 OK within the full suite.
* Full suite, pinned venv: **487 tests OK, 0 skipped** (baseline 471 + 16). Plain Python: 487 OK
  (227 vendor-dependent tests not run there).
* Mutation check: 7 deliberate regressions are each detected:
  * ERROR not enforced;
  * old zero-objective ERROR record;
  * fallback dropping receipts;
  * timeout misclassified;
  * verdict always green;
  * workflow `|| true`;
  * no outer catch.
* `actionlint` OK on the new workflow.

## 4. Confirmed vs not confirmed

* **CONFIRMED (code):** the ERROR path discarded diagnostics; the job reported infrastructure success as task success.
* **NOT CONFIRMED:** the cause of the historical 4B ERROR. `ENGINE_TIMEOUT` remains a hypothesis for run
  44121642913; its evidence cannot be recovered retroactively. The new code would have recorded the category.

## 5. Remaining risks / limitations

* Classification depends on exception types from the pinned vendor and httpx. An engine that wraps errors
  differently is classified `ENGINE_FAILURE` (safe, but less specific).
* The engine timeout is still a client timeout; the server may keep computing after it fires.
* On an engine timeout the deadline can already be exceeded by up to one 120 s generation; this is now measured, not prevented.
* The failed generation's wall time comes from the client clock; token counts are unavailable by nature.

## 6. Recommendations for TE-06 (not started)

* If authorised, one 4B run through the TE-05E workflow, with unchanged limits, to measure the real error category.
* If ENGINE_TIMEOUT is confirmed, reduce the prompt growth (page view size) before touching any budget.
