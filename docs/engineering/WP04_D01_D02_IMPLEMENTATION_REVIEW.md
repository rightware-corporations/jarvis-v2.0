# WP-04/D01–D02 — Opt-in text facade review notes

**Scope:** candidate implementation for Issue #10 only. No acceptance of E0/E1, D03–D08, A4, real Qwen or Windows behaviour.

## In-process use (host-owned)

~~~python
from rightware.text_facade import TextFacade

facade = TextFacade(owner_id="local")  # local placeholder, NOT multi-user authentication
session_id = facade.open_session()       # opaque random token, minted by host
try:
    result = facade.submit(session_id, "Explica o que é RAM.")
    print(result.status.value, result.text, result.limitations)
finally:
    facade.close()
~~~

The first informational model request lazily initializes the pinned OpenJarvis `OllamaEngine(host="http://127.0.0.1:11434")` and `SimpleAgent` inside the already-installed, locked vendor environment. It does **not** download a model, configure Ollama, launch a process, initialize voice or open the agent CLI. Tests pass injected fakes; real model inference was not authorized in this mission.

**Host trust boundary:** the caller can provide plain text, an already-minted session ID and `channel="text"`. It cannot pass principal, capabilities, receipt or verified result fields. The facade issues random request IDs, binds sessions to its fixed local owner, and emits `effective_capabilities=()` in its internal request contract. JSON/user instructions are raw model data, never grants.

**Routing:** best-effort conservative classification into `ANSWER`, `PLAN`, `CLARIFY`, `TASK`, `CONTROL`, `MEMORY_INTENT`. Unmistakable commands and memory writes receive a static `UNAVAILABLE` response before the model is called. This is *not* a Portuguese intent quality claim. `ANSWER_ONLY` and `PLAN_ONLY` mean **text only**. No semantic or factual verification is performed; no effects/receipts or persistent memory can be created or claimed.

**Context:** in-RAM histories, isolated by opaque session token, bounded by turn count and character cap. Old complete pairs are discarded. Closing a session removes history. No restart recovery and no memory persistence. Real model capacity/Portuguese anaphora quality remain unmeasured.

**Timeout/cancellation:** a daemon inference worker permits the host to return a bounded timeout/cancel result and discard late output. Since pinned synchronous `SimpleAgent.run` has no documented cooperative cancellation, the worker itself may continue until its engine timeout; a still-running worker blocks a new request for that same session. This never implies remote side effects or rollback. A future D03 worker lifecycle requires separate design/review.

**Adversarial limits:** the facade rejects overt model claims of execution and all structured upstream tool results. A prompt-injected model may still generate inaccurate *text*, including nuanced implied claims; model-language assurance is NOT established by fake tests. All results expose `factual_verified=False` and fixed limitations. No external browsing, mail, calendar, file, shell, MemoryService, WindowsActions, receipts or A1–A3 gates are present in this path.

## Testing/acceptance boundary

New deterministic suite: `python -m unittest -v tests.test_wp04_d01_d02`; project suite: `python -m unittest discover -s tests -v`; pinned upstream environment uses `vendor/openjarvis/.venv/bin/python` and existing frozen lock. CI checks are associated with exact commit SHAs, not inferred from a historical green baseline.

Corpus `WP03_PT_CONTEXT_CORPUS_v1.csv` is used for representative **route/safety fake** cases only. Tests cannot validate the 36-case Portuguese context rubric without separately approved real-model evaluation. Reviewers must verify the branch diff, pin/gitlink untouched, legacy command parity, fake PASS/FAIL/SKIP counts, final CI and no-effect semantics prior to any D03 authorization.
