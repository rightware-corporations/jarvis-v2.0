# RIGHTWARE JARVIS v2.0 — Minimal contract for bringing R2 tool execution into the product

**Date:** 2026-11-11. **Status:** design contract, documented only. **Nothing here is wired into `rightware/`** (no product code changed). **QWEN REAL: no new run.**
**Compared:**
- the R2 lab agent (`labs/work04_cognitive/w04lab/harness_r2.py`, on top of the frozen WORK-02 `w02lab` sandbox and policy);
- the product runtime (`rightware/runtime.py`, `rightware/voice.py`, `rightware/windows_actions.py`, `configs/local.toml`).

Labels: **FACTO** = in code; **INFERÊNCIA** = engineering judgement.

## 1. What each side does today (FACTO)

| Concern | Product (`rightware/`) | R2 lab agent |
|---|---|---|
| Engine | Local Ollama only (`127.0.0.1:11434`, `OLLAMA_NO_CLOUD=1`). API keys and proxies are stripped from the child environment. `chat_command` refuses cloud models | Same engine. Pinned digest checked in preflight |
| Agent | `SimpleAgent`, no tools (chat CLI `-a simple`; `OpenJarvisBrain` in voice) | `OrchestratorAgent` in `function_calling` mode with 4 tools, `parallel_tools=False` |
| Who decides an effect | **Deterministic Portuguese rules** (`detect_actions`), never the model | **The model** proposes a tool call; code authorises or refuses it |
| Authorisation | Session flag `--allow-actions` **and** a per-action spoken/typed «sim»; anything else cancels | `Policy`: allowlist, exact schema, budgets (12 calls; per tool 3/6/2/3), single-use approval bound to exact arguments, fail-closed batches, deadline, cancel. Overwrite pre-check (R2) |
| Execution boundary | Fixed absolute executables, `shell=False`, no user arguments | `Sandbox`: simple ASCII names, read only in `input/`, new files only in `output/`, `O_NOFOLLOW`, inode check, atomic `os.link` publish |
| Outcome truth | `ActionResult` is `VERIFIED` only if a new stable process is observed. The reply is generated from the outcome (`describe`), not by the model | `completion.py`: the task is complete only for a persisted, authorised file **and** a later `verify_report` PASS on that same file. A text answer never counts |
| False-claim guard | Regex `_CLAIMS_EFFECT` appends «nenhuma acção foi executada» | `claims_r2` sentence- and negation-aware claim detector; `false_success` and `premature_completion_claim` |
| Untrusted content | None reaches the model (no tools) | Tool output is framed as data. `source_guard` quarantines directed instructions. Replay uses a random-boundary frame (fixed in `b59eec5`) |
| Context | `AgentContext` keeps the session conversation (voice) | Each `run()` is a fresh context. One bounded continuation with sanitised replay |
| Audit | Action id, authorised/confirmed, outcome, pid. **No conversation text** | Policy log (sanitised arguments), trace (previews), evidence JSONL |

## 2. Minimal contract for product tool execution

To be implemented in `rightware/` only after a separate authorisation. Each item names its R2 source and a product test it must pass.

