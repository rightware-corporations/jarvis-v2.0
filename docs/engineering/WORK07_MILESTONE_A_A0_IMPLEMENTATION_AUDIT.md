# WORK-07 Milestone A — A0 implementation audit and exact change plan

**Date:** 2026-11-13 (Africa/Maputo)  
**Classification:** A0 AUDIT / READ-ONLY ENGINEERING PLAN. **Not** a production change, implementation authorization, or test execution.  
**Repository:** `rightware-corporations/jarvis-v2.0`; observed baseline `develop` `e71dba3155eadc99c9bdba1a875a1c35bcc323b2`.  
**Baseline CI:** 3/3 SUCCESS: runs `43469800180`, `43469788657`, `43469788763`.  
**Inputs:** Milestone A contract, HANDOFF through R3-C2-020, R3-C2-012 E1/E4, R3-C2-014–019 and tested labs. Sources read directly from HEAD; assertions below are grounded in existing code unless flagged as proposals.

## 1. Engineering decision at A0: constrained first milestone

**Recommendation (not an approved production release):** introduce an *opt-in* completion gate only for **trusted approved preset(s)** with positive, explicit browser objectives. A user-facing `operator_confirmed` free-form contract needs separate authentication/confirmation integration and should not be shipped before such authority exists. Avoid treating natural-language extraction or a model-generated checklist as trusted truth.

Supported A1 contract draft:
- version `A1`, unique ID and 1–N mandatory objectives, explicit authorized HTTPS targets, approved hosts, positive `read_page` or `open_original` types;
- optional expected original identity proof from a **trusted preset**, such as preapproved full SHA-256 digest or verifier validated independently of page claims;
- no conditional, ordered, forbidden, repeated side-effect, Windows action or arbitrary web search requirements until their enforcement is implemented;
- default OFF for ordinary `AgentSession` sessions, preserving current API and behavior.

**Important design gap:** with a generic, unknown document, URL/title/HTTP 200 do NOT prove the original publisher document. A successful GET without a credible trusted predicate yields `PAGE_OBSERVED`, not `ORIGINAL_VERIFIED`. Use `UNKNOWN` when original authenticity is unprovable. A published digest may become stale; explain version/representation explicitly.

## 2. Actual integration map

