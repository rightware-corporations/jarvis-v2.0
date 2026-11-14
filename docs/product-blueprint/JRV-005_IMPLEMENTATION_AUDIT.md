# JRV-005 — Current Implementation Audit & Evidence Matrix

**Product:** RIGHTWARE JARVIS v2.0  
**Audit date:** 2026-11-14  
**Version:** 1.0 — evidence-based, read-only audit of production source tree and selected tests  
**Status:** AUDIT COMPLETED / FINDINGS PROPOSED FOR REVIEW — no new implementation approval  
**Audited \`develop\` commit:** \`f4a50e5075d0b94f635b1540885a0f2bd5258bc8\`  
**Snapshot:** GitHub repository tree API, \`recursive=1\`, non-truncated; 378 Git entries including directories.  
**CI on exact audited SHA:** WORK-05 product \`43602493816\` SUCCESS; foundation \`43602493752\` SUCCESS and \`43602497227\` SUCCESS.  
**Evidence base:** Actual files fetched at audited ref, checked against JRV-001/002/003/004 and HANDOFF; selected test source and CI workflow.  
**Scope:** Product code, runtime entrypoints, tested engineering pathways and clearly separated laboratory code.  
**Not performed:** local repo checkout, execution of tests in this audit, Qwen inference, Windows audio/hardware validation, user acceptance, full dependency transitive audit or security penetration testing.  
**Next:** JRV-006 — gaps, risks, dependencies and prioritization.

## 1. Evidence methodology and grades

This audit distinguishes *existence of code*, *selected test coverage*, *CI green*, and *end-to-end usable product*. These are not interchangeable.

| Code | Evidence grade | Interpretation |
|---|---|---|
| VERIFIED_SCOPE | Implemented and covered by inspected tests and successful pinned-env CI; only for the **specific tested behaviour/environment** |
| IMPLEMENTED_UNVERIFIED | Production code exists, but present evidence does not establish the requested target behaviour or hardware/integration |
| PARTIAL | Some responsibilities exist but not the full JRV requirement or not integrated across entrypoints |
| ABSENT_IN_AUDITED_PATHS | No corresponding production feature identified in this complete tracked tree and examined module paths; not proof that no hidden upstream capability exists |
| UNKNOWN | Could exist upstream or in an unexamined layer; evidence insufficient |
| LAB_ONLY | Experiment or deterministic fixture, not a product runtime guarantee |
| PROPOSED | Blueprint target, no implementation implied |

A single subsystem can have multiple grades: e.g. Windows tool policy has verified fake-unit behavior, but real Windows process launch remains unverified on the target device. \`verified\` here never implies commercial readiness or user acceptance.

### 1.1 Observed GitHub/CI

- \`develop\` at audit start: \`f4a50e5075d0b94f635b1540885a0f2bd5258bc8\`.
- Git tree: 378 entries, \`truncated=false\`. Tracked production package \`rightware/\`; \`tests/\`; \`qa/\`; \`labs/\`; \`vendor/openjarvis\` (Git submodule) and documentation.
- On this SHA: GitHub CI product \`43602493816\` and foundation \`43602493752\`, \`43602497227\`, all SUCCESS.
- \`.github/workflows/work05-product.yml\`: plain Python \`unittest\` first (upstream-dependent tests may skip), then \`uv sync --frozen --no-dev\` in pinned OpenJarvis venv and \`python -m unittest discover -s tests -v\`; the workflow explicitly fails if the venv output contains \`skipped\`.
- Prior A3 engineer checkpoint reports **408 tests OK, zero skips** in pinned venv at code SHA \`65dad56f73b872017ef5c2d1c8717909d7c0106e\`. The current audit verified successful product CI on its own SHA but did **not independently fetch a current test-count log**; therefore 408 is historical evidence, not a newly measured count.
- No source-code modification in this audit. Tests were **read**, not re-run.

### 1.2 Audit limitations

The complete tracked **path list** was enumerated. Selected source files and representative tests were fetched; this is not a line-by-line security review of every Python file, every laboratory script or the full pinned \`vendor/openjarvis\` submodule tree. An unavailable or hidden upstream feature is marked UNKNOWN rather than asserted absent. \`CI SUCCESS\` attests to configured jobs, not voice integration, real model quality or target Windows functionality.

## 2. The product currently has three distinct execution experiences

~~~mermaid
flowchart TD
  CLI["python jarvis.py"]
  CLI -->|chat| Simple["Upstream SimpleAgent CLI + Ollama"]
  CLI -->|voice| Voice["RIGHTWARE VoiceLoop"]
  Voice --> VoiceBrain["Upstream SimpleAgent + AgentContext"]
  Voice --> Win["RIGHTWARE WindowsActions"]
  CLI -->|agent| Agent["RIGHTWARE AgentSession"]
  Agent --> Orch["Pinned OrchestratorAgent"]
  Orch --> Policy["RIGHTWARE AgentPolicy"]
  Orch --> Browser["RIGHTWARE PublicBrowser / HttpxFetcher"]
  Orch --> Actions["RIGHTWARE WindowsActions"]
  Agent --> A1["A1 TaskContract opt-in"]
  Agent --> A2["A2 ReceiptLedger opt-in"]
  Agent --> A3["A3 CompletionGate opt-in"]
  ChatDemo["qa/Kaggle notebook: Qwen experiments"] -.-> Simple
~~~

**Finding F-001 — Fragmented entrypoints (HIGH product integration relevance):**
1. \`python jarvis.py chat\` goes through \`rightware.runtime.chat_command\` into the upstream CLI's \`simple\` agent with Ollama; no proof that this route uses RIGHTWARE A1/A2/A3.
2. \`python jarvis.py voice\` invokes \`rightware.voice.VoiceLoop\` with \`OpenJarvisBrain\` wrapping upstream \`SimpleAgent\`, its own \`AgentContext\`; Windows actions are detected deterministically outside the model and confirmed through \`WindowsActions\`.
3. \`python jarvis.py agent "..." \` invokes \`rightware.agent.cli\` and creates \`AgentSession\` using pinned \`OrchestratorAgent\` and RIGHTWARE authorization path.
4. **Critically, the public \`agent\` CLI currently creates \`AgentSession\` without passing \`task_preset\`, \`receipts=True\` or \`completion_gate=True\`** (inspected \`rightware/agent/cli.py\` lines 19–53). Therefore A1/A2/A3 exist as usable **Python opt-ins/tested core**, not as a demonstrated ordinary CLI product experience.
5. \`voice\` is not integrated through the full A3 policy/receipt/completion path; \`session.py\` explicitly says "text now; voice later through the same call."

**Consequence:** It is incorrect to claim "JARVIS already has memory, voice, autonomous task execution and verified completion in one interface." These currently span separate paths with different safety and contextual behavior.

## 3. Inventory by JRV-004 logical module

| MOD | JRV subsystem | Actual source found | Grade and evidence | Verified boundary / gap |
|---|---|---|---|---|
| MOD-01 | JRV-01 Interaction/perception | \`rightware/voice.py\`, \`rightware/runtime.py\`; simple upstream CLI | PARTIAL / IMPLEMENTED_UNVERIFIED | Text and voice loop exist; STT/TTS wrappers and fake voice tests exist; target microphone/voice end-to-end not proven |
| MOD-02 | JRV-02 Intent/context | Upstream \`SimpleAgent\` (referenced from voice), \`OrchestratorAgent\` (agent), \`rightware/agent/session.py\` | PARTIAL | Model contextual interpretation exists; no independent RIGHTWARE context-resolution/ambiguity-correction controller identified |
| MOD-03 | JRV-03 Memory/knowledge | \`voice.OpenJarvisBrain._ctx\`, in-session model context, in-memory \`ReceiptLedger\`, \`TaskTrace\` | PARTIAL; durable memory ABSENT_IN_AUDITED_PATHS | Voice retains turn context in an \`AgentContext\`; no RIGHTWARE durable user-memory repository/cross-restart deletion API identified |
| MOD-04 | JRV-04 Planning/reasoning | \`AgentSession\` + pinned upstream \`OrchestratorAgent\`, A1 narrow trusted presets | PARTIAL | Limited model tool planning and immutable synthetic browse objectives; no generic product plan/dependency graph with arbitrary approved task classes |
| MOD-05 | JRV-05 Execution/adapters | \`rightware/windows_actions.py\`, \`rightware/agent/web.py\`, \`browser.py\`, \`session.py\` | VERIFIED_SCOPE for policy/fake adapters; PARTIAL overall | Two fixed Windows actions; scoped read-only public browser/web; no generic file create/move/send/calendar connectors found |
| MOD-06 | JRV-06 Verification/recovery | \`task_contract.py\`, \`receipts.py\`, \`completion.py\`, \`session.py\` | VERIFIED_SCOPE for opt-in A1/A2/A3 with FAKE; PARTIAL overall | Bound receipts and deterministic gate; only synthetic original-document presets; \`identity_rule=NONE\` never yields \`COMPLETE_VERIFIED\`; no durable resume |
| MOD-07 | JRV-07 Security/identity | \`agent/policy.py\`, \`agent/web.py\`, \`agent/browser.py\`, \`windows_actions.py\` | VERIFIED_SCOPE for allowlist/quotas/SSRF/approval tests; PARTIAL | Runtime exact argument approval, browser controls and Windows confirmations. No comprehensive multi-principal identity and secret management layer identified |
| MOD-08 | JRV-08 Runtime/infrastructure | \`jarvis.py\`, \`rightware/runtime.py\`, \`rightware/diagnose.py\`, \`rightware/windows/Jarvis-Issa.ps1\`, \`configs/\` | PARTIAL / VERIFIED_SCOPE setup logic | Pinned submodule \`f21d902...\`, local Ollama commands, doctor; no demonstrated packaged, installed, recoverable Windows service, durable job scheduler |
| MOD-09 | JRV-09 Experience/personalization | CLI \`chat\`, \`agent\`, \`voice\`, Kaggle demo notebook | PARTIAL | CLI and experimental notebook chat exist; no integrated production graphical desktop UX with task history, approvals and memory management |
| MOD-10 | JRV-10 Engineering/quality | \`.github/workflows/\`, \`tests/\`, \`qa/compare_models.py\`, \`labs/\`, \`docs/HANDOFF.md\` | VERIFIED_SCOPE for configured CI and selected regressions; PARTIAL end-to-end | Pinned-env suite and green CI; no verified full-product real Windows/voice + real-Qwen A3 recovery acceptance |

**Granularity warning:** A module can be \`PARTIAL\` even where a narrow internal component is \`VERIFIED_SCOPE\`. No numerical percentage of full product completion follows from these grades.

## 4. Product components: real paths and key symbols

| Component | Source and symbols checked | Existing responsibility | Key caveat |
|---|---|---|---|
| Launcher | \`rightware/runtime.py\`: \`verify_source\`, \`prepare_config\`, \`setup\`, \`doctor\`, \`chat_command\`, \`voice_command\`, \`agent_command\` | Pinned source checks, local setup/launcher and health checks | \`doctor\` explicitly does not perform inference |
| Voice | \`rightware/voice.py\`: \`WhisperSTT\`, \`SapiTTS\`, \`KokoroTTS\`, \`OpenJarvisBrain\`, \`VoiceLoop\` | STT, TTS options, voice/text loop, upstream conversational context | Voice tests use FakeBrain/FakeSTT/FakeTTS; Windows real microphone not validated |
| Windows effects | \`rightware/windows_actions.py\`: \`ACTIONS\`, \`detect_actions\`, \`WindowsActions.run/_execute\` | Fixed \`notepad\` / \`calculator\` only; confirmation, process verification, safe audit | Tests explicitly do **not** launch real processes |
| Agent launcher | \`rightware/agent/cli.py:main\` | One text instruction with optional \`--allow-web\`, \`--site\`, \`--allow-actions\` | No CLI opt-in flags/wiring for A1/A2/A3 |
| Core agent | \`rightware/agent/session.py:AgentSession\`, \`_RightwareOrchestrator\`, \`_PolicyTool\`, \`_CompletionEngine\` | Pinned orchestrator, policy hook, tool execution, answers and opt-in gate | One-run session; experimental gate only when constructor flags supplied |
| Policy | \`rightware/agent/policy.py:AgentPolicy\`, \`Budgets\`, \`ToolDef\`, \`canonical\` | Tool registry, allow scopes, deadlines, quotas, anti-loop, audit before effect | Authorization of one tool call is not proof of its execution |
| Web read | \`rightware/agent/web.py:HttpxFetcher\`, \`check_url\`, \`Page\` | Public GET, URL/SSRF checks, peer validation, content framing | No authenticated POST, login, browser JS or arbitrary external workflow |
| Semantic browser | \`rightware/agent/browser.py:PublicBrowser\` | Scoped semantic links/forms, GET search, HTML parse | No browser JavaScript, arbitrary UI automation or authenticated sessions |
| Tracing | \`rightware/agent/trace.py:TaskTrace\` | Opt-in sanitized tool/model view trace | In-memory; not durable task history |
| Trusted task catalog | \`rightware/agent/task_contract.py:TaskContract\`, \`BrowserObjective\`, \`TRUSTED_PRESETS\` | Code-owned immutable catalog and validation | Two synthetic presets only; cannot accept arbitrary model-created contracts |
| Receipts | \`rightware/agent/receipts.py:ExecutionReceipt\`, \`ReceiptLedger\` | Runtime-linked authorization/execution/timeout attribution | In-memory; operational evidence not publisher identity |
| Completion | \`rightware/agent/completion.py:evaluate\`, \`CompletionResult\`, \`recovery_feedback\` | Pure deterministic verdict and constrained recovery instructions | Strict original-document identity unresolved; \`COMPLETE_VERIFIED\` unreachable for current synthetic presets |
| Lab models | \`labs/work02_active_agent\`, \`labs/work04_cognitive\`, \`labs/work07_*\` | Deterministic fake models/benchmarks and research experiments | \`LAB_ONLY\`; not wired as general production JARVIS capability |
| Kaggle | \`qa/JARVIS_ISSA_KAGGLE*.ipynb\`, \`qa/compare_models.py\` | Actual remote model experiments and notebook flow | Interactive notebook is not installed desktop app nor real Windows control |

### 4.1 Scope and security detail

- \`rightware/windows_actions.py:ACTIONS\` contains \`notepad\` and \`calculator\`, with deterministic Portuguese detection, fixed executables and confirmation; no arbitrary commands or filenames.
- \`rightware/agent/web.py\` is explicitly GET-only, with no cookies, login, model-chosen headers or POST. \`browser.py\` exposes semantic link/field actions and checks every URL/redirect for restrictions.
- \`rightware/agent/policy.py\` performs \`before_tool_call\` and \`authorize_execution\`; grants are bound to canonical parameters, with limits and audit.
- \`rightware/agent/task_contract.py\` \`TRUSTED_PRESETS\` has exactly two fixtures: \`synthetic-archive-two-originals\` and \`synthetic-archive-two-originals-recovery\`, both for \`archive.fixture.example\`; only second allows one recovery continuation.
- \`rightware/agent/session.py:AgentSession.__init__\` has opt-in keyword flags \`task_preset=None\`, \`receipts=False\`, \`completion_gate=False\`, and raises on gate without both trusted preset and receipts.
- \`rightware/agent/completion.py\` uses bound executed audited receipts, exactly matching objective URLs and raw-byte evidence, without using model prose as verifier. It classifies original identity as \`UNKNOWN_IDENTITY\` without a trusted rule.

## 5. UC-001–033 implementation traceability

**Key:** \`S\` = scoped implementation/test evidence; \`P\` = partial; \`U\` = implemented path but target behavior unverified; \`A\` = absent in audited product paths; \`?\` = unknown pending further review. Ratings apply to **full UC target**, not individual subtasks.

| UC | Required behaviour | Evidence in current production paths / test | Grade and main gap |
|---|---|---|---|
| 001 | Answer factual question | Upstream \`chat\`, \`voice.OpenJarvisBrain\`; \`qa/compare_models.py\` | U — model responds, no full quality acceptance corpus |
| 002 | Resolve ambiguous intent | Model context; Kaggle manual dialogue | P — no dedicated RIGHTWARE disambiguation controller |
| 003 | Repair misunderstanding | Upstream/context history; Kaggle manual corrections | P — not reliable/benchmarked |
| 004 | Track pronoun references | \`voice.OpenJarvisBrain._ctx\` | P — context present; limits and referent correctness not verified |
| 005 | Disclose uncertain knowledge | Session/system prompts, QA cases | P — not an independent truthful-claim controller for all modes |
| 006 | Compare sources with web | \`agent/web.py\`, \`browser.py\`, \`AgentSession\` | P — scoped public read path, answer-quality tests incomplete |
| 007 | Summarize a local document | No scoped local file-reading adapter found | A — no product UC-007 integration |
| 008 | Save preference durably | \`voice._ctx\` is transient | A — no durable memory write/consent repository identified |
| 009 | Recall after restart | No RIGHTWARE durable user memory store identified | A — not proven |
| 010 | Correct/delete saved memory | No user memory management interface found | A — not proven |
| 011 | Protect private information | Policy/log redaction; web safety | P — no complete user memory/identity isolation model |
| 012 | Decompose goal into plan | \`OrchestratorAgent\` model reasoning, A1 fixed objectives | P — no generic typed plan/dependency graph |
| 013 | Ask for essential input | Agent natural-language generation | U — no deterministic missing-field contract seen |
| 014 | Create local folder | Windows adapter only launches two apps | A — no filesystem create tool identified |
| 015 | Organize files | No product file organize tool found | A — no read/write/undo/preview adapter |
| 016 | Draft message without sending | General text model answer | P — drafting plausible; no mail integration required/verified |
| 017 | Send confirmed message | No mail/send tool in product registry | A — no provider ID/idempotency verification |
| 018 | Read calendar | No calendar adapter in product registry | A |
| 019 | Change calendar after approval | No calendar write adapter | A |
| 020 | Launch authorized app | \`windows_actions.py\`, \`tests/test_windows_actions.py\` | S for mocked policy; U for actual Windows |
| 021 | Find and verify original docs | A1/A2/A3, \`web.py\`, \`browser.py\`, tests A1–A3 | P — synthetic only; identity rule NONE |
| 022 | Perform contracted multi-step task | \`session.py\`, \`policy.py\`, A1/A2/A3 tests | S for bounded FAKE browse fixture; P broadly |
| 023 | Verify mandatory objectives | \`completion.py\`, \`tests/test_work07_milestone_a3_completion.py\` | S for evidence gate; no real original-document identity |
| 024 | Communicate partial/unknown | A3 \`AgentReply.task_completion\`, \`completion\` | S opt-in FAKE; CLI flags not exposed |
| 025 | Resume across restart | No durable \`TaskSnapshot\`/ledger | A |
| 026 | Cancel active task | \`AgentSession.cancel\`, policy cancellation | S for denial of new calls; P for durable/OS kill guarantees |
| 027 | Deny unauthorized tool | \`AgentPolicy\`, tests \`test_agent_policy_*\`, issue #9 | S for scoped tested path |
| 028 | Resist prompt injection | Browsing prompts + independent policy, security tests | P — model instruction adherence not proven universally |
| 029 | Voice end-to-end | \`voice.py\`, \`tests/test_voice.py\` fake and launcher | U — no real mic/STT/TTS/target hardware validation |
| 030 | Setup and diagnose | \`runtime.py\`, \`diagnose.py\`, \`tests/test_runtime.py\` | S for programmatic checks; U for deployment target |
| 031 | Recurring automation | No product scheduler/durable recurrence | A |
| 032 | Recover from execution failure | A3 limited continuation; A2 timeout/late handling | S for FAKE bounded run; A for crash-consistent recovery |
| 033 | Show task history and consent | CLI/trace/audit outputs | P — no integrated user-facing history/approval management UI |

**Reminder:** a capability marked \`A\` means absent **from inspected RIGHTWARE product paths and tracked repository design**, not that the upstream dependency lacks any related function.

## 6. CT-01–10 coverage

| CT | Domain | Evidence found | Status/gap |
|---|---|---|---|
| CT-01 | Routing & clarification | \`runtime.chat\`, \`voice\`, \`agent\` separate; model decisions | PARTIAL — no common intent router |
| CT-02 | Context integrity | Upstream SimpleAgent \`AgentContext\`; experiments | PARTIAL — context only in specific paths |
| CT-03 | Truthful output | \`AgentReply\`, \`reply_json\`, A3 objective state | PARTIAL — not uniformly enforced in \`chat\`/\`voice\` |
| CT-04 | Memory lifecycle | \`voice.OpenJarvisBrain._ctx\` transient | ABSENT durable lifecycle |
| CT-05 | Identity/privacy | Policy, safe arguments, redacted logging | PARTIAL — principal/consent and memory retention design absent |
| CT-06 | Plan & authorization | \`AgentPolicy\`, A1 fixed preset contracts | PARTIAL — policy strong in scope, generic planner missing |
| CT-07 | Evidence/completion | \`receipts.py\`, \`completion.py\` and tests | VERIFIED_SCOPE opt-in FAKE; identity and persistence unresolved |
| CT-08 | Side effects/consent | \`WindowsActions\` confirmation, policy | VERIFIED_SCOPE narrow tool set; general consent connectors absent |
| CT-09 | Recovery/lifecycle | A2 late handling, A3 bounded continuation | PARTIAL — in-memory only, no crash resume |
| CT-10 | Runtime quality | setup/doctor, test workflows, Kaggle notes | PARTIAL — target device readiness not established |

## 7. Test/source evidence index

| Evidence source | What it can support | What it cannot support |
|---|---|---|
| \`tests/test_agent_policy_r1.py\`, \`test_agent_policy_web.py\` | Policy canonicalization, budgets, authorization/denial under fixtures | Universal attack resistance across all environments |
| \`tests/test_work07_browser.py\`, \`test_agent_network.py\` | Controlled public browser and network safety fixtures | Browser JS/login/production site interoperability |
| \`tests/test_work07_milestone_a1_product.py\` | A1 opt-in trusted contracts | General task definitions from user/model |
| \`tests/test_work07_milestone_a2_receipts.py\` | A2 receipt binding, faults/timeouts in test harness | Durable enterprise audit |
| \`tests/test_work07_milestone_a3_completion.py\` | 29 A3 tests against FAKE/model fixtures; \`UNKNOWN_IDENTITY\` safety | Real Qwen recovery or original publisher authenticity |
| \`tests/test_issue9_refusal_reason.py\` | Scope-correct rejection explanation regression | All downstream model behavior |
| \`tests/test_voice.py\` | VoiceLoop coordination with FakeBrain/STT/TTS; interruptible control | Real audio hardware operation |
| \`tests/test_windows_actions.py\` | App launch policy with fake subprocess | Actual Calculator/Notepad launch on Issa's PC |
| \`tests/test_runtime.py\`, \`tests/test_windows_readiness.py\` | Runtime setup/doctor/config and environment checks | Complete installed/persistent Windows app |
| \`qa/JARVIS_ISSA_KAGGLE*.ipynb\`, \`qa/compare_models.py\` | Real Qwen model comparison experiments when execution artifact exists | Continuous assistant service or Windows tool access |
| \`labs/work02_active_agent\`, \`labs/work04_cognitive\`, \`labs/work07_r3c*\` | Research and fake/restricted real-gate experimental evidence | Product functionality without explicit integration |
| \`.github/workflows/work05-product.yml\` | Tests defined and executed at pinned dependency in CI | Real model, voice/audio, device and integration acceptance |

**Potential engineering debt F-002:** some source docstrings in \`task_contract.py\` and \`session.py\` still describe A1 as if A2/A3 were not implemented; current modules implement A3 elsewhere. These are documentation consistency issues, not proof of a runtime defect.

**Potential engineering debt F-003:** current README first-release language ("text first; voice and Windows pending") and historical \`docs/ARCHITECTURE.md\` predate the extensive A1–A3 development. Keep them historically correct but introduce a clear current status page to prevent confusion.

## 8. Integration and architectural risks — prioritized findings

| Finding | Severity for intended product | Evidence | Follow-up (not implementation authorization) |
|---|---|---|---|
| F-001 Split chat/voice/agent execution paths | HIGH | \`runtime.chat_command\`; \`voice.OpenJarvisBrain\`; \`agent.cli:AgentSession\` | Design common user-facing control plane; preserve existing tested paths during migration |
| F-004 A1–A3 not wired into ordinary agent CLI | HIGH | \`agent/cli.py\` passes none of \`task_preset\`/\`receipts\`/\`completion_gate\` | Product opt-in UX and safe preset selection before any rollout |
| F-005 No durable user memory | HIGH | Transient \`AgentContext\`; tracked RIGHTWARE tree lacks memory repository | Define consent/privacy schema and persistence acceptance |
| F-006 No durable resumable task journal | HIGH | A2 receipts/A3 gate held in process memory | Design idempotency, reconciliation, event persistence and crash recovery |
| F-007 Only synthetic task contracts | HIGH for original-doc use case | 2 fixture presets, \`identity_rule=NONE\` | Trusted identity design and domain-specific verifier |
| F-008 Very narrow OS action portfolio | MEDIUM | \`ACTIONS\` includes only Notepad/Calculator | Prioritize actions from approved use cases; avoid unrestricted shell |
| F-009 Missing calendar/mail/file adapters | MEDIUM–HIGH | No product tools registered in \`session.py\` for these actions | Sequence integrations after policy/contract approval |
| F-010 Real Windows voice validation missing | HIGH for hands-free release | \`test_voice.py\` uses fake adapters | Hardware audio/STT/TTS and false wake benchmarks |
| F-011 Model response quality not governed by dedicated context router | HIGH for usefulness | Dialogue handled by LLM; Kaggle ambiguous "mundo" episode | Portuguese intent/repair corpus and explicit routing strategy |
| F-012 UI still developer-facing | HIGH for Issa pilot | CLI & experimental Kaggle notebook | Design local user surface and approval/task-state UX |
| F-013 No confirmed model A3 recovery with Qwen | MEDIUM–HIGH | A3 tests FAKE, Qwen separate QA path | Authorized real-model end-to-end acceptance separately |
| F-014 No risk-based release acceptance targets | MEDIUM | JRV-003 KPIs TBD | Baseline on hardware/corpus, then set release gates |
| F-015 Upstream vendor/API dependency not independently fully audited here | MEDIUM | Pinned submodule; selected wrapper inspection only | API/licence/security compatibility investigation |
| F-016 Documentation chronology mixed | LOW–MEDIUM | old launcher architecture doc + new BP | Status/provenance banner, preserve historical doc |

Severity is a **planning assessment**, not a verified vulnerability rating. A "missing capability" is not a defect unless it belongs to an approved release scope.

## 9. Proposed architecture-to-code decision register

| Decision domain | Evidence-informed recommendation | Dependency/guardrail | Status |
|---|---|---|---|
| Unified orchestration | Create a shared trusted execution/control interface across chat/voice/agent gradually | Preserve A/B default-off and action scope | RECOMMENDATION |
| Context/intent | Add measurable contextual repair and low-cost routing before expensive tools | Portuguese corpus and no unneeded network requests | RECOMMENDATION |
| Memory | Differentiate ephemeral context, durable user facts and task state; adopt transactional store only after policy | Consent, provenance, deletion, restart tests | RECOMMENDATION |
| Task contracts | Broaden supported contract families only through code-approved schemas and independent verification | Prevent user/model data from self-minting authority | RECOMMENDATION |
| Windows integrations | Keep typed narrow adapters with confirmation; expand from approved use-case needs | Windows target validation and audit | RECOMMENDATION |
| Original source identity | Use trusted expected digests or publisher registry where appropriate; no URL-alone proof | Threat model and negative fixture | OPEN |
| Real-model acceptance | Pin model, hardware, prompts, budgets and provider; compare against FAKE controls | Explicit experiment approval and data-handling review | RECOMMENDATION |
| Runtime packaging | Local-first modular process is plausible; measure actual target hardware | Security and deployment feasibility | HYPOTHESIS |
| Shared Intelligence Core | Potential local code reuse, not automatic service dependency | Separate repo code/licence/API audit | INVESTIGATION REQUIRED |

## 10. JRV-006 input: dependency graph

~~~mermaid
flowchart TD
  Scope["Approve release scope and behaviour contracts"]
  Scope --> Routing["Unify routing / app surface"]
  Scope --> Privacy["Memory consent and retention"]
  Scope --> Actions["Select first action adapters"]
  Privacy --> Memory["Durable user memory"]
  Privacy --> Ledger["Durable task event ledger"]
  Actions --> Verification["Per-action verification predicates"]
  Ledger --> Recovery["Crash recovery & idempotency"]
  Verification --> Recovery
  Routing --> Integration["Integrated chat / agent / voice"]
  Memory --> Integration
  Recovery --> Integration
  Integration --> E2E["Real Windows + Qwen end-to-end acceptance"]
  E2E --> Release["Release gate"]
  Identity["Trusted original-document identity decision"] --> Verification
~~~

The graph is **candidate dependency structure**, to refine in JRV-006. Not all items are mandatory for the first release; scope selection is a gate.

## 11. Unknowns that require targeted investigation

1. Exact pinned \`vendor/openjarvis\` interfaces and license subcomponents beyond the wrapper references (the Git submodule tree wasn't exhaustively inspected in this audit).
2. Whether an existing upstream memory/store module could be reused without hidden network or privacy implications.
3. Real Windows 10/11 compatibility and operator machine specifications.
4. First-run download, installation footprint and package integrity in the user's target environment.
5. Quantitative Qwen 2B/4B instruction-following, tool-use reliability and recovery under A3 feedback on the target environment.
6. A trusted identity proof mechanism for original documents under a defined threat model.
7. Voice wake/STT/TTS performance and acceptable latency for Portuguese real-world conditions.
8. Correct operational retention/encryption/backup of durable records and auditable side effects.
9. User experience acceptance and which integrations Issa values enough for a first scoped release.
10. A4 end-to-end acceptance (currently not authorized).

**Do not invent missing answers.** Each is either a design decision or a separately authorized experiment/audit.

## 12. Exit criteria, findings and next action

**Completed for JRV-005 v1.0:** pinned GitHub HEAD and CI; full tracked path inventory; inspected product entrypoints; ten-module mapping; 33-UC mapping; 10-CT mapping; key test and lab coverage; identified core integration gap; preliminary risk/dependency analysis.

**Not a full security certification:** selected source/tests were inspected, not all repository files/vendor internals; the audit did not execute tests or real model/hardware scenarios. All target architecture remains subject to operator review.

**Most material finding:** A1/A2/A3 exist as a tested opt-in Python core, while ordinary chat, voice and agent CLI routes are separate. The product needs a unified, user-facing execution design **and explicit release scope**, not merely another batch of isolated agent features.

**Next:** JRV-006 — graded gap matrix, cross-system dependencies, risks and prioritization, with clear distinction between mandatory first-release requirements and optional/future capabilities. Afterwards JRV-007 roadmap/release gates and explicit operator approval.