| # | Rule | Reuse from R2 | Product acceptance test (deterministic) |
|---|---|---|---|
| C1 | **Closed tool registry.** Tools are registered by exact name; nothing else is constructible. No shell, network, code execution or generic file access | `ToolExecutor` allowlist + `Policy.validate` | An unknown or extra-argument tool call is refused and logged; the registry equals the allowlist |
| C2 | **Two independent checks per call:** a hook before execution and a re-check at the tool boundary, with approval bound to the exact canonical arguments, single use | `Policy.before_tool_call` + `authorize_execution` | Arguments changed after approval are refused; a replayed approval is refused |
| C3 | **Budgets and fail-closed batches.** Global and per-tool limits, deadline, cancel. One invalid call in a model response denies the whole batch | `Budgets`, `batch_guard`, `halt_reason` | Limit reached → refusal; a batch with one invalid call executes nothing |
| C4 | **Effects need session authorisation AND per-action human confirmation.** Read-only tools need neither. Writes and Windows effects need both | `WindowsActions.run` + `is_confirmation` (product); `write_authorized` (lab) | Without the flag → REFUSED; anything other than an explicit non-negated «sim» → CANCELLED |
| C5 | **Model-proposed effects go through the SAME `WindowsActions` path** as rule-detected ones. The model never builds paths or commands | `ACTIONS` table, fixed executables | A model tool call can only name an `action_id` from `ACTIONS`; the result text comes from `describe(result)` |
| C6 | **Outcome, not prose, defines success.** The user-facing status comes from the verified tool outcome (`VERIFIED` / persisted+verified artefact). Model claims are checked (`claims_r2`) and never override it | `completion.py`, `describe`, `claims_r2` | A model saying «feito» with no verified outcome is shown as not done |
| C7 | **Untrusted content stays data.** Every document or tool result shown to the model is framed. Any re-injection into a user/system turn uses an unguessable boundary with neutralised markers. Directed instructions are quarantined, but this is never treated as proof of safety | `UNTRUSTED_HEAD/TAIL`, `source_guard`, `recovery_r2.bounded_source_replay` | Forged end-of-frame text stays inside the frame (`test_w04_r2_hardening`) |
| C8 | **Deterministic facts are computed by code**, not inferred by the model: date order, arithmetic, existence of files. The model gets the computed result | `chronology_r2` (date order), sandbox existence checks | A reversed «antes/depois» claim between two dates is flagged |
| C9 | **Bounded recovery:** at most one continuation, same policy object and budget, no new permissions | `recovery_r2` | A continuation cannot exceed the remaining budget |
| C10 | **Audit without conversation text:** tool name, sanitised arguments (hash for long values), decision, outcome, timestamps. Local only. Never credentials | `Policy._record`, `WindowsActions.audit`, `evidence_r2` redaction | The audit log contains no user text and no credential-shaped strings |
| C11 | **Local-only engine and pinned upstream** remain preconditions | `runtime.child_environment`, `verify_source`, `prepare_config` | Unchanged |

## 3. Must NOT be carried into the product

These are lab or benchmark artefacts; they encode a synthetic task and its answers:
- **Synthetic benchmark machinery:** `scenarios.py` and every ground-truth structure (`truth`, `facts`, `forbidden_*`, canary).
- **Answer-checking evaluators:** `verifier_v2.py`, `oracle*.py`, `factual.py`, `assess*.py` and cross-run gates. They score reports against hidden answers.
- **Benchmark-specific guidance:**
  - `feedback_r2.RULE_HINTS` is tied to the benchmark report contract (R1–R8). In the product, feedback must come from the real tool outcome.
  - `SYSTEM_PROMPT` of the harness: the report format and finding types are benchmark-specific.
- **Test scaffolding:** `fake_engines`, `fake_reports`, human-review packet, smoke runner and the CPU/GPU workflows.
- **Policy rules tied to the report task:** «verify only a report written in this run» and «write only after a read». The general principles (order constraints, single-use approval) carry over; these specific rules do not.

## 4. Gaps before any product integration (INFERÊNCIA)

1. **No product tool yet besides the two Windows actions.** Defining the first real product tool (for example a read-only document reader over a user-chosen folder) needs its own spec: which folder, size limits, consent.
2. **Context model differs.**
   - The product keeps a session conversation; the lab restarts context per run.
   - In the product, tool results must not be stored in conversation memory as trusted user turns. This is the same risk as D1, in a different place.
3. **Confirmation UX for model-proposed actions.** Today only rule-detected actions ask for confirmation. A model-proposed action must ask in the same words and must not be confirmable by text that the model itself produced.
4. **Real-model evidence is weak.**
   - R2 has 0 PASS on real Qwen so far: EVOL-4001 failed twice on CPU, after 0/3 on Kaggle.
   - The tool-execution safety properties are demonstrated: 0 sandbox violations in every real run.
   - Task competence is not.
   - Integration should start with tools whose correctness is verified by code (C6, C8), not by the model's prose.
5. **Windows-only effects.** `WindowsActions` is verified only on the Windows CI runner; recipient-PC acceptance is still pending (`docs/WINDOWS_VOICE.md`).

## 5. Proposed next gate

1. **Real Qwen, EVOL-4001 only, on the pinned new R2 HEAD (CPU workflow).** This measures whether the bounded replay, the overwrite pre-check and the chronology feedback change the failure. It is a different R2 condition and must not be pooled with earlier runs.
2. **Then a pre-registered holdout:** new seeds and new attack wording, before any generalisation claim.
3. **Product:** a separate spec for C1–C11 with the first read-only product tool, tests first. No `main`/`develop` change until it is reviewed.