| Observed code | Relevant lines | Existing behavior | Proposed minimal increment |
|---|---|---|---|
| `rightware/agent/session.py` | 90–107 | `ToolOutcome` and `AgentReply` data records lack scoped task contract / receipt chain | Add default-compatible optional completion metadata, do NOT mutate historical fields for no-contract |
| `rightware/agent/session.py` | 109–131 | `_GuardedEngine.generate()` checks policy halt and batch guard | Contracted, bounded pre-final evaluation/feedback; account for `max_turns` and continuation budget; leave uncontracted path identical |
| `rightware/agent/session.py` | 163–198 | `_PolicyTool.execute()` checks `authorize_execution`, records outcome, adds to list and trace | Trusted **execution-boundary** receipt emission tied to exact approved call; never infer from post-hoc hash alone |
| `rightware/agent/session.py` | 202–228 | `AgentSession.__init__` takes capabilities/sites but no contract | Optional preset contract reference with strict provenance validation; default `None` |
| `rightware/agent/session.py` | 288–336 | `run()` initializes policy/browser/trace and orchestrator; returns `_compose` | Initialize per-run receipt ledger and opt-in verifier; preserve no-contract result and cleanup |
| `rightware/agent/session.py` | 338–345 | `_close_pending` reconciles approved calls not executed | Preserve `NOT_EXECUTED` and audit; no fabricated successful receipt |
| `rightware/agent/session.py` | 347–409 | `_compose` marks any successful source `ANSWERED_WITH_SOURCES`; factual flag always False | For contracted runs only, issue truthful operational `INCOMPLETE/UNKNOWN/COMPLETE_VERIFIED`, preserve factual accuracy False, refusal/budget flags |
| `rightware/agent/session.py` | 412–417 | `reply_json` serializes current result | Add opt-in, backward-compatible objective results, never leak page text |
| `rightware/agent/policy.py` | 180–255 | `before_tool_call` persists approval then tracks canonical args; `authorize_execution` consumes canonical args; `note_outcome` logs status | **Risk:** approvals keyed by canonical tool+args, not a stable individual call_id; decide whether to add internal call correlation or instrument at orchestrator boundary without weakening audit/lock |
| `rightware/agent/trace.py` | 37–105 | `call_id` from proposal, approval, result; in-memory, opt-in; `_current` used for result; short 16-hex result hash | Informational observer only; no G3 by trace hash; avoid assuming it is always enabled |
| `rightware/agent/browser.py` | 242–280 | Events include operation, final URL, HTTP status, raw body digest, content type, truncated and title | Define typed page-vs-view digest scope; do not infer original authenticity from final_url |
| `rightware/agent/web.py` | 291–340 | Redirect hops each receive host/SSRF checks; `Page(requested,current,status,...,sha256(raw),truncated)` | Keep SSRF/allowlist; trace of redirect path/publisher authenticity is not currently captured; never silently claim chain |
| `labs/work07_r3c2/interception.py` | 27–125 | FAKE-test _GuardedEngine interception and bounded continuation; objectives are fixture-provided and URL-based | Use as experimental design reference, not production module |
| `labs/work07_r3c2/live_receipt_adapter.py` | entire file | Post-run correlation by tool/status/truncated digest; grades G1/G2_OBSERVATIONAL | Never use as trusted production receipt factory; fail closed on collisions |
| `tests/test_work07_r3c2_e3_l1l4.py` | entire file | 27 synthetic contract tests; no NLP extraction | Regression only, not end-to-end product acceptance |
| `tests/test_work07_r3c2_live_adapter.py` | entire file | 9 FAKE/real AgentSession observational tests | Regression only; not authenticated receipts |

## 3. Critical mechanics and design constraints

### 3.1 Approval identity and exact outcome

`AgentPolicy.before_tool_call` records approval and adds `canonical(name,args)` to `_approved` and `_pending`; `authorize_execution` consumes one matching key. This is strong argument-bound enforcement but **does not assign a unique authorization id** to each approval. A duplicate call with identical canonical args can be ambiguous if naive order matching is used. A1/A2 must not claim G2 transactional provenance until unique ids are produced at the trusted boundary.

A proposed minimal receipt identity is `(run_id, sequence)` generated by runtime in strict execution order, with `tool_call_id` linked only when reliably provided. Importing a call id from a model JSON is **not equivalent to authentication**: bind it to the approval/execution lifecycle in code. Don't mutate policy authorization semantics without tests and review.

### 3.2 Trace is insufficient as authority

The optional `TaskTrace` uses `_current`, 16-character hashes and proposal ids. It can support investigations, but a `trace=False` session still needs valid receipts in opt-in mode. Distinguish model-visible result digest, raw page SHA-256, and text/content digest. All IDs should be scoped to one run and checked for uniqueness.

### 3.3 Source proof and truncation

`Page.sha256` hashes the downloaded **raw** bytes, whereas `TaskTrace.result_sha256` hashes the framed **tool content** and `last_view.view_sha256` the model-visible view. They are different representations. `Page.truncated=True` when response read limits are hit; hashing truncated raw bytes proves only the downloaded prefix, not the complete document. A negative case must reject truncated content as proof of a known full-document digest.

For source authenticity, a trusted preset must specify what document is expected and an independent verifying rule. Exact URL match is a necessary locator constraint for some presets, not a semantic proof. Redirects may be allowed only if final URL and accepted issuer/identity can be verified under the existing security restrictions. If that cannot be verified, verdict UNKNOWN.

### 3.4 Response status and terminal semantics

