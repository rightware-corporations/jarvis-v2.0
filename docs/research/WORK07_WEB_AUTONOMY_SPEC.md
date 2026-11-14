# RIGHTWARE JARVIS v2.0 — WORK-07: public web autonomy and verified task completion

**Status:** IMPLEMENTATION SPECIFICATION / REFERENCE TASK PROPOSED. **Decision:** the operator prioritises research/navigation/task completion **before** voice integration. **Branch policy:** use `develop` only; do not create feature branches. `main` and `demo/issa-20261111` unchanged. **No new Qwen inference authorised by this document.**

## 1. Objective

Build on WORK-06 real smoke success (run `43117246194`, n=1, Qwen3.5:4b, model-proposed `web_read`) to demonstrate an actual **multi-step** user instruction. The previous smoke proved one public page could be read, not general search/navigation/completion; the model did **not** independently include the URL in its answer, and factual correctness was not verified.

Target: one user instruction -> agent interprets -> plans under bounded budgets -> uses **actual** public web-search interface -> follows relevant links -> reads two separate authoritative sources -> compares verified facts -> returns a truthful Portuguese answer with attributed URLs -> independently inspected PASS/FAIL/INCOMPLETE.

## 2. Fixed known-answer challenge: RFC Editor

**User-facing instruction (no answers or URLs of target pages supplied to the model):**

> “Jarvis, entra no site RFC Editor, pesquisa os documentos RFC 9110 e RFC 9112, abre os dois e explica qual define a semântica do HTTP e qual define o HTTP/1.1. Apresenta os títulos oficiais e os links das fontes.”

**Allowed starting point:** `https://www.rfc-editor.org/search/` (actual public search UI).

**Gold/reference facts — evaluator only, never in product prompt/tool output:**
- RFC 9110: official title **HTTP Semantics**, June 2022, describes shared HTTP semantics. `https://www.rfc-editor.org/rfc/rfc9110.html`
- RFC 9112: official title **HTTP/1.1**, June 2022, specifies HTTP/1.1 message syntax, parsing and connection management. `https://www.rfc-editor.org/rfc/rfc9112.html`
- Each answer must pair the correct RFC number/title/subject and give the corresponding exact official source (normalised equivalent canonical RFC Editor URLs accepted).

**Authoritative evidence:** RFC Editor original HTML publications at the URLs above. External site availability and dynamic search UI can vary; browser access failures are **INCOMPLETE** and must not be represented as cognitive FAIL.

## 3. Architecture / boundaries

- Read real `rightware/agent/{policy,web,session}.py` and pinned OpenJarvis before implementing. Retain `AgentSession` and `AgentPolicy` as the **single policy enforcement path**. No benchmark oracle in the product.
- Existing `web_read` is read-only HTTP GET; it is **not** an interactive browser. Implement a *separate, explicit, small* public-browser/search adapter rather than pretending `web_read` can click/type. Inspect pinned OpenJarvis capabilities and tradeoffs; if Playwright/Chromium is needed, isolate and pin dependencies outside upstream's frozen lock and assess deployment cost.
- Minimal semantic capabilities: open allowed public page; inspect visible/search inputs and links; enter a **public non-sensitive search query** in the RFC Editor search field; activate the recognised search action; follow safe public result links; extract bounded visible text. No arbitrary shell, JavaScript evaluation, filesystem tool, downloads, uploads or authenticated profile.
- A single **low-risk public-research capability grant** may cover navigation, search-field typing and reading across the task, without repeated confirmation. Distinguish that from arbitrary form submission; credential input; posting, sending, purchasing or modifying data, which are **not implemented** and must fail closed. The agent may never bypass the registry or capability limits.
- Browser sandbox: fresh temporary unauthenticated profile; per-task hostname allowlist (`www.rfc-editor.org` and any separately approved minimal dependencies), redirects and browser-origin requests constrained; block private/loopback/metadata/network-local IPs, internal URLs, non-HTTP(s), browser-native privileged schemes, unknown POSTs, downloads, new window escapes and unexpected navigation. Browser's DNS/network controls must be proven to restrict **real connections**, not only the page URL. If real egress isolation cannot be demonstrated, stop at deterministic tests, not live-browser approval.
- Budgets: bounded turns/queries/pages/actions/characters/time; policy audit per proposed tool call, grant, execution and source; bounded retries; cancellation; stop on tool failure; protect against prompt injection in public pages.
- Browser tools should expose semantic elements, not unrestricted mouse/keyboard actions. Keep controls stable and accessible. No webpage-origin instructions may become agent instructions.
- Never claim success merely because the Qwen model knows the answer or fabricates page URLs. Runtime execution evidence is mandatory; source provenance alone does not prove factual correctness.

## 4. Validation ladder

**A — Design/preflight (no real Qwen):** inspect, document architecture, identify browser dependencies and safety risk. Persist HANDOFF.

**B — Deterministic tests (FAKE):** real semantic browser adapter with controlled local fixture (search field, results, two documents), *not a fake that makes the tool calls on behalf of the model*; mock selectors where needed; injection and redirects; non-allowed networks; timeouts; quotas; fail-closed audit, refusals, interruption; test forbidden form submission and downloads. The reference-answer oracle lives only under `tests/` or `labs/`.

**C — Real-browser preflight (without LLM):** verify that `https://www.rfc-editor.org/search/` works in the selected isolated environment and yields traversable results. Record site behaviour, selectors, HTTP status and limits. This is external network access, so submit a scoped plan for approval before live-browser execution.

**D — Real Qwen evaluation (separate explicit approval):** Qwen3.5:4b pinned model/engine, exact HEAD and plan digest, fixed task, authorised browser-only tools, bounded run. Capture calls **generated at engine boundary**, visited URLs, search queries/inputs, navigation events, pages actually read, policy decisions, results, answer, source attribution and independent rubric. No inference from simply compiling code.

**Verdict:** PASS requires two **actually retrieved and opened** official documents plus correct comparison and correctly attributed sources; FAIL for model mis-navigation, incorrect answer or missing verified steps with functioning environment; INCOMPLETE for browser/website/GitHub/Ollama/environment failure. Do not score a single hardcoded `web_read` answer or scripted navigation as PASS.

## 5. Deliverables / governance

On `develop`: design + minimal product adapter (if feasible) + deterministic tests + CI + updated documentation + append-only `docs/HANDOFF.md` checkpoint **before each substantial output**; push and verify remote HEAD. Respect `main` release boundary and `demo/issa-20261111` isolation; no new branches, no merges, no real Qwen without explicit authorisation. Stop and report blockers rather than diluting network or action controls.

**Priority:** web multi-step research/task completion first. Voice/STT/TTS integration is intentionally postponed, not discarded.

## 6. Implementation status (2026-11-12, Claude Code)

| Ladder step | Status |
|---|---|
| **A** | Done (`WORK07_BROWSER_ADAPTER_DESIGN.md`). |
| **B** | Done: `rightware/agent/browser.py`, fixture tests `tests/test_work07_browser.py`, and evaluator/runner/workflow tests `tests/test_work07_gate.py`. |
| **C** | Prepared, **not run**: `labs/work07_rfc_gate/gate.py --run site-preflight` and `.github/workflows/work07-site-preflight.yml`. |
| **D** | Prepared, **not run**: `--run qwen` and `.github/workflows/work07-qwen-rfc.yml`. |

Exact authorisation requirements and plan digests: `WORK07_REAL_GATES.md`.
