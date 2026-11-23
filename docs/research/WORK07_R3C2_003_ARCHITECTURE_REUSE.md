# WORK-07 R3-C2-003 — Existing architecture research and reuse investigation

**Date:** 2026-11-12. **Mode:** read-only research. No product code was changed, nothing external was installed or executed, and no Qwen/Ollama was run.

**Base:** `develop` `38cad88f` (decision checkpoint `462d6946`). OpenJarvis pin `f21d902f4d3bd7f0f3f138f1a4613019a394b549`.

**Labels used:**
- **FACTO (código)** means read in source at the cited path and line.
- **DOCUMENTADO** means taken only from docstrings or comments.
- **HIPÓTESE** means not verified.

## 0. Question

R3-C1 showed (FAKE model, real agent) that `ANSWERED_WITH_SOURCES` is produced whenever any page was read, even when required objectives (opening the original documents) were never met. Before designing our own completion controller, we asked:
1. Does the pinned runtime already provide the mechanism?
2. Which proven external patterns solve this, and at what cost on a CPU-only Qwen3.5:4b?

## 1. Internal audit (pinned OpenJarvis + RIGHTWARE)

### 1.1 How `OrchestratorAgent` decides to finish — FACTO (código)

- `vendor/openjarvis/src/openjarvis/agents/orchestrator.py:368-394` (`_run_function_calling`): the loop runs up to `max_turns`. **The only finishing rule is that the model response has no tool calls** (`if not raw_tool_calls:` at line 390). It then returns `AgentResult(content=...)`. If the turns run out, `max_turns_exceeded=True` (lines 530-536).
- `agents/_stubs.py:333-366` (`_check_continuation`): it re-prompts **only** when `finish_reason == "length"` (truncation), at most 2 times, with «Continue from where you left off.». It does no task or objective check.
- There is no ledger, verifier, critic or replanning in `agents/`. A search for `ledger|replan` finds nothing, and `def (after_|on_final|verify|validate_output)` has no match in `agents/` or `core/`.
- `agents/monitor_operative.py:42,123,171,208`: `task_decomposition` («phased» / «monolithic» / «hierarchical») is **only a prompt-template parameter**. There is no decomposition mechanism.
- `workflow/graph.py:50-72` rejects cycles (it is a DAG). `workflow/engine.py:315-343` (`_run_loop_node`) repeats an agent until `condition_expr` **appears as a substring of the model output**. That is model self-assessment, and it needs `system.ask`. Not suitable.
- `agents/research_loop.py:307-369` (`renumber_citations`): citations `[N]` are mapped **only** to retrieved hits, and unknown refs are not turned into sources. This is a reusable *provenance* pattern (citation ⇒ retrieved item), but it does not check completeness.

### 1.2 Can the final output be intercepted before termination? — FACTO (código), yes, in two places

1. **Engine boundary.** `agents/_stubs.py:265-295` (`_generate`) passes the orchestrator's **same `messages` list object** to `engine.generate`. RIGHTWARE already wraps the engine (`rightware/agent/session.py:109-131`, `_GuardedEngine.generate`) and sees every response, including the final one, **before** the orchestrator decides to stop.

   A wrapper could:
   - append feedback to `messages`;
   - ask the model again;
   - return a response that contains tool calls.

   The orchestrator would then execute those calls through the normal hook → policy → tool path (lines 476-520) and continue. This is the same mechanism upstream already uses in `_check_continuation` (append messages and regenerate).
2. **Outer loop.** `AgentSession.run` (`session.py:288`) runs `agent.run` once. A bounded second pass could reuse the conversation (`AgentContext.conversation`, `_stubs.py:25-31`, consumed by `_build_messages`, `_stubs.py:198-230`) and the **same** `AgentPolicy`, so quotas are shared. This is costlier: the context is rebuilt and each pass starts a new orchestrator.

Overriding `_check_continuation` in `_RightwareOrchestrator` was rejected: it can only return **text**, so it cannot resume tool use.

### 1.3 Existing task-state or verification hooks — FACTO

- Upstream has no task-state or completion hook, only events (`core/events.py`: `AGENT_TURN_END`, `LOOP_GUARD_TRIGGERED`, `AGENT_STALL_DETECTED`, …).
- RIGHTWARE already has:
  - `AgentPolicy` (authorisation, budgets, deadline, cancel, argument-aware anti-loop before approval, `close_pending`; `policy.py:105,180,217,243,257`);
  - `_RightwareOrchestrator` (single enforcement path, explicit refusals; `session.py:133-160`);
  - `ToolOutcome` and `_compose` (`session.py:347`; post-hoc classification);
  - `TaskTrace` (opt-in, hash-only; `trace.py:37`, `link_visibility` :109);
  - browser evidence (final URL, status, title, sha256).

