# TE-04 — Qwen3.5 2B vs 4B: fixed public task, observed outcomes

**Date:** 2026-11-17
**Classification:** LIVE_MODEL_TESTED / BOTH INCOMPLETE / REVIEW_REQUIRED. No production acceptance.
**Architecture:** Existing RIGHTWARE OpenJarvis OrchestratorAgent + AgentSession/AgentPolicy + A1/A2/A3. No Goose integration.

## Evidence index

| Trial | GitHub Actions | Full request SHA | Artifact | SHA-256 artifact ZIP |
|---|---|---|---|---|
| Qwen3.5 2B | [44103342916](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44103342916) | `2d895918ab3e98d63bbf5bd46893e1343bff0f60` | `te03-iana-qwen2b`, id 14335624986 | `2c2a85350f0525ecfc0197ec50962a541206c1edab9463e088354c896b3f31d2` |
| Qwen3.5 4B | [44107892549](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44107892549) | `425d29caa82e0a660137cd80e0c1034101e11f33` | `te04-iana-qwen4b`, id 14339129559 | `a0e80da0cfdcd37d2ac7b8e89329aa3cced6730e54dfb790d2af4efbbfb7bbe7` |

The artifacts were downloaded from GitHub and inspected as actual ZIP bytes. Each includes the typed `task.json`, `verdict.json`, model metadata, version, exit code and empty stderr. No prompt transcripts or raw page text are included.

## Identical controls, different models

- Platform: GitHub-hosted Ubuntu 24.04 CPU runner, Ollama `0.40.15`, distribution SHA-256 verified; OpenJarvis gitlink remains `f21d902f4d3bd7f0f3f138f1a4613019a394b549`.
- Both tasks: public GET/browse only on `www.iana.org`, code-owned objectives `IANA_RESERVED` = `https://www.iana.org/domains/reserved` and `IANA_EXAMPLE` = `https://www.iana.org/help/example-domains`.
- Host code opt-in `--allow-public-read` required. Same default Portuguese request, same `max_calls=10`, `max_turns=10`, `max_tokens=768`, `temperature=0.2` and `deadline_seconds=115`; no shell/Windows/filesystem capabilities.
- Actual model profiles were not quantization-matched: 2B is `qwen3.5:2b`, digest `0689d44085e06d165161a8a9a1731344278cfb5aade63a3c3dbdb48ab54b130a`, **1.9B Q8_0**; 4B is `qwen3.5:4b`, digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`, **4.2B Q4_K_M**. Thus the experimental variable is the packaged model variant, not only parameter count.

## Observed comparison

| Result | 2B | 4B |
|---|---|---|
| Live model and local Ollama initialized | YES | YES |
| IANA_RESERVED | PAGE_OBSERVED (receipt 1) | PAGE_OBSERVED (receipt 1) |
| IANA_EXAMPLE | MISSING | MISSING |
| `operational_state` | HALTED | HALTED |
| `receipts_count` | 10 | 3 |
| `halt_reason_code` | NOT RECORDED in TE-03 | **DEADLINE**, code-owned enum in TE-04 |
| `factual_verified` | false | false |
| `completion_verified` | false | false |
| Exit code | 3 (review) | 3 (review) |
| Workflow outcome | FAIL as designed: missing objective | FAIL as designed: missing objective |

**4B sanitized receipt sequence**:
1. `web_open` -> `OK` (first required page observed).
2. `web_follow` -> `REFUSED` (not executed as requested; exact argument/denial reason intentionally absent).
3. `web_find` -> `UNKNOWN` (the diagnostic allowlist did not recognize its recorded status; do **not** assert tool success, failure or a specific reason).

The 4B process reached the **115-second task deadline** per host `halt_reason_code=DEADLINE`. The duration of the GitHub step also includes execution overhead, and is not a precise inference latency measurement.

For the older 2B run, ten receipts coincide with `max_calls=10` and the final state is `HALTED`. Tool budget exhaustion is a strong hypothesis, **not independently confirmed**, because that run did not emit the halt reason or individual call statuses.

## Interpretation

- **Neither** default model completed the two public source-observation objectives in a single bounded run.
- 4B did NOT produce a better outcome than 2B under equal host limits. But this is one attempt each, on CPU, with different default quantization, so it does not rank the intrinsic reasoning quality of the models.
- The executor, policy and completion gate correctly prevented the claim of verified task completion; an observed first page did not count as two.
- 4B diagnostic `DEADLINE` distinguishes a model/runner throughput constraint from the 2B likely call-budget problem.
- Repeating with longer deadlines or more tools would be a **different experiment**, not evidence of success at the fixed constraints.
- These runs do not prove autonomous recovery, factual Portuguese answer correctness, file comparisons, Windows operations, tool proxy security against adversarial inputs, or necessity of Goose.

## Recommendation — next narrow engineering experiment

**Do not integrate Goose yet.** First run a read-only no-model inspection of why repeated/ineffective calls occur: aggregate the existing policy decision log into a small set of reason codes (never raw arguments) and distinguish tool denial, unavailable link, HTTP/redirect and model timeout. If the cause is prompt/tool misuse, improve **task planning/grounded tool choice**; if unavoidable CPU latency, benchmark the same variant on a GPU or with a separately approved deadline.

Require an objective-level proof before declaring the JARVIS task executor usable in product. No unconditional shell, file or OS grants.

**Branch status:** all PRs remain DRAFT and stacked; no merge or product release.
