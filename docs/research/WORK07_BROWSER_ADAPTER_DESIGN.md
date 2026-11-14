# WORK-07 — Architectural decision: semantic public browser (Phase 1)

**Date:** 2026-11-12. **Status:** DECIDED and implemented on `develop` (see HANDOFF). This document does not authorise any external execution.

## 1. What exists today (inspected, not assumed)

| Component | Facts verified in the code | Usable for WORK-07? |
|---|---|---|
| `rightware/agent/web.py` `web_read` | Single HTTP GET. SSRF guard (upstream `check_ssrf` plus `is_global`). DNS-pinned httpcore backend and peer check. Every redirect re-checked. Limit of 1 MB / 12 000 characters. No cookies. HTML reduced to text. | It is **not** a browser: it cannot locate fields, type, submit or follow links. It remains a separate tool. |
| Upstream `openjarvis/tools/browser.py` (pin `f21d902`) | Playwright Chromium. `check_ssrf` only on the URL given to `browser_navigate`; nothing for subresources, redirects, form submissions or link clicks. Free CSS/text selectors. `page.evaluate` (JavaScript) used internally. Screenshots. A single process-wide session. **Playwright is not installed in the pinned venv** (optional extra `browser`). | **Rejected**: it would expose unrestricted browser controls and cannot prove the network boundary. |
| `OrchestratorAgent` (function calling) | `before_tool_call` hook and then `LoopGuard` (blocks the 4th identical call). Sequential execution. Tool results accumulate in the context. `num_ctx` defaults to 16 384. | Kept as the loop. Budgets account for the cumulative context. |

## 2. Decision

A new, small adapter, `rightware/agent/browser.py` (`PublicBrowser`): an **interactive semantic browser without JavaScript**, built on the same pinned transport as `web_read`.

- **Interactive state per task:**
  - current page and history;
  - registry of fields (`F1`, `F2`, …) and links (`L1`, `L2`, …) with stable identifiers for the **whole** task;
  - values typed into fields.
- **Semantic tools, not mouse or keyboard** (capability `browse`, a single grant per task):

| Tool | Effect |
|---|---|
| `web_open(url)` | opens a page on an authorised host |
| `web_find(text)` | finds links/text already loaded (no network) |
| `web_type(field, text)` | writes a short public query into a **search field** (state only, no network) |
| `web_submit(field)` | activates the search form for that field; **only GET forms** classified as search |
| `web_follow(link)` | follows an already-seen link to an authorised host |

- **Not implemented, and therefore fail-closed:**
  - POST, or any form that is not a search form;
  - password, e-mail, file or hidden-text fields typed by the model;
  - login and cookies;
  - downloads (only `text/html` and `text/plain`);
  - JavaScript and screenshots;
  - shell and filesystem;
  - new windows.
- **Network boundary (provable):**
  - every request (open, follow, submit **and every redirect**) goes through the `HttpxFetcher` with the pinned backend;
  - the task host allowlist applies at **each hop**;
  - plus SSRF, `is_global`, the peer check, ports 80/443 and no proxy.
  - There is no other process making connections (no Chromium), so no subresource can leave the boundary.
- **Prompt injection:**
  - page content and element labels are delivered in the untrusted frame with a random boundary;
  - page links only allow following within the allowlist and budget;
  - pages cannot add tools or capabilities.
- **Evidence:** `PublicBrowser.events` records each navigation (operation, final URL, HTTP status, SHA-256, characters, and the public query submitted). The audit keeps only hashes and lengths of typed text.

## 3. Why not Playwright/Chromium now

- Chromium resolves DNS and opens connections by itself. Proving the boundary would require an egress proxy with pinned DNS plus interception of every request; that is a new component with a large attack surface.
- Version-pinned dependencies outside the upstream lock add ~150–300 MB per runner or Windows PC.
- **INFERÊNCIA (to confirm in the Phase 4 preflight):** the RFC Editor search page is a classic HTML GET form and does not need JavaScript.
- If the preflight shows that JavaScript is required, the planned alternative is:
  - Playwright pinned in a separate venv;
  - `route('**')` with an allowlist;
  - a fresh context with `accept_downloads=False` and `java_script_enabled` controlled;
  - an egress proxy that reuses `validated_addresses`.

  That option needs a new design approval. Live browsing is not exposed without proven isolation.

## 4. Known limitations of the adapter

- Pages that only work with JavaScript give an empty page (`EMPTY_CONTENT`) or have no forms. The result is INCOMPLETE, never a cognitive FAIL.
- Text is cut at 1 MB / 12 000 characters (view of 3 500 characters). Long documents are read from the start: the title and abstract at the top are enough for the reference task, but not for questions about the middle of a long document.
- Link and field identifiers are only valid within the task. A new `run()` starts a new browser with no state (temporary profile).
