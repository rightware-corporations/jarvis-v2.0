# WORK-07 — Real gates prepared (Phase 4 site preflight, Phase 5 Qwen): NOT RUN

**Status:** code, workflows and tests are on `develop`. **No external browsing and no Qwen inference have been run.** Each gate needs its own explicit operator authorisation, naming the exact approved commit.

Runner and evaluator: `labs/work07_rfc_gate/gate.py` and `labs/work07_rfc_gate/evaluator.py`. The evaluator, holding the reference answers, lives outside the product, and the model never receives it.

## Authorisation protocol (same as WORK-06, per gate)

1. The operator approves an exact **code** commit on `develop` (CI green) and the gate's plan digest.
2. A separate **request** commit, immediately after that HEAD, changes **only** the gate's request file:
   ```json
   {"experiment": "...", "request_id": N, "approved_code_sha": "<40-hex>",
    "plan_sha256": "<digest>", "authorized_by": "<single line>"}
   ```
   - `request_id` is the previous value + 1, so it is single use.
   - GitHub re-runs are refused.
   - Any other intervening commit voids the request.
3. The workflow GATE 0 validates this with `labs.work07_rfc_gate.gate --check-request <op>` before installing anything.

| Gate | Request file | Workflow | Experiment | `plan_sha256` |
|---|---|---|---|---|
| Phase 4: site preflight (no model) | `ops/work07_site_preflight_request.json` | `.github/workflows/work07-site-preflight.yml` | `WORK07_RFC_SITE_PREFLIGHT` | `b0e4ac7849b7ad14d19ca4c61da7f0929fa1ef351c5b0a5f633419eba6178ef4` |
| Phase 5: real Qwen | `ops/work07_qwen_request.json` | `.github/workflows/work07-qwen-rfc.yml` | `WORK07_RFC_QWEN_GATE` | `44d9664812cd98648f17691508f4adf9710463ef20354b09ed4d12e144a02d94` |

**Recommended order:** Phase 4 first. If it gives `NOT_READY`, for example because the search needs JavaScript, the Qwen gate should not be requested: the result would be INCOMPLETE, and the browser decision must be reviewed.

## Phase 4 — real-browser preflight (no LLM)

**What runs:** the real `PublicBrowser` with `HttpxFetcher` (pinned transport), host allowlist `www.rfc-editor.org` only, on a GitHub runner.

**Fixed driver** (evaluator side, deterministic):
1. Open `https://www.rfc-editor.org/search/`.
2. List the search fields.
3. For 9110 and 9112, in each field, type `N` and then `RFC N` and submit with GET.
4. Look for a link `/rfc/rfcN.html`, or via `/info/rfcN`, and follow it.
5. Record the HTTP status, final URL, title, SHA-256, real TCP connections (host, IP, port), field names and form actions, and view excerpts.

At most 12 page loads.

**Result:**
- `READY`: both documents opened with HTTP 200 and a title.
- `NOT_READY`: the reasons are recorded.

**Network requests this authorises:**
- the runner to `www.rfc-editor.org` (port 443, GET only);
- package downloads for the venv (PyPI/uv via GitHub).

No Ollama, no model.

**Expected cost:** about 3 minutes (INFERÊNCIA).

## Phase 5 — one real Qwen3.5:4b run

**Model input:**
- the user's instruction (exact text in the plan);
- the product system prompt with the scope «sites autorizados: www.rfc-editor.org»;
- the start page `https://www.rfc-editor.org/search/`.

No answers, document URLs or titles are supplied.

**Capabilities:** `browse` only (`web_open`, `web_type`, `web_submit`, `web_follow`, `web_find`). There is no `web_read`, `windows_action`, shell or filesystem.

**Limits:**
- 14 turns, 768 tokens per response, 900 s deadline;
- 14 tool calls in total, with per-tool limits: open 3, type 4, submit 4, follow 6, find 6.

