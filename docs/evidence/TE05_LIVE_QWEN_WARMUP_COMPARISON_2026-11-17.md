# TE-05 — Real local Qwen warm-up comparison: independent review (2026-11-17)

**Status:** Experimental live evidence / **Qwen 2B PASS_LIMITED twice**, **Qwen 4B REVIEW/ERROR**. Not product acceptance, not a merge authorization.

## Executive result

An operator-directed transition from Claude Code to ChatGPT caused two **overlapping 2B runs**: Claude had started a GitHub Actions inference after the initial repository check and the ChatGPT-operated one-shot job began before the new run appeared in the workflow listing. Both 2B runs completed. The separate Claude-operated 4B run completed with a failed task verdict. No additional model experiments are authorized or needed here.

| Property | 2B (Claude workflow) | 2B (duplicate independently generated) | 4B (Claude workflow) |
|---|---|---|---|
| GitHub Actions | [44120973970](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44120973970) | [44121272096](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44121272096) | [44121642913](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44121642913) |
| Request SHA | `70fcd27a9691bc443dd48a3672664b2d9e883730` | `5e12c3d3f8e4900d259cc4c2842db36b729e7f67` | `a7cebd920e70b5cfe42f3ef4f0a398c1ec3f9de5` |
| Local model | qwen3.5:2b (Q8_0) | qwen3.5:2b (Q8_0) | qwen3.5:4b (Q4_K_M) |
| Warm-up | 2.464s, OK | 2.605s, OK | 4.973s, OK |
| Actual task time | 84.980s | 51.149s | 181.418s |
| Complete task wall | 87.445s | 53.754s | 186.390s |
| IANA_RESERVED | PAGE_OBSERVED, receipt 1 | PAGE_OBSERVED, receipt 1 | **Not available in sanitized output** |
| IANA_EXAMPLE | PAGE_OBSERVED, receipt 2 | PAGE_OBSERVED, receipt 2 | **Not available in sanitized output** |
| Receipts | 2; web_open OK ×2 | 2; web_open OK ×2 | 2; receipt details discarded by ERROR reporting path |
| Model generations | 3 | 3 | 0 **recorded in output**, NOT proof that no inference occurred |
| Halt reason | NONE | NONE | NONE (error path; cannot interpret as a completed run) |
| A3 continuations | 0 | 0 | 0 recorded |
| Operational state | UNKNOWN_IDENTITY | UNKNOWN_IDENTITY | ERROR |
| Verdict | **PASS_LIMITED** | **PASS_LIMITED** | **REVIEW** |
| factual_verified / completion_verified | false / false | false / false | false / false |

**Same task/policy:** two code-owned IANA URLs; HTTPS public browsing only; OpenJarvis pin `f21d902f4d3bd7f0f3f138f1a4613019a394b549`; `max_calls=10`, `max_turns=10`, `deadline_seconds=115`, model engine timeout `120s`, `temperature=0.2`, no shell/filesystem/Windows actions or cloud LLM. All runs used `--warmup`, local Ollama 0.40.15 and verified Ollama model digests. Different Qwen sizes use different quantization.

## Primary evidence, actual archive inspection

- **2B Claude run:** artifact id `14346225573`, ZIP SHA-256 `c291f7cd3f5bfd8bb38ca755c3e33fa785fde91259544438541d1d418efcd86c`; confirms 2/2 PAGE_OBSERVED, 2 web_open OK, 3 generations, no halt and warm-up load time 2.055s. Model source SHA `4fd4925154cb9c33d1926a4395fe90c72ee70700`.
- **2B independent run:** artifact id `14345416840`, ZIP SHA-256 `61ddcf563ee4cffa8118f93b41c1cf157543c914753923d2113d685a9a10677e`; confirms same 2/2 with 2 web_open OK, 3 generations, no halt. Model source branch based exactly on TE-05 `0ae3383528e8da0ee4eda82982d830895c4968c1` plus isolated workflows and HANDOFF (no product source changes).
- **4B Claude run:** artifact id `14346126829`, ZIP SHA-256 `5b9f8e14248e874411ed3c403cb180a09fd1a508f711b44be2f23be04b6e1403`; confirms `verdict=REVIEW`, `operational_state=ERROR`, `limitations=["INCOMPLETE_OBJECTIVE_EVIDENCE"]`, `receipts_count=2`, `objectives=[]`, `generation_metrics=[]` (in the **public result**, not an inference-free execution), task duration 181.418s. Warm-up load 3.827s. stderr empty. Cannot identify the exact underlying engine exception or which objectives were observed.

**Important CI discrepancy:** GitHub Actions run `44121642913` has conclusion `success`, while its published verdict is `REVIEW` and the task is `ERROR`. This means **workflow infrastructure succeeded but the product task failed**. The run must NOT be counted as a model benchmark PASS. Correcting exit policy should be a separate reviewed change; do not rewrite historical evidence.

## Interpretation and code-level issue identified for follow-up

- The contracted task in `AgentSession._apply_completion_gate` builds an ERROR CompletionResult with **empty objectives** when the underlying agent reply is ERROR. `TaskEntry._run_trusted` requires exactly two objectives even on the ERROR path, and substitutes the generic `INCOMPLETE_OBJECTIVE_EVIDENCE` error. It discards sanitized per-generation and receipt diagnostics in that branch. This explains why the 4B public result lacks objective and generation data and masks the original exception; it does **not** establish which exception triggered the engine ERROR.
- `halt_reason_code="NONE"` on an ERROR result does NOT rule out a model HTTP client timeout; deadline is checked between turns. The 4B run took ~181s including ~5s warm-up, vs 115s task deadline, but no detailed Ollama audit/exception metadata was published, so timeout or CPU inference delay is a hypothesis rather than a proven root cause.
- The 2B has now demonstrated efficient **two-step real browser tool use** with fixed contract objectives in 2/2 samples; both A3 results correctly remain UNKNOWN_IDENTITY because publisher identity and factual summaries have not been independently verified.
- The 4B **has not** demonstrated an ability to complete the same task. The model packs differ in size and quantization and CPU inference throughput; this experiment cannot support a general model-quality ranking.

## Next recommendation (not implemented here)

**TE-05E error-path preservation:** A small, fake-first fix should preserve sanitized error category and receipt/generation metrics when `AgentSession` fails, without spilling raw exceptions/prompts/URLs. Then test the no-tool/timeout path deterministically. Review whether the workflow should mark `REVIEW` as failure. Avoid automatically rerunning Qwen or increasing permissions/time budgets. Nothing here justifies switching to Goose.

**Continuity:** TE-05 implementation PR #16 remains DRAFT, no merge. Temporary validation CI #17 was closed without merge. The ChatGPT experiment branch `exp/te05-live-qwen-20261117` contains unique workflow/checkpoint evidence and is NOT a replacement for PR #16. Claude experimental branch `exp/te05-live-qwen` was observed separately and was not edited by ChatGPT.