### 1.4 What must stay independent of model self-assessment — decision derived from the evidence

- Whether a page was **actually retrieved**, and its URL, status, title and hash: tool outcomes recorded by code.
- Whether a call was **executed, refused or not executed**: policy and audit (R3-B).
- Final completion classification and budgets.

The model may *propose* objectives or say «done». **It must never be the source of truth for «done»**, and it must not remove objectives that are explicit in the instruction.

### 1.5 Duplication risks in the R3-C2-001/002 proposal

| Proposed component | Already exists | Gap |
|---|---|---|
| Evidence Registry | largely yes: `ToolOutcome.evidence` and browser `events` (url, status, title, sha256, op), `TaskTrace` (proposal → decision → result, presented/used links), audit | **linking evidence to objectives** and **source-type** labelling |
| Completion Controller «recovery» | a bounded re-prompt mechanism exists upstream (`_check_continuation`, length only) and an interception point exists in `_GuardedEngine` | a **completion check** feeding that point |
| Loop or retry protection | `AgentPolicy` anti-loop, quotas, global budget, deadline | a separate small **completion-retry budget**, since `max_turns` does not count engine-level retries |
| Task Contract | does not exist | it is genuinely new: **where objectives come from** is the open problem (see §3) |

### 1.6 Interaction with R3-B policy, loop protection, audit and budgets — FACTO and analysis

- Tools proposed after a completion feedback go through the **same** `before_tool_call` → `authorize_execution` → `note_outcome` path. Quotas, the anti-loop rule, the audit and `close_pending` apply unchanged.
- **Gap (FACTO):** an engine-level re-prompt is **not** counted by the orchestrator's `max_turns` (that loop counts its own iterations) nor by `AgentPolicy.calls` (which counts tool proposals). Any recovery therefore needs its **own** explicit budget (for example 1) and must honour `policy.halt_reason` (cancel and deadline) before re-prompting.
- `TaskTrace.on_generate` already records each engine response, so retries would be visible. `RecordingEngine` in `labs/work07_rfc_gate/gate.py` sits **inside** `_GuardedEngine`, so real-run evidence would also capture retries.

## 2. External code comparison (read-only shallow clones, nothing executed or installed)

| Project @ commit (date) | Licence | Mechanism, read in code |
|---|---|---|
| microsoft/autogen @ `8390985` (2026-11-12) | code: MIT (`LICENSE-CODE`); docs: CC-BY-4.0 | Magentic-One `.../teams/_group_chat/_magentic_one/_magentic_one_orchestrator.py:300-405`, `_prompts.py:59-99` |
| pydantic/pydantic-ai @ `c28aafa` (2026-11-12) | MIT | `pydantic_ai_slim/pydantic_ai/exceptions.py:80` `ModelRetry`; `_output.py:518-548` `OutputValidator.validate`; `_agent_graph.py:846-870` `consume_output_retry` |
| crewAIInc/crewAI @ `ea57411` (2026-11-12) | MIT | `lib/crewai/src/crewai/task.py:289-291` `guardrail_max_retries=3`, ~1455-1510 retry loop; `utilities/guardrail.py:60` `GuardrailResult`; `tasks/llm_guardrail.py` |
| langchain-ai/langgraph @ `b4cb0f1` (2026-11-11) | MIT | `libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py:74,297,627-631,831-841,919-949`; `libs/langgraph/langgraph/errors.py:69` |
| openai/openai-agents-python @ `64fbde5` (2026-11-11) | MIT | `src/agents/guardrail.py:20,134`; `src/agents/run_internal/guardrails.py:238`; `src/agents/exceptions.py:354,442` |
| OpenHands/software-agent-sdk @ `fb75ae9` (2026) | MIT | `openhands-sdk/openhands/sdk/agent/critic_mixin.py:76-138`; `critic/impl/agent_finished.py`; `critic/base.py:20-40`; `conversation/stuck_detector.py:181-201` |

`All-Hands-AI/OpenHands` @ `d58ca3d` (MIT) now contains only the frontend. The agent and controller live in `OpenHands/software-agent-sdk`.

### 2.1 Mechanisms (FACTO, código) and fit for RIGHTWARE

