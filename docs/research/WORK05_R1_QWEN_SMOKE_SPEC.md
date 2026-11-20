# RIGHTWARE JARVIS v2.0 — WORK-05 R1-F: real-Qwen smoke of the product agent (PREPARED, NOT RUN)

**Status:** runner, workflow and tests are committed. **No inference has been run.** The run needs an explicit operator authorisation naming the exact HEAD.

## What is tested

The real product path: `AgentSession.run` → pinned `OrchestratorAgent` → `OllamaEngine` (Qwen3.5:4b, digest `d8b0f5e9…`) → `AgentPolicy` → `web_read` with the pinned connection → `ToolOutcome` → `AgentReply`.

| Parameter | Value |
|---|---|
| Instruction (fixed) | «Lê a página https://example.com/ com a ferramenta web_read e diz-me, numa frase em português, para que serve este domínio segundo a própria página. Cita o endereço.» |
| Page | `https://example.com/`: public and stable, an IANA example domain with no personal data and no login |
| Capabilities | `web` only. `WindowsActions` not constructed (`actions=None`); no shell, filesystem or other tool exists in the registry |
| Limits | 4 turns, 512 tokens per response, 3 tool calls, 300 s deadline (policy and engine) |
| Runner | `python -m rightware.agent_smoke --expect-sha <HEAD> --expected-digest <digest> --evidence-dir DIR` |
| CI | `.github/workflows/work05-qwen-smoke.yml`. **Inert**: it runs only when a push to this branch adds or changes `ops/work05_smoke_request.json` (`experiment`, `request_id`, `authorized_by`) |

**Gates before inference:**
- request schema and ref;
- exact SHA, ancestry on the branch, pin and clean tree;
- at least 4 vCPU and 14 GiB;
- the full product suite in the venv with **no skips**;
- Ollama 0.40.15 checked by SHA-256, loopback only;
- model digest compared, fail closed.

**Evidence**, uploaded always, with `SHA256SUMS`:
- `gates.jsonl` and the product test log;
- `smoke/smoke.json`: plan, preflight, the **model responses recorded at the engine boundary** (tool name, URL, argument hash, content length), the reply JSON (outcomes, sources, flags, `verification`) and the verdict;
- `smoke/audit.jsonl` and the console log.

## How «Qwen really called the tool» is distinguished from a scripted call

- `RecordingEngine` wraps the **real** engine and records only what `engine.generate` returned. FAKE tests use scripted engines whose `engine_id` is not `ollama`.
- `classify()` returns **INCOMPLETE** unless `engine_id == "ollama"` **and** the preflight digest equals the expected one (tested).
- PASS requires a `web_read` proposal **in the recorded model responses** for the fixed URL. An executed outcome alone is not enough.

## Classification (deterministic, `rightware/agent_smoke.classify`, tested)

- **PASS:** all of the following hold:
  - real pinned engine;
  - the model proposed `web_read` for `https://example.com/`;
  - no other tool proposed;
  - at most 3 proposals;
  - completion `ANSWERED_WITH_SOURCES`;
  - the fixed page recorded as a source;
  - no `UNSUPPORTED_READ_CLAIM`, `UNVERIFIED_EFFECT_CLAIM` or `AUDIT_FAILED` flag;
  - a non-empty answer.
- **FAIL:** the real model took part, but any PASS condition is missing (for example it never proposed the tool, proposed another tool, the run halted, or a claim flag was raised).
- **INCOMPLETE:**
  - not a real pinned-model run;
  - engine or audit error;
  - the fixed page unreachable or erroring from the runner (an external cause, not a model failure);
  - preflight blocked (exit 2).
- **Always reported, never a PASS condition:**
  - `answer_mentions_page_terms`: whether the answer uses words that appear on the page;
  - `answer_factually_verified=false`.

A source record proves what was read, not that every sentence is true.

## Authorisation needed (operator)

1. The exact HEAD to test: a commit on `feat/work05-product-agent` after this one, with green product CI.
2. Approval to push `ops/work05_smoke_request.json` (`request_id: 1`). This single change triggers one run.
3. Acknowledgement that the GitHub runner makes outbound requests to `example.com` and `registry.ollama.ai` (model pull).

## Expected cost

About 5–10 minutes on CPU, extrapolated from earlier CPU runs (INFERÊNCIA).

## WORK-06 revision (2026-11-12): authorisation on `develop`

The workflow listens to **`develop`** only. The old trigger, `feat/work05-product-agent`, was obsolete after branch consolidation.

**Request file** `ops/work05_smoke_request.json` (exact keys):
```json
{"experiment": "WORK05_PRODUCT_AGENT_REAL_SMOKE", "request_id": 1,
 "approved_code_sha": "<40-hex develop HEAD approved by the operator>",
 "plan_sha256": "<python -m rightware.agent_smoke --plan-only → plan_sha256>",
 "authorized_by": "<single line>"}
```

**Gate** (`rightware/agent_smoke.check_request`, before any install or model; tested):
1. The approved code SHA and the triggering request commit SHA are different, and both are recorded.
2. The request commit changes **only** the request file relative to the approved SHA, and the approved SHA is its ancestor. Consequence: the approved SHA must be the `develop` HEAD **immediately before** the request commit. Any intervening commit, including documentation, voids the request.
3. `request_id = previous + 1 = number of request commits`. This makes each request single use and refuses replays and gaps.
4. GitHub re-runs (`run_attempt > 1`) are refused; a new run needs a new request.
5. `plan_sha256` must equal the fixed plan: model, digest, Ollama version, pin, URL, instruction, capabilities and limits.

**Preflight** (runner): the running code must equal the approved code apart from the request file. The digest is fixed (not a parameter) and the pin is checked. Evidence records `approved_code_sha`, `trigger_sha` and `plan_sha256`.
