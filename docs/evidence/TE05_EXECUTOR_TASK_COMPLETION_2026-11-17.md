# TE-05 — Executor diagnostics, trusted objectives, timing (17/11/2026)

**Nature of this evidence:** deterministic unit/integration tests with a FAKE model, mocked HTTP
(`httpx.MockTransport` through the real `HttpxFetcher`) and injected clocks. This is **NOT** real
Qwen, real network, voice, Windows or task-acceptance evidence. No real inference was run.

Branch `feat/te05-executor-task-completion` (based on `feat/te04-task-diagnostics-qwen4b` @ `5c7e0d4`).
OpenJarvis pin `f21d902` unchanged. `develop`/`main` untouched.

## 1. What changed

| Area | Change | File |
|---|---|---|
| Diagnostics | `DENIED` added to the safe receipt-status vocabulary (TE-04 receipt 3 was a DENIED shown as `UNKNOWN`) | `rightware/task_entry.py` |
| Diagnostics | Finite reason codes: policy denials (`DEADLINE`, `TOOL_BUDGET`, `REPEATED_ACTION`, …) and browser refusals (`UNKNOWN_LINK`, `HOST_NOT_ALLOWED`, …); unrecognised text → `OTHER` | `rightware/agent/diagnostics.py`, `browser.py`, `receipts.py`, `session.py` |
| Diagnostics | Per-generation numeric metrics: tokens, Ollama `load` / `prompt_eval` / `eval` / `total` seconds, client wall time, tool-call count, deadline overrun | `diagnostics.py`, `session.py` (`_GuardedEngine`) |
| Export | `TaskEntryResult.receipt_reason_codes`, `generation_metrics`, `continuations`; CLI JSON `receipt_reason_codes`, `generations`, `generation_totals`, `timing` | `task_entry.py`, `task_cli.py` |
| Objectives | Contracted runs (completion gate ON) state the code-owned objectives (id, label, approved URL) to the model, stating that they cannot be changed and grant nothing | `session.py` (`objectives_prompt`) |
| Continuation | IANA preset `max_continuations` 0 → 1 (existing `_CompletionEngine` blocking rules unchanged) | `task_contract.py` |
| Timing | Optional `--warmup`: ONE tool-free local generation before the task; reported separately; counted in `total_wall_seconds` | `task_cli.py` |
| Read-only accessor | `AgentPolicy.elapsed_seconds` (read-only; for the overrun metric) | `policy.py` |

**Not changed:** authorisation logic, policy decisions, quotas, `max_calls=10`, `max_turns=10`,
deadline 115 s, engine timeout 120 s, tool registry, hosts, `reply_json`, vendor/pin.
The diagnostics export no tool arguments, URLs, page content, model text, credentials or transcripts.

## 2. Tests actually run (this environment, pinned venv)

* New `tests/test_te05_executor_task_completion.py`: 18 tests, OK.
* Relevant modules: TE-02 10, TE-03 9, TE-04 3, issue #9 7, A1 contract 15, A1 product 16,
  A2 receipts 21, A3 completion 29, R3-C1 21, R3-C2 E1–E4 15 — all OK.
* Full suite, pinned OpenJarvis venv: **471 tests, OK, 0 occurrences of "skipped"**.
* Full suite, plain Python (no vendor): 471 tests, OK (214 vendor-dependent tests not run there).
* A/B against TE-04 base `5c7e0d4` on the five R3-C1 scenarios (sessions without the gate):
  `reply_json`, reply text and model-received messages identical, after normalising the per-run random page-frame nonce
  (the nonce also differs between two runs of the base itself).
* Mutation check: six deliberate regressions (DENIED masked, objectives removed, continuation
  removed, objectives without gate, denial code removed, warm-up dropped) are each detected by the new tests.
* One A1 interface assertion was updated to document the new `ToolOutcome.code` field (default `None`, absent from `reply_json`).

## 3. Regression scenarios (FAKE)

* **TE-04 shape:** open OK → `web_follow L99` REFUSED `UNKNOWN_LINK` → slow turn ends at t=120 s →
  `web_find` **DENIED `DEADLINE`** → `HALTED`/`DEADLINE`, no continuation; the third generation is
  recorded with `deadline_overrun_seconds = 5.0`.
* **TE-03 shape:** ten single-call turns (repeated `web_find`/`web_open`, unknown links) →
  codes `REPEATED_ACTION`×4, `UNKNOWN_LINK`×2; 1/2 objectives observed; `HALTED`.
  **Correction to the TE-05 read-only diagnosis:** with `max_turns=10` and `max_calls=10`, ten single-call
  turns exhaust both budgets together; the orchestrator stops on the turn limit first, so the code is
  **`TURN_BUDGET`**, not `TOOL_BUDGET`. TE-03's actual code remains NOT VERIFIED (it was not emitted at the time).
* Premature answer → exactly one continuation listing only the missing id → `UNKNOWN_IDENTITY` (never `COMPLETE_VERIFIED`).
* Second premature answer → `INCOMPLETE`; claimed completion without tools → `INCOMPLETE`, 0 receipts.
* Prompt injection in page text and in the instruction → off-site open refused `HOST_NOT_ALLOWED`, never fetched;
  objectives in the prompt unchanged; result `INCOMPLETE`.
* No new permissions: only the five `web_*` tools are offered; `allow == {"browse"}`; budgets 10/115/10.
* No continuation when the proposal budget is exhausted.

## 4. Timeout and deadline semantics (analysis, from code)

* `AgentPolicy` deadline (115 s) starts when `AgentSession.run` creates the policy, so it **includes the
  first generation's model load** (cold start). It is checked only **between** steps: before a
  generation (`_GuardedEngine`), at `before_tool_call`, at `authorize_execution` and in `batch_guard`.
  A generation already in progress is not interrupted. The deadline is therefore **not absolute**; the
  new `deadline_overrun_seconds` metric shows how far a run went past it.
* `OllamaEngine(timeout=120)` is an **httpx client** timeout (applied per connect, read, write and pool operation). When it fires,
  the client raises; whether the Ollama server stops the computation is NOT VERIFIED here and it may continue.
* `ToolExecutor` gives each tool 30 s in a worker thread; on timeout the thread may keep running
  (`TIMED_OUT` receipt, later `late`).
* Upper bound on task wall time is therefore above 115 s: up to one in-flight generation (≤ 120 s client timeout) plus,
  in the worst case, one 30 s tool timeout.
* `prompt_tokens` from the pinned engine is `max(reported, estimate)`; `prompt_tokens_evaluated` is
  what Ollama actually evaluated (KV-cache aware). Both are exported.
* A3 continuation needs an orchestrator turn left; with 10/10 budgets it can only fire when the model
  answers prematurely before its tenth turn and calls are left.

## 5. Limitations / open questions

* No real Qwen run: whether stating the objectives and allowing one continuation improves the 2B/4B
  outcome is **unknown**.
* Warm-up is opt-in (`--warmup`); the TE-04 workflow does not pass it yet.
* `service.log` and audit JSONL are still not uploaded by the TE-04 workflow.
* Identity remains `NONE`: `COMPLETE_VERIFIED` is still unreachable by design.

## 6. Recommended next experiment (requires separate explicit authorisation)

One real run per model (2B and 4B), same task and **unchanged** limits (10/10/115), with `--warmup`, publishing
the new JSON (`receipt_reason_codes`, `generations`, `timing`), to measure separately the cold load,
prompt processing and generation, and the effect of the stated objectives.