**Magentic-One.** Each round, an extra LLM call fills a JSON *progress ledger*: `is_request_satisfied`, `is_in_loop`, `is_progress_being_made`, `next_speaker`, `instruction_or_question` (`_prompts.py:59-99`). The orchestrator retries JSON parsing up to `max_json_retries` and raises if it still fails (`:316-379`). Completion is `if progress_ledger["is_request_satisfied"]["answer"]` (`:388`). Stalls are counted (`:394-399`), and `n_stalls >= max_stalls` triggers `_update_task_ledger` and replanning (`:402-405`). `max_turns` bounds the rounds (`:303`).
- *Fit:* the stall and replan counters are a good pattern. But **completion is LLM self-assessment**, which our principles forbid as the sole basis. It also costs one extra structured-JSON LLM call per round (HIPÓTESE: unreliable and slow on a CPU 4B model; not measured).

**PydanticAI.** A developer-written `OutputValidator` (often deterministic code) raises `ModelRetry` with feedback, which becomes a retry prompt. `consume_output_retry` counts `output_retries_used`, and above `max_output_retries` raises `UnexpectedModelBehavior` (`_agent_graph.py:846-870`): a hard stop with an explicit error.
- *Fit:* **closest to what we need**: a deterministic check at the final answer, structured feedback, a small explicit budget and a terminal failure state.

**CrewAI.** Each task has a developer-written `expected_output` and `guardrail`(s): a callable or `LLMGuardrail`, returning `GuardrailResult(success, result, error)`. On failure the **task is re-executed** with the error as context, up to `guardrail_max_retries` (default 3). After that it raises «Task failed … validation after N retries».
- *Fit:* same pattern at task granularity. Re-executing the whole task is too costly for us.

**LangGraph prebuilt agent.** It uses the **same** finish rule as OpenJarvis («no tool_calls → END», `should_continue` :831-841). There is an optional `post_model_hook` node after the model (:297, :804-806) and a router (:919-949) that decides tools, structured response or END. `remaining_steps` (default 25) is a managed budget: with fewer than 2 steps and tool calls pending, it answers «Sorry, need more steps…» (:627-631, :689). `GraphRecursionError` is the hard cap (`errors.py:69`).
- *Fit:* confirms the architecture point that a **post-model hook between the model response and termination** is the standard place for this check. We already have that point (`_GuardedEngine`). Migrating to LangGraph would add a framework dependency for something we can do in about 1 class.

**OpenAI Agents SDK.** An output guardrail returns `GuardrailFunctionOutput(tripwire_triggered=…)`. If triggered, it raises `OutputGuardrailTripwireTriggered` (`run_internal/guardrails.py:238`) and **ends the run**, with no retry. `MaxTurnsExceeded` is the turn cap.
- *Fit:* the «block, don't recover» pattern, useful for the terminal state when the budget is exhausted.

**OpenHands SDK.** A `Critic` scores the run, and `AgentFinishedCritic` uses **objective artefacts**: the last action is `FinishAction` and the git patch is non-empty. With `IterativeRefinementConfig(success_threshold, max_iterations)` the conversation **continues** with a follow-up prompt while the score is below threshold and iterations remain (`critic_mixin.py:76-138`). The stuck detector compares **action and observation content**, not only names (`stuck_detector.py:181-201`).
- *Fit:* «critic on objective evidence, plus bounded continuation». This **matches our need** and confirms R3-B's argument-aware loop design.

## 3. What to reuse vs implement

| Need | Reuse (pattern or code) | Implement (RIGHTWARE) |
|---|---|---|
| Interception before termination | **existing** `_GuardedEngine` (`session.py:109`); pattern = LangGraph `post_model_hook`, upstream `_check_continuation` | small check at «final response without tool calls» |
| Bounded recovery and terminal failure | pattern = PydanticAI `ModelRetry` + `max_output_retries`; OpenHands `max_iterations`; OpenAI tripwire for the terminal state | a `completion_retries` budget (1–2), honouring `halt_reason` |
| Deterministic verification | pattern = OpenHands critic on artefacts; research_loop citation ⇒ retrieved item | verifier over **existing** evidence (`ToolOutcome`, browser events, `TaskTrace`) |
| Evidence registry | **existing** outcomes, events, trace and audit | only objective ↔ evidence links and a source-type label |
| Stall or loop | **existing** R3-B `AgentPolicy` anti-loop (content-aware, like the OpenHands stuck detector) | nothing new |
| Objectives (Task Contract) | none of the projects derives objectives reliably: CrewAI and PydanticAI have the **developer** write them; Magentic-One has the LLM write facts and plan and self-assess | **open problem** (§6) |

### 3.1 Options

1. **Minimal patch (recommended to evaluate first):**
   - a `CompletionCheck` invoked by `_GuardedEngine` on a final response;
   - deterministic objectives only (see §6), a verifier over existing evidence and 1 bounded feedback re-prompt;
   - `_compose` then reports `ANSWERED_WITH_SOURCES` only if the check passes, else a new explicit «incomplete» state.

   Estimate: about 1 module plus edits to `_GuardedEngine` and `_compose`. No new dependency; pin unchanged.
