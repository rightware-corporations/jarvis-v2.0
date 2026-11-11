# RIGHTWARE JARVIS v2.0 — WORK-05: product agent foundation

**Date:** 2026-11-11. **Branch:** `feat/work05-product-agent`, created from `develop@de628df`. `main` and `develop` are unchanged; no merge.
**Status:** first vertical slice implemented and tested deterministically (FAKE engine, mock HTTP). **QWEN REAL: NOT RUN.** A real run needs explicit authorisation.
**Foundation kept:** OpenJarvis (pinned `f21d902`) + Ollama + Qwen. No framework rewrite and no new dependencies: `httpx` is already in the frozen lockfile.

Labels: **FACTO** = in code or test; **INFERÊNCIA** = judgement; **NOT VERIFIED**.

## 1. Phase 1 — what exists and what is reused (FACTO)

| Component (pinned) | Assessment | Decision |
|---|---|---|
| `OrchestratorAgent` (`function_calling`, `before_tool_call`, `parallel_tools=False`) | Proven in WORK-02/03/04 with fail-closed hooks | **Reused** as the agent loop |
| `OllamaEngine` | Local, already used by `voice.py` | **Reused** |
| `security/ssrf.check_ssrf` | Blocks private CIDRs, metadata hosts and disguised IPv4; fails closed on DNS errors. Misses 100.64/10 (CGNAT) | **Reused** + stricter local `is_global` check |
| `tools/http_request` | Expands `os.path.expandvars` on **model-controlled headers**, so a model could exfiltrate environment values. Also allows POST/PUT and arbitrary headers | **Not exposed** |
| `tools/browser*` (Playwright) | Navigation, clicks, typing; Playwright is not in the frozen core install | **Not exposed.** Public reading is implemented separately |
| `tools/shell_exec`, `file_write`, `code_interpreter` | Generic power | **Not exposed** |
| `rightware/windows_actions.py` | Allow-list, session authorisation, human confirmation, verified outcome, audit without text | **Reused unchanged** as the only effect path (C5) |
| `rightware/voice.py` | `SimpleAgent` chat + rule-based actions | Unchanged. Will call the same `AgentSession.run()` later (§4) |
| WORK-04 R2 lab (`labs/`, other branch) | Oracles, truth and the report contract are benchmark-only | **Not imported.** Only the principles move: contract C1–C11 (`docs/research/R2_RUNTIME_INTEGRATION_CONTRACT.md` on `feat/work04-r2-semantic-safety`) |

## 2. Phase 2 — the vertical slice (FACTO)

```
user instruction ─► AgentSession.run(text)                     rightware/agent/session.py
   ─► OrchestratorAgent + Qwen (OllamaEngine)                   (upstream, pinned)
   ─► tool proposal ─► AgentPolicy.before_tool_call             rightware/agent/policy.py
        closed registry · exact schema · session capability · per-tool + global budget
        · deadline · cancel · fail-closed batch · approval bound to exact args
   ─► _PolicyTool.execute ─► AgentPolicy.authorize_execution (single use)
   ─► web_read (read-only)                                      rightware/agent/web.py
      or windows_action ─► WindowsActions.run(confirm=HUMAN)    rightware/windows_actions.py
   ─► ToolOutcome {status, evidence} recorded by code
   ─► AgentReply: model text + facts from outcomes (sources, notes on unsupported claims),
      completion ∈ {ANSWERED, ANSWERED_WITH_SOURCES, TOOLS_FAILED, ACTION_VERIFIED,
                    ACTION_NOT_DONE, HALTED, ERROR}
```

**CLI:** `python jarvis.py agent "instrução" [--allow-web] [--allow-actions] [--json]`. Both capabilities are **off** by default. It runs in the upstream venv with the same local-only environment as voice (`OLLAMA_NO_CLOUD=1`, API keys and proxies stripped).

### `web_read`: public, read-only

- **Request:**
  - GET only, http/https, ports 80/443;
  - no credentials in the URL, fixed User-Agent;
  - **no model-controlled headers or body**;
  - no cookies (cleared before every request), `trust_env=False`.
- **SSRF:**
  - upstream `check_ssrf` (fails closed if unavailable);
  - every resolved address must be `is_global`, and `*.local`/`.internal`/`localhost` are refused;
  - **every redirect target is re-checked**;
  - after connecting, the **peer address of the actual socket** must be global before the body is read (DNS-rebinding defence). If the peer cannot be proven, the read is refused.
- **Limits:** 5 redirects, 15 s, 1 MB body, 12 000 characters of text, `text/html`/`text/plain` only.
- **Output:**
  - stdlib HTML → visible text (script, style, iframe and comments removed);
  - framed as **untrusted data** with a random per-call boundary; forged frame markers are neutralised (C7).
- **Separation:** authenticated or state-changing browser work (login, forms, clicks) is **not provided** and is a separate future capability (§4.3).

### Truthfulness (C6)

- Sources come only from successful `web_read` outcomes, with the final URL, HTTP status and SHA-256 of the body.
- A reply that claims an effect («abri…») without a `VERIFIED` action, or a reading («segundo a página…») without a successful read, gets an explicit note and a flag.
- Policy refusals are counted in the reply.

### Audit (C10)

`.runtime/logs/agent-YYYYMMDD.jsonl` records tool name, decision, reason and outcome. A URL is reduced to **host + SHA-256 prefix**: no query strings and no conversation text (tested).

