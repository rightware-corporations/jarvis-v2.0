# WORK-07 R3-C2-012 — E1 + E4 results (FAKE model, test-only)

**What ran:**
- the real `AgentSession`, pinned `OrchestratorAgent`, `AgentPolicy` and `PublicBrowser`, over the R3-C1 local synthetic archive;
- a deterministic FAKE model;
- `InterceptingEngine` (`interception.py`), a subclass of the real `_GuardedEngine`, installed only during the experiment.

Production `AgentSession.run()` and `_compose()` are **unchanged**; this is asserted in the tests. Nothing here is evidence about Qwen.

Tests: `tests/test_work07_r3c2_e1e4.py`, 15 tests, all PASS.

## Results (actual)

`model_calls` comes from `CountingEngine` and matches the model's own count.

| Scenario | Experiment verdict | Continuations | Orchestrator generations | Model calls | Product `completion` (unchanged) |
|---|---|---|---|---|---|
| E1: info pages → premature answer → feedback → follows both originals (AX-202 via `web_find`) | `COMPLETE_VERIFIED` | 1 | 11 | 12 | `ANSWERED_WITH_SOURCES` |
| E1: continuation tries the off-site mirror (REFUSED) | `INCOMPLETE_BUDGET_EXHAUSTED` (O1, O2) | 1 | 9 | 10 | `ANSWERED_WITH_SOURCES` |
| E1: required URL loads with HTTP 404 | `INCOMPLETE_BUDGET_EXHAUSTED` (O9) | 1 | — | — | — |
| E4: budget 0 | `INCOMPLETE_BUDGET_EXHAUSTED` | 0 | — | — | — |
| E4: budget 2, repeated premature answers | `INCOMPLETE_BUDGET_EXHAUSTED` | 2 | 8 | 10 | `ANSWERED_WITH_SOURCES` |
| E4: deadline reached at the premature answer | `HALTED` (no re-prompt) | 0 | — | 8 | `HALTED` |
| E4: cancellation at the premature answer | `HALTED` (no re-prompt) | 0 | — | — | `HALTED` |
| E4: `web_open` quota exhausted during continuation | `INCOMPLETE_BUDGET_EXHAUSTED`; denial explicit, quota not reset (3/3) | 1 | — | — | — |
| E4: anti-loop denial during continuation | `INCOMPLETE_BUDGET_EXHAUSTED`; «acção idêntica» | 1 | — | — | — |
| E4: approved but not executed (upstream guard reinjected) | `INCOMPLETE_BUDGET_EXHAUSTED`; flag `APPROVED_NOT_EXECUTED` | 1 | 11 | 12 | `ANSWERED_WITH_SOURCES` |
| E4: global proposal budget reached | `HALTED`, model never called again | 0 | 8 | 7 | `HALTED` |
| E4: `max_turns` = 8 (premature answer on the last turn) | `IN_PROGRESS`: continuation tools ran, then the orchestrator stopped | 1 | 8 | **9** (> `max_turns`) | `HALTED` (turn limit) |

**Invariants checked in every scenario:**
- every model call is counted: `model_calls = orchestrator_generations + continuations − halt short-circuits`;
- `continuations ≤ budget`;
- `model_calls ≤ max_turns + budget`;
- audit approvals = audit outcomes;
- `policy.pending() == []`;
- policy budgets are never reset (one `per_tool` across the whole run).

## Mutation (all detected)

| Mutant | Result |
|---|---|
| No halt check before continuation | 2 failures |
| Evidence ignores the outcome | 1 failure, after adding the 404 test |
| Feedback leaks the URL | 1 failure |
| Budget off by one | 7 failures |
| **No budget** | the run looped on generations until the kernel killed it for lack of memory |

The last mutant confirms that interception **creates an unbounded generation path unless it has its own budget**.

## Findings for the next decisions

1. **Feasible (FACTO, FAKE model):** the existing `_GuardedEngine` boundary can hold back a premature final answer, append code-generated feedback and resume tool use through the unchanged hook → `AgentPolicy` → tool → audit path, without touching the pinned OpenJarvis.
2. **The budget is load-bearing.** Continuations are outside `max_turns` (9 model calls with `max_turns`=8). A production version needs:
   - its own counter;
   - a `halt_reason` check before every re-prompt;
   - **a check of the remaining orchestrator turns**, otherwise a continuation on the last turn is wasted (the `IN_PROGRESS` row).
3. **Mapping the verdict is a separate step.** The product still reports `ANSWERED_WITH_SOURCES` in all incomplete cases, because `_compose` is untouched. A production patch must map the verdict to a completion state; that is not done here.
4. **Browser refusals (REFUSED) do not raise `TOOL_REFUSALS`**, which only covers policy denials. Worth deciding in a production design.
5. **E3 dependency:** objectives were supplied by the experiment (exact required URLs). In production nobody supplies them. The open questions are:
   - how objectives are derived;
   - what counts as evidence when the URL is unknown in advance (L1–L4 are about source type and content signals, not URL equality).
6. **L1–L4 dependency:** the check here is URL equality on OK events. It is not robust to redirects to equivalent URLs, to mirrors on the allowed host, or to an «original» that is really a catalogue page.
7. The feedback and the candidate answer stay in the conversation context, so the context grows with each continuation. That matters on a 16 k context and CPU (Qwen3.5:4b, not measured).