2. **Modular integration:** an outer loop in `AgentSession.run` (OpenHands/CrewAI style) with shared policy and conversation. Cleaner separation, but more context and CPU per retry.
3. **Runtime migration** (LangGraph, PydanticAI, Agents SDK, Magentic-One): **not justified by the evidence**.
   - The needed mechanism is about 1 hook plus a counter, which we already have.
   - Migration would replace the audited `OrchestratorAgent` + `AgentPolicy` path (R3-B lessons: hook ordering matters) and add dependencies outside the frozen lock.
   - It is not proven better with Ollama and Qwen3.5:4b (HIPÓTESE).

## 4. Security and compatibility risks

- **Engine-level retries bypass `max_turns`.** A separate budget is mandatory and must check `halt_reason` (cancel and deadline) before each re-prompt.
- **Feedback text is a prompt-injection surface** if it echoes page content. Feedback must be generated from code and structured: objective ids, missing evidence types, presented link ids. No page text.
- The model must not be able to **remove objectives or self-certify**; any model-proposed objective can only *add* to the list.
- **Source-type labelling must not rely on URL patterns alone** (R3-C2-002 principle). Candidates: page title or headers, content signals, being reached from a page that links to it as «original». Each one is fallible, so only «verified/unverified», never «true».
- Keep `ANSWERED_WITH_SOURCES` semantics backward-compatible for old evidence; never reclassify historical runs.
- The trace in a real runner: hash-only already, but re-check redaction before enabling it (R3-C1 limitation).

## 5. Recommended deterministic experiments (no Qwen)

1. **E1 — interception feasibility:** in tests only, with the R3-C1 fixture and a FAKE model, a prototype `_GuardedEngine` subclass turns scenario A or E's final answer into one feedback re-prompt. The FAKE model then follows the presented original link. Assert:
   - the tools go through policy and audit;
   - quotas are not reset;
   - `max_turns`, deadline and cancel are honoured;
   - the budget is exhausted gracefully into an explicit «incomplete» state.
2. **E2 — verifier accuracy matrix:** on scenarios A–E plus new adversarial ones (fake «original» page, info page that copies the title, 404 original, original only via `web_find`), measure false PASS and false FAIL of candidate source-type signals, without URL patterns.
3. **E3 — objective sources:** compare (a) explicit operator or task spec, (b) deterministic extraction of enumerated identifiers from the instruction (for example «X and Y»), (c) model-proposed objectives that may only add. Measure on synthetic instructions; no RFC rules in the product.
4. **E4 — budget accounting:** prove that no path allows unbounded generate calls (property test over FAKE sequences).

Each experiment's evidence is FAKE-model only and must be labelled as such.

## 6. Outstanding unknowns

- **Where objectives come from** for free-form user instructions. Every framework surveyed has a developer write the expected output or validator, or trusts the LLM. An open-domain assistant has neither; this is the core R3-C2 design decision.
- Whether Qwen3.5:4b **acts on structured feedback** (resumes tool use) or just rephrases. Unknown; it needs an authorised real run, and must not be inferred from FAKE results.
- Whether a JSON ledger (Magentic-One style) is reliable on Qwen3.5:4b. Not measured.
- On the real RFC Editor site, whether the original link on `/info/rfcN/` is within the first 25 links. Not verified (R3-C1).

## 7. Qwen3.5:4b integration considerations

- CPU inference took about 7.5 min for 9 responses in real run `43189355873`, so every extra LLM call matters. Prefer **deterministic** verification (no extra LLM call when the check passes) and **at most 1–2** feedback re-prompts.
- Avoid an extra per-round ledger call (Magentic-One).
- Keep the feedback short and structured: the 16 k context is shared with page views of about 3.5 k characters.
- The same plan-hash and authorisation protocol applies. Any change to limits or behaviour needs a new plan digest and a new authorisation; no real run without it.

## 8. Recommendation (engineering decision for the operator)

Approve **Option 1 (minimal patch)**, starting **only with experiment E1 + E4 in tests**:
- a deterministic completion check at the existing `_GuardedEngine` interception point;
- PydanticAI- and OpenHands-style bounded feedback with an explicit budget and a terminal «incomplete» state;
- evidence from the existing registry.

In parallel, decide the **objective-source policy** (§6, E3) before any product change to `_compose`. Do **not** migrate the runtime or adopt Magentic-One-style self-assessed completion.