`_compose` currently returns `ANSWERED_WITH_SOURCES` whenever any READ tool has OK status, even when all requested documents were not opened. Do not globally replace this meaning for noncontracted runs. In contracted mode, false COMPLETE must be impossible and `reply_json` must reflect identical verdict and missing objective IDs. Audit failures take priority over declared completion.

### 3.5 Budget and loop invariants

E1/E4 interception in the lab can generate an extra response beyond upstream `max_turns`; last-turn continuation can be wasted. A3 must know effective remaining orchestration turns and avoid requesting an impossible tool step, while preserving `Budgets.max_calls`, clock deadline, cancellation, per-tool quotas, no regrant, anti-loop and batch fail-closed semantics. The E4 mutant without budget caused OOM: mutations must be isolated with hard timeout/memory cap.

## 4. Exact proposed diff plan — only after separate authorization

| Sequence | Proposed additions/edits | Contract and regression |
|---|---|---|
| A1 | **NEW** `rightware/agent/task_contract.py` with immutable trusted preset data/validator; **EDIT** `rightware/agent/session.py` optional `task_contract` input | No-contract output byte-compatible; reject untrusted/empty/conditional/unsupported contracts; no grants expanded |
| A2 | **NEW** `rightware/agent/receipts.py` scoped in-memory receipt data + unique sequence; **EDIT** `rightware/agent/session.py` execution boundary/cleanup; touch `policy.py` **only if proven necessary**, with separately audited approval semantics | Approved/executed/status ties; foreign or duplicate IDs rejected; NOT_EXECUTED never accepted; trace OFF still safe |
| A3 | **NEW** `rightware/agent/completion.py` deterministic evaluator; **EDIT** `rightware/agent/session.py` opt-in result/status, final interception, bounded recovery, `reply_json` | Correct `COMPLETE_VERIFIED/INCOMPLETE/UNKNOWN/HALTED/ERROR`; no global status semantic change; no model authority |
| A4 | **NEW** `tests/test_work07_milestone_a_contract.py`, `tests/test_work07_milestone_a_receipts.py`, `tests/test_work07_milestone_a_completion.py` plus synthetic browser fixture reuse | A-01–A-18, existing E1/E4/R3-C1 regressions and pinned CI; 0 false COMPLETE |
| NOT A | `vendor/openjarvis/**`, `rightware/agent/web.py`, `rightware/agent/browser.py`, `main`, Shared service/DB, Qwen inference | Out of scope unless a later, explicit constraint forces a separate decision |

**Warning:** names are proposed, not present files. Avoid creating a competing completion controller framework or altering the pinned orchestrator. Start A1 with one small preset, not a generic requirements language.

## 5. Engineering acceptance and go/no-go

**A0 audit status: COMPLETE as a read-only code review**. No code or tests were executed by this audit; prior baseline CI was observed green.

To proceed with **A1 production implementation**, require an explicit bounded authorization specifying:
- only opt-in trusted preset and strict validator;
- no Qwen, no real network, no vendor/policy/quotas/pin change;
- no A2–A4 automatically unless separately authorized;
- a demo that old no-contract flows remain unchanged;
- HANDOFF checkpoint per commit and CI proof.

**Open product questions to decide before A1 or A3:** which preset is approved, which issuer/content proof is acceptable, whether contracted `AgentReply.completion` can add new status values without breaking callers, how to derive turn availability without bypassing the orchestrator. For first acceptance, the fixture archive originals (AX-101/AX-202) can be a **test preset only**, not a real website publisher proof.

## 6. Provenance and status

This document is a technical *plan and code audit*, not an A1 implementation or measured A1–A4 success. The previously verified 320/0-skip suite belongs to R3-C2-019; it is not an assertion that the proposed production tests exist.

**Next action:** review and confirm A0's limited A1 scope, then hand the exact mission to Claude Code. Keep HANDOFF-FIRST, preserve historical Qwen FAIL/BLOCKED and avoid concurrent overwrites.
