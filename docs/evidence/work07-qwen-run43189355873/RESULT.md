# RIGHTWARE JARVIS v2.0 — WORK-07 Phase 5, request_id 3

## Historical verdict: **FAIL** (real Qwen3.5:4b, not a simulated model)

The *real* Qwen model executed successfully through the pinned Ollama/OpenJarvis runtime, but the autonomous research task did **not** satisfy its complete acceptance contract. This result must remain FAIL; later engineering improvements cannot reclassify the original evidence.

### Execution identity and boundaries

| Field | Verified value |
|---|---|
| GitHub Actions run | [43189355873](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43189355873), attempt 1 |
| Evidence artifact | [13930551641](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43189355873/artifacts/13930551641) |
| Request commit | `122797880ce850f4d154f9cc5f13a23c80ec3b64`, changed only `ops/work07_qwen_request.json` |
| Approved code | `5aba773a06f3d6a81c00bb2b0ee017a463e8bbd4` |
| Plan SHA256 | `44d9664812cd98648f17691508f4adf9710463ef20354b09ed4d12e144a02d94` |
| Model | Qwen3.5:4b, pinned digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04` |
| Capabilities | `browse` only; `www.rfc-editor.org`; no Windows actions, scripts, login or paid API |
| Limits | 14 turns, 14 proposed tool calls, 768 reply tokens, 900s deadline |
| Actual UTC inference | 2026-11-12 09:12:58–09:20:27 (approximately 7 min 30 s) |
| GATE 0–3 | All PASS, including strict single-use request and pinned model |
| Technical execution | `COMPLETED`, exit 0 |
| Acceptance | **FAIL**, `accepted=false`; GitHub workflow conclusion `failure` |
| Original ZIP SHA256 | `debbfca867ac73f20e006c8b6f6f7a97d4cdd635e067499feba3bdd211743eaf` |
| Archive checksums | 11/11 passed against original `SHA256SUMS`; ZIP hash matches GitHub artifact digest |

### Real autonomous tool sequence

The model produced **8 tool proposals in 9 response turns**:

| # | Proposed operation | Observed outcome |
|---|---|---|
| 1 | `web_open https://www.rfc-editor.org/search/` | OK — HTTP 200 |
| 2 | `web_type F1` with query `RFC 9110` | OK |
| 3 | `web_submit F1` | OK — RFC 9110 results HTTP 200 |
| 4 | `web_open https://www.rfc-editor.org/info/rfc9110/` | OK — official RFC information page HTTP 200 |
| 5 | `web_type F1` with query `RFC 9112` | OK |
| 6 | `web_submit F1` | OK — RFC 9112 results HTTP 200 |
| 7 | `web_open https://www.rfc-editor.org/info/rfc9112/` | Approved in audit, but **no recorded execution outcome** |
| 8 | `web_follow L37` | OK — official RFC 9112 information page HTTP 200 |

There were **five actual successful page-load events** (open, submit, open, submit, follow), all HTTP 200 at `www.rfc-editor.org`. They included the search, two GET search-result pages and the two official information pages. The fifth page-load was via `web_follow L37`, not a successful execution of proposal 7.

The model wrote a relevant Portuguese explanation: RFC 9110 (`HTTP Semantics`) defines HTTP semantics, while RFC 9112 (`HTTP/1.1`) specifies HTTP/1.1 message syntax and related concerns. The evaluator no longer reports the former Markdown title-attribution false negative.

### Why acceptance FAIL is justified

The four exact remaining reasons in `acceptance.json` are:

1. `RFC 9110 was not actually opened` — **the canonical RFC document**, not `/info/rfc9110/`.
2. `RFC 9112 was not actually opened` — **the canonical RFC document**, not `/info/rfc9112/`.
3. `official URL of RFC 9110 not attributed in the answer` — final answer cites `/info/rfc9110/` rather than `/rfc/rfc9110(.html|.txt)`.
4. `official URL of RFC 9112 not attributed in the answer` — final answer cites `/info/rfc9112/` rather than `/rfc/rfc9112(.html|.txt)`.

The final model answer incorrectly described its sources as *fontes primárias consultadas* even though only the information pages were read; `answer_factually_verified=false` in the product reply. It did NOT fabricate the HTTP distinctions, but it did not complete the document-opening instruction.

### Audit integrity / diagnostic

`tool_execution_audit` states `status: READABLE`, **15 entries**, `approved_without_outcome: 1`, `pending_tool_names: ["web_open"]`, `outcome_without_approval: 0`. Audit entry 13 is approval of `web_open /info/rfc9112/` and has no paired outcome. Proposal 8 `web_follow L37` *did* execute successfully. The exact cause of the OpenJarvis hook/runner mismatch remains unproven; do not conflate approval with execution.

The browser evidence includes `x-typesense-api-key=REDACTED` in search URLs. No new scope/permission expansion is justified by this failure.

### Interpretation and next work (recommendations, not approved changes)

WORK-07 R2 made the prompt describe generic primary-source verification and preferred `web_follow`, but **this single real Qwen attempt still stopped at the information pages**. The bottleneck is not the overall capacity to perform search, follow links, or explain the distinction. It is *autonomous task-completion control*: verifying that the requested source objects were actually opened before stopping, combined with diagnosing the orphaned `web_open` approval.

Recommendations for a subsequent engineering iteration: (1) inspect OpenJarvis tool-call execution and pre-call hook semantics against the frozen pinned vendor; reproduce approved-without-outcome deterministically; (2) expose generic machine-verifiable task progress and source-type evidence to the agent without embedding RFC answers or forcing a hardcoded route; (3) test end-of-task truthfulness when only summaries are opened, and no extra Qwen/GPU until an explicit next request authorization.

Historical sequence remains: site-preflight requests 1/2 NOT_READY, request 3 READY; Qwen request 1 FAIL real, request 2 BLOCKED at GATE 0 (no inference), request 3 **FAIL real**. The request 3 is consumed; **request 4 requires independent explicit authorization** after engineering/CI and exact-code validation.

## Provenance

Original evidence stays in GitHub Actions under its retention policy. This report and the companion `PROVENANCE.txt` are durable indexes, not byte-identical substitutes for the original artifact. Model, plan, pin, `main` and live product code were not changed by this reporting checkpoint.