## 3. Tests (FACTO, deterministic)

| File | Count | Covers |
|---|---|---|
| `tests/test_agent_policy_web.py` | 21 | Closed registry and schema (incl. `headers` injection attempt), session capabilities, single-use approval, budgets, deadline, cancel, fail-closed batch, audit redaction; URL checks (schemes, credentials, ports, control characters, localhost, `.local`, private, metadata, CGNAT, `::1`, IPv4-mapped, decimal IPv4, public name → private IP, mixed resolution, DNS failure, upstream verdict, upstream guard on literals, guard missing → fail closed); HTML extraction; frame forgery; httpx `MockTransport`: GET only, fixed headers, **no cookies after a `Set-Cookie` redirect**, redirect to metadata refused, redirect loop, content type, size limits, unprovable or private peer refused |
| `tests/test_agent_session.py` | 14 | Real `OrchestratorAgent` + scripted engine: sources from code; **page injection cannot trigger an action** when actions are off; confirmation by a human callback, verified outcome; declined → nothing launched and the false claim flagged; unauthorised session refused; refused URL reported honestly; unsupported read claim flagged; capability off → tool not offered; loops bounded (per tool and global, turn limit = HALTED); batch with an unknown tool executes nothing; engine down = ERROR; audit without conversation text or URL query; no lab imports; no unsafe upstream tools |
| `tests/test_agent_launcher.py` | 3 | `jarvis.py agent` uses the upstream venv and the local-only environment; capabilities are off unless flagged; other commands still reject unknown flags |

**Mutation checks:** 15 security rules were each removed in turn, and every removal made at least one test fail. Examples: the `is_global` check, the port check, the credential check, the SSRF verdict, the peer check, cookie clearing, the redirect re-check, frame neutralisation, the session capability check, single-use approval, the batch guard, audit host-only, human confirm, the claim note and the turn-limit halt.

**Local results:**

| Environment | Result |
|---|---|
| Upstream venv | **94 tests OK, 0 skipped** (56 existing + 38 new) |
| Plain Python | OK; tests that need OpenJarvis or httpx skip |

**CI:** `.github/workflows/work05-product.yml` runs both. In the venv run, any skip fails the job.

## 4. Phase 3 — future interfaces (documented, NOT implemented)

All of them plug into the same `AgentSession.run(text) -> AgentReply` and the same `AgentPolicy`. A new capability adds one `ToolDef`, one session flag, a runner that returns a code-checked `ToolOutcome`, and deterministic tests first.

1. **Portuguese speech input and dictation.**
   - `WhisperSTT` (exists) → text → `AgentSession.run`.
   - `AgentReply.text` → `speech_text` → TTS.
   - Confirmation questions are spoken, and the answer comes **from the microphone or keyboard, never from model text** (same `confirm` callback).
   - Dictation into an application is a consequential action: it needs explicit confirmation of the target window.
   - Transcripts are not stored (C10).
2. **Desktop application control.**
   - Extend `ACTIONS` (fixed executables, verification by new PID) before any generic UI automation.
   - UI automation (focus, typing) would be its own capability flag with a per-action preview and confirmation. No shell.
3. **Browser interaction and navigation.**
   - `web_read` (done) stays the public, read-only path.
   - A separate `browser_session` capability (Playwright from the `browser` extra) is needed for authenticated or stateful work:
     - isolated profile, no stored passwords;
     - per-domain allow-list chosen by the user;
     - every click, form submission or download previewed and confirmed;
     - screenshots kept as evidence.
   - Never mixed with `web_read`.
4. **Filesystem operations.**
   - Roots chosen by the user (folder picker), as in the WORK-02 sandbox (simple names, `O_NOFOLLOW`, inode check, atomic publish, no overwrite).
   - Read-only first; writes need confirmation; deletes are not offered.
   - Structured outputs follow the R2-D contract (typed tool arguments, Markdown rendered by code).
5. **Persistent task state and recovery.**
   - A per-task JSON journal under `.runtime/tasks/` with the plan, approved calls, outcomes and hashes.
   - Resume only with the user's confirmation and the **same** policy budgets.
   - At most one bounded continuation (the R2 lesson); no conversation text stored by default.
6. **RIGHTWARE Shared Intelligence** (independent project, **not connected**).
   - A future read-only REST/MCP client capability (`shared_context_query`): OAuth-scoped, per-request user consent, responses framed as untrusted data, no personal data sent without consent, full audit.
   - Its code is not merged here and no personal data is connected at this stage.

## 5. Risks and limits

- **Real-model behaviour is NOT VERIFIED.** All results come from the FAKE engine. Qwen may not call `web_read` correctly, may over-call it, or may not cite sources. One authorised CPU smoke on a public, stable page is the next gate.
- **The peer check depends on the httpx/httpcore `network_stream` extra.** If it is absent the read fails closed: safe, but it could block legitimate reads on another httpx version (pinned now).
- **Public content can still mislead the model.** The frame prevents instructions from acting, and actions need a human. Declarative misinformation on a page is not filtered; answers show their sources so the user can judge.
- **Outbound requests.** `--allow-web` makes outbound requests from the user's PC to sites the model chooses. The user enables it per session and the audit shows the hosts. A domain allow-list is a possible next step.
- **HTML extraction is simple** (stdlib). JavaScript-rendered pages return little text; this is reported honestly, without browser execution.
