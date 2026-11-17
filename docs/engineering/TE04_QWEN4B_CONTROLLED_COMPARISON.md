# TE-04 — Qwen 4B controlled comparison and non-sensitive halt diagnostics

**State:** Experimental implementation candidate, no acceptance or merge.
**Comparison baseline:** TE-03 live Qwen 2B one-shot [44103342916](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/44103342916) with 1/2 objectives observed, 10 receipts, HALTED, no factual verification.
**Evidence note:** From the 2B artifact alone the precise reason for HALTED is unknown, though 10 receipts coincide with max_calls=10. Prior runner wall time is not the same as the 115s policy deadline.

## What changed

- `rightware/task_entry.py`: diagnostic classification from **existing host-controlled** AgentReply.halted into a fixed enum only: NONE, TOOL_BUDGET, DEADLINE, TURN_BUDGET, CANCELLED, OTHER. The diagnostic can NEVER echo arbitrary model text or tool arguments. Bounded ordered receipts contain only sequence, tool allowlist and fixed result status; unknowns become OTHER/UNKNOWN. No policy behavior or tool allowance changed.
- `rightware/task_cli.py`: adds `halt_reason_code` and sanitized `receipt_events` to JSON result (without URLs or model commentary).
- `tests/test_te04_task_diagnostics.py`: synthetic fake-model test and rejection of unsanitized fields.
- `.github/workflows/te04-iana-live-qwen4b.yml`: a **single-shot** live Qwen3.5:4b run on a separate branch, only when its dedicated request file is committed; source must be exactly the immediate parent and request commit may change only that file.

## Comparability contract

The 4B run preserves the TE-03 public IANA task with:
- Same code-owned objective URLs, `www.iana.org` HTTPS read-only browsing
- Same existing OpenJarvis pin, Ollama v0.40.15 SHA256 and frozen venv
- Same `--allow-public-read --json` invocation, default Portuguese instruction
- Same `max_calls=10`, `max_turns=10`, `max_tokens=768`, `temperature=0.2`, `deadline_seconds=115`
- No shell, filesystem, WindowsActions, cloud LLM or model-controlled capability expansion
- Model change only: Qwen3.5:2b → Qwen3.5:4b
- New diagnostics are observational; they must not affect tool execution.

**Interpretation:** One 4B run cannot establish statistical reliability. If a model reaches both pages, A3 still returns UNKNOWN_IDENTITY because publisher identity is not independently verified. A green benchmark is not a claim that the model's Portuguese summary is accurate. A review/incomplete verdict is not a permission to silently increase tool quotas or add capabilities.

## Decision gate

When the Qwen4B run ends, inspect the actual job verdict and typed tool diagnostics, compare with the prior 2B artifact and classify:
1. Model/tool-call strategy difference likely if 4B observes both within identical limits.
2. Executor design limitation if both reach the same quota with inefficient repeated tools.
3. Infrastructure limitation if local Ollama/website/model download/runner fails before inference.
4. Insufficient evidence if diagnostics are unavailable or the two samples remain ambiguous.

Record exact source commit, run ID, model digest, result, receipt sequence, and next recommendation in HANDOFF. **Never rerun automatically.**