**Recorded at the engine boundary:**
- every response: tool names, public arguments (URL, F#/L#, query text) and final text;
- browser events: operation, URL, status, title, SHA-256, query, real connections;
- the policy audit (hashes);
- the product reply JSON and the evaluator verdict.

**Classification** (`evaluator.evaluate`, tested):
- **PASS**, which requires all of the following:
  - real engine `ollama` with the pinned digest;
  - the model itself proposed `web_type` and `web_submit`;
  - a results page was retrieved OK;
  - a result link was followed OK;
  - RFC 9110 and RFC 9112 were **actually opened** (canonical `/rfc/rfcN(.html|.txt)` URL) with the official title on the page;
  - in the **model's own text**, each RFC is paired with its official title and purpose (semantics versus HTTP/1.1), with no swap, and both official URLs are cited;
  - only `browse` tools, no attempt to leave the site, `ANSWERED_WITH_SOURCES`, not halted, no claim or audit flags, within the call budget.

  A memory-only answer cannot pass, because no document was opened. `needs_human_review` is always true.
- **FAIL:** the environment worked, but any PASS condition is missing, for example no search, documents opened directly without navigation, a wrong pairing, a missing URL, a 404 on a URL the model invented, or a navigation attempt outside the site.
- **INCOMPLETE:**
  - not the real pinned model;
  - engine or audit error;
  - a site, browser or runner failure (connection failure or timeout, HTTP 5xx/403/429, page without readable text, DNS or network refusal) that may explain the failure. The model's reasons are then recorded but not scored.

**Network requests this authorises:**
- `www.rfc-editor.org` (GET, from the agent);
- `registry.ollama.ai` (model pull);
- GitHub release download of Ollama 0.40.15 (checked by SHA-256);
- PyPI via uv.

**Expected cost (INFERÊNCIA):** 10–30 minutes on CPU, because the context grows with each page (about 3.5 k characters per view). The workflow timeout is 75 minutes.

## What the operator must authorise, verbatim elements

1. **Phase 4:** «AUTORIZO o preflight WORK-07 do site RFC Editor, sem modelo, `request_id: 1`, código aprovado `<SHA do HEAD de develop>`, plano `b0e4ac78…ef4`».
2. **Phase 5** (only after Phase 4 is `READY`), a separate authorisation: «AUTORIZO uma execução real Qwen3.5:4b WORK-07, `request_id: 1`, código aprovado `<SHA>`, plano `44d96648…d94`, limites 14 turnos / 14 chamadas / 768 tokens / 900 s, apenas `browse` em `www.rfc-editor.org`».

Any code change after approval changes the approved SHA, so a new authorisation is needed. Any change to the plan changes its digest.

## R1 revision (2026-11-12): document validation and acceptance separated from execution

**Document validation** (`evaluator.check_document`, shared by the preflight and the Qwen evaluator). A document only counts as opened if all three hold:
- HTTP status exactly **200**;
- after any redirect, the final URL is the canonical URL of **the same** RFC: `https://www.rfc-editor.org/rfc/rfcN`, `.html` or `.txt`;
- the page title is exactly the official title, optionally prefixed with «RFC N:» or «RFC N -».

The preflight returns `READY` **only** if RFC 9110 and RFC 9112 are both validated in this way. It records, per document:
- the link that was followed and the final URL;
- `redirected`, the title and the problems found.

These cases give `NOT_READY` (all tested):
- missing, wrong or swapped title;
- redirect to the other document, to a non-document page or off the site;
- HTTP 203 or 503.

**Workflows: technical execution versus acceptance.** Each WORK-07 workflow has two separate steps:

1. `TECHNICAL EXECUTION — …`: green means the runner completed. **It is not an acceptance verdict.** The exit code is written to `technical-exit.txt`.
2. `ACCEPTANCE VERDICT — fails unless the verdict is READY/PASS` (`if: always()`): runs `gate --acceptance <op>` and writes `acceptance.json` to the evidence and to the job summary. It **fails the job** for `NOT_READY`, `FAIL`, `INCOMPLETE`, a missing or unreadable verdict, or a BLOCKED or failed runner.

Evidence preservation and upload remain `if: always()` and run after the verdict, so the evidence is uploaded in every case.

**Consequence:** a green job means technical completion **and** an accepted verdict. In any other case the job is red, and the technical step tells you whether the runner ran at all.

The plan digests are **unchanged**, because these are code corrections covered by the approved SHA:
- `b0e4ac78…ef4` (site preflight);
- `44d96648…d94` (Qwen).
