# TE-05 live acceptance — Qwen3.5 2B then 4B, one run each (17/11/2026)

**Nature:** real local inference on GitHub-hosted CPU runners (Ollama 0.40.15), real public network to
`www.iana.org`. One run per model, no retries. This is limited operational evidence, **not** product
acceptance, not factual verification, not a general model ranking.

Branch `exp/te05-live-qwen`; approved code commit `4fd4925` (= TE-05 head `0ae3383` + one-shot workflow
+ HANDOFF only). OpenJarvis pin `f21d902`. Limits unchanged: IANA preset objectives, `max_calls=10`,
`max_turns=10`, `deadline_seconds=115`, engine client timeout 120 s, `--warmup`.
Verified from the job logs and the GitHub API (artifact ZIPs could not be fetched from this session:
the artifact blob host is blocked by its network policy; ZIP SHA-256 values are those printed by the upload step).

| | Qwen3.5 2B (request 1) | Qwen3.5 4B (request 2) |
|---|---|---|
| Run / job | [44120973970](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44120973970) / 134171895374 | [44121642913](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44121642913) / 134174303312 |
| Request SHA | `70fcd27` | `a7cebd9` |
| Model digest (verified in job) | `0689d440…130a` (Q8_0) | `d8b0f5e9…2c04` (Q4_K_M) |
| FAKE suite in job | 471 OK, 0 skipped | 471 OK, 0 skipped |
| Verdict | **PASS_LIMITED** | **REVIEW** |
| Operational state | UNKNOWN_IDENTITY | **ERROR** (`INCOMPLETE_OBJECTIVE_EVIDENCE`) |
| IANA_RESERVED / IANA_EXAMPLE | PAGE_OBSERVED (r1) / PAGE_OBSERVED (r2) | not available (error path) |
| Receipts | 2: `web_open` OK ×2 | 2 counted; events discarded by error path |
| Reason codes | none | not available |
| Halt reason | NONE | NONE (error path) |
| Continuations | 0 | 0 recorded |
| Generations (task) | 3 (2 tool calls proposed) | 0 exported (error path; inference did occur) |
| Prompt / completion tokens | 7 546 / 484 | n/a |
| Load / prompt eval / eval (s) | 0.003 / 50.312 / 34.352 | n/a |
| Warm-up | OK, 2.464 s wall (load 2.055 s) | OK, 4.973 s wall (load 3.827 s) |
| Task wall | 84.980 s | **181.418 s** |
| Derived tools + overhead | 0.241 s | n/a |
| Total wall | 87.445 s | 186.390 s |
| Job status | success (infrastructure) | success (infrastructure — **not** task acceptance) |

A separate operator-run 2B job ([44121272096](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44121272096),
branch `exp/te05-live-qwen-20261117`, not started by this session) also reported PASS_LIMITED (2 receipts, 3
generations, task 51.149 s). See `docs/evidence/TE05_LIVE_QWEN_WARMUP_COMPARISON_2026-11-17.md` on that branch.

## Findings

* **FACT — 2B improved versus TE-03 on the same task and limits.** TE-03 2B: HALTED, 10 receipts, 1/2 objectives.
  TE-05 2B: both objectives observed with exactly 2 `web_open` calls, no denial, no halt, no continuation needed.
* **INFERENCE — the improvement comes mainly from stating the contract objectives to the model**, since the model
  opened exactly the two stated URLs. Warm-up cannot explain it: the 2B cold load was only ~2 s.
  N=1 here (N=2 with the operator's run); not a reliability estimate.
* **FACT — the time is spent on prompt processing, not model load.** For 2B, prompt eval was 50.3 s of 84.7 s
  of generation wall time; warm-up removed ~2–4 s of load. The prompt grows with each page view.
* **FACT — the 4B run ended in ERROR, after 181.4 s of task time, which exceeds the 115 s deadline.** In code, `AgentSession.run` returns
  ERROR when the engine raises. The pinned `OllamaEngine` turns an httpx timeout into `EngineConnectionError`.
  `TaskEntry` then replaces the zero-objective ERROR record with `INCOMPLETE_OBJECTIVE_EVIDENCE` and
  drops receipt events and generation metrics.
* **HYPOTHESIS (not verified) — a 4B generation hit the 120 s client timeout.** 181.4 s is consistent with about
  61 s of earlier turns plus one generation cut at 120 s. The deadline is checked only between steps, so it could not stop that generation.
  The exact exception was not exported.
* **FACT — no permission, budget or timeout was raised for the task.** Only the outer harness kill was raised to 320 s, and it did not fire in either run.
  No retries. Both claims stay `factual_verified=false` and `completion_verified=false`; the 2B result is `UNKNOWN_IDENTITY`, not `COMPLETE_VERIFIED`.

## Limitations

* The 4B diagnostics were lost on the ERROR path (code defect, below).
* The quantizations differ (Q8_0 vs Q4_K_M), the runners are shared CPUs, and N=1: no model ranking.
* The job conclusion is `success` even when the verdict is REVIEW (workflow design).

## Recommendation (requires separate authorization)

1. **TE-05E, FAKE first:** keep the safe diagnostics on ERROR (finite error category such as
   `ENGINE_TIMEOUT` / `ENGINE_UNAVAILABLE`, receipt events, reason codes, generation metrics), with no raw
   exception text. Add a deterministic test for an engine timeout in the middle of a task. Make the live workflow fail when the verdict is not PASS_LIMITED.
2. Only then, if authorised, run one more 4B attempt with the same limits, to find out whether the failure is the 120 s client timeout.
   Raising budgets is not recommended until that is known.
