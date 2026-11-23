# RIGHTWARE JARVIS v2.0 — WORK-05 R1: security review of the product agent

**Branch:** `feat/work05-product-agent`. **Baseline:** `188e1b73d1ada1e80aef3d0f65b0d7a2447cda2f` (code equal to `6fedaca`, CI `43099989107` success: 94 tests, 0 skipped in the venv).
**Method:** deterministic probes, with no external network and no real internal endpoint. Socket-level calls are simulated with `unittest.mock`; HTTP uses `httpx.MockTransport`. The probe script is reproduced in the R1 regression tests. **No Qwen inference.**

## R1-A findings (reproduced on the baseline before any fix)

| ID | Severity | Finding | Evidence (probe output) | Affected code | Correction |
|---|---|---|---|---|---|
| F1 | **P0** | **DNS rebinding.** `check_url` validates the addresses from its own resolver, but httpcore re-resolves the host name inside `socket.create_connection`. The TCP connection, and therefore the GET request, can go to an address that was never validated. The post-connection peer check only rejects the **response** | Validated `93.184.216.34`; connection attempted to `('rebind.example', 443) → ['127.0.0.1']` | `web.py` `HttpxFetcher.fetch` (default httpx transport) | Pinned network backend: connect only to an IP that the same validated resolution approved, with TLS SNI and certificate verification still on the URL host name. Keep the peer check as a second layer (R1-B) |
| F2 | P1 | **Batch not atomic.** `batch_guard` checks only names and schemas. A batch whose later call is not allowed (capability or quota) still executes its earlier calls | `[web_read, windows_action]` with only web allowed → first approved, second denied. Four `web_read` calls with a limit of 3 → `[True, True, True, False]` | `policy.py` `batch_guard` | Pre-validate the whole batch: names, schemas, session capabilities, per-tool and global quotas counting the batch, cancellation and deadline. Any failure denies every call (R1-C) |
| F3 | P1 | **Deadline not rechecked at execution.** `authorize_execution` checks cancellation and arguments but not the deadline | Approved at t=0 with a 10 s deadline; execution at t=99 still authorised | `policy.py` `authorize_execution` | Recheck the deadline (and cancellation) at the boundary (R1-C) |
| F4 | P1 | **Audit failure leaves a dirty state.** When the audit file cannot be written, the hook raises **after** it has consumed a quota slot and stored an approval key. The orchestrator then denies the call, so nothing executes, but the policy state is wrong. A failure to write the post-execution audit was not reported | `FileExistsError`; 1 orphan approval; `per_tool={'web_read': 1}` | `policy.py` `_record`/`before_tool_call`; `session.py` `_PolicyTool.execute` | Mandatory audit: write the decision **before** mutating state, and deny (fail closed) if it cannot be persisted. If the post-execution record fails, mark the reply as an error (R1-C) |
| F5 | P1 | **HTTP 4xx/5xx counted as a source.** Any accepted content type returns a `Page`; the session marks it `OK` and lists it under «Fontes lidas» | HTTP 404 and 500 → `Page(status=404/500)` → OK | `web.py` `fetch`; `session.py` `_web_read`/`_compose` | Only 2xx with non-empty text is a retrieved source. Other statuses are an explicit `HTTP_ERROR` outcome without content. Separate «resposta recebida», «conteúdo obtido», «fonte registada» and «exactidão não verificada» in the reply (R1-D) |

**To verify during R1-C/D:** completion after tool calls that the policy refused but that produced no outcome. The baseline returns `ANSWERED` (candidate false-success classification). No benchmark code is in `rightware/agent` (an import-level test already exists).

**C1–C11 gaps:** C2 (F3), C3 (F2), C6 (F5), C7 network layer (F1), C10 (F4). C8 and C9 have no current product tool. C11 is satisfied.

## Corrections (R1-B, R1-C, R1-D)

| ID | Status | Commit | Tests written first (failing on the baseline) | Mutations killed |
|---|---|---|---|---|
| F1 | **Fixed**: pinned connection to the validated IP; TLS name kept | `3c220ee` | `test_agent_network.py` (8) | 7/7 |
| F2 | **Fixed**: whole-batch pre-validation | `58e1ba8` | `test_agent_policy_r1.py` BatchAtomicity (4 failed before) | 3/3 |
| F3 | **Fixed**: deadline rechecked at the boundary | `58e1ba8` | BoundaryRecheck (1 failed before) | 1/1 |
| F4 | **Fixed**: decision persisted before any state change; fail closed; post-execution loss = ERROR | `58e1ba8`, `df222b2` | MandatoryAudit (3 failed before) + 2 session tests | 4/4 |
| F5 | **Fixed**: `HTTP_ERROR`/`EMPTY_CONTENT` are not sources; `verification` separates the five levels | `df222b2` | `test_agent_session_r1.py` (12 failures before) | 4/4 |
| F6 (new, found in R1-C) | **Fixed**: only-refused tools used to give `ANSWERED`; now `TOOLS_REFUSED` with an explicit status line | `df222b2` | `test_only_refused_tools_is_not_an_answered_success` | 1/1 |
| F7 (new, found in R1-B) | **Fixed**: a malformed IPv6 or port raised `ValueError` instead of a controlled refusal | `3c220ee` | `MalformedUrls` | 1/1 |
