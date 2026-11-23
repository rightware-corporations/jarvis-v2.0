# RIGHTWARE — JARVIS DO ISSA — WORK-03: GitHub Actions CPU for the real WORK-02 proof

**Date:** 09/11/2026. **Executor:** Claude Code. **Status:** **WORK03_PREPARED — ACTIVATION BLOCKED (decision required)**. QWEN REAL: **NOT RUN**.

Labels used:
- **FACTO** = observed or measured;
- **INFERÊNCIA** = engineering estimate;
- **NÃO VERIFICADO** = not checked.

Result labels: `FAKE PASS` / `QWEN REAL PASS` / `QWEN REAL FAIL` / `ENVIRONMENT BLOCKED` / `NOT RUN`.

## 1. Repository audit (FACTO)

| Item | Value |
|---|---|
| `develop` at start | `85b0a8e50545bced665d2a890354ccdafac40e50` (= reference HEAD); local fast-forward from `fa9faa9`, no divergence |
| Default branch | `main` (remote `HEAD` → `main`) at `9198e1a` — **contains only `README.md`**, no `.github/` |
| Workflows | `develop`: `.github/workflows/foundation.yml` only. API `list_workflows`: 1 workflow (`RIGHTWARE foundation`, registered through its push runs on `develop`) |
| Pin | `f21d902f4d3bd7f0f3f138f1a4613019a394b549`, unchanged |
| Changes since WORK-02 publication | `2546356`, `a74cb1f`, `d172f17`, `85b0a8e`: docs only (K04 Kaggle blocker, GPU options, Lightning AI unavailable, CPU Actions proposal). Lab code unchanged since `fa9faa9` |
| Documents read | HANDOFF (all addenda), WORK-01, WORK-02 report, K04 options, ARCHITECTURE BRIEF, lab README, `run_real.py`, `foundation.yml` |

**Divergences found:** none against the code. The K04 document still recommends Lightning AI first, but the later HANDOFF addendum records that sign-ups are disabled. The later addendum prevails; nothing was rewritten.

## 2. Phase B — `workflow_dispatch` (the blocker)

- **FACTO (GitHub documentation, "Events that trigger workflows → workflow_dispatch"):** to trigger `workflow_dispatch`, the workflow file must exist on the **default branch**. The run itself can target another ref (e.g. `develop`); the definition then comes from that ref.
- **FACTO:** `main` has no workflow file. A workflow on `develop` that declares only `workflow_dispatch` is therefore **inert**:
  - it does not appear in the Actions UI;
  - the dispatch API cannot target it;
  - push, PR and schedule do not run it.
- **Consequence:** the workflow can be prepared and published on `develop` safely, but **real activation is BLOCKED** until one of the options below is approved. I did not modify `main`, add an alternative trigger or work around this.

| Option | What changes | Risk | Recommendation |
|---|---|---|---|
| **A** | One commit to `main` adding **only** `.github/workflows/work03-cpu-agent.yml` (same file). Then dispatch from Actions → *Run workflow* → branch `develop`, `sha=<commit>` | `main` gets one file. No code or other workflow moves to `main`. Dispatch still requires write access | **Recommended**: smallest and auditable; `main` stays otherwise untouched |
| B | Change the repository default branch to `develop` | PR base defaults and repo semantics change; reversible in Settings | Acceptable alternative; broader effect than A |
| C | Add `push: tags: ['work03-run-*']` on `develop` (trigger by pushing a tag) | Alternative automatic trigger; anyone with push could start it; adds tags | Needs explicit approval; weaker control than A |
| D | Temporary `push` trigger with a path filter, run once, then remove | Runs on push (forbidden by this mission); easy to misfire | Not recommended |

## 3. Phase A — feasibility on a standard runner

**Runner (FACTO, GitHub docs as cited in the HANDOFF):** `ubuntu-24.04`, 4 vCPU, 16 GB RAM, 14 GB SSD, no GPU, free for public repositories, job limit 6 h.

**Local measurement in a similar machine (FACTO):** 4 vCPU, `MemTotal` 15 GiB, so the gate threshold is ≥ 14 GiB.

| Resource | Estimate | Basis |
|---|---|---|
| Model RAM | ~3.5–4.5 GB for `qwen3.5:4b` at `num_ctx` 8192, plus ~0.5 GB Python | K03B **FACTO**: 3,140,495,604 bytes loaded at ctx 4096 (GPU). The 8192 KV increase is an **INFERÊNCIA** (≤ ~1.2 GB for a dense 4B; Qwen3.5 hybrid layers likely less). Comfortable under 16 GB |
| Disk peak | ~8–11 GB | **FACTO**: Ollama archive 1,543,547,172 B (SHA verified earlier); venv core ~0.4 GB measured; upstream source 111 MB. **NÃO VERIFICADO**: extracted Ollama size (bundles GPU libraries, deleted on CPU) and model blob size (~3.4 GB expected). The workflow deletes the archive after extraction and the GPU libraries before the model pull. Gate 1 requires ≥ 15 GiB free and, if short, removes unused preinstalled SDKs on the ephemeral runner |
| CPU inference time | ~3–8 min per WORK-02 run → ~40–105 min for 13 runs, plus ~10–15 min setup | **INFERÊNCIA** (4B Q4 on 4 vCPU: roughly 20–60 tok/s prompt and 4–10 tok/s generation; ~6 model calls per run; report dominates output; `think=false`). **Not measured**: GATE 3 records the first real latency |
| Job time | Under the 345-min job timeout | Worst case: 13 × 1,200 s run limit = 260 min plus setup; fits under 6 h |
| Timeouts | Engine 600 s per request; run 1,200 s; tool 30 s (lab tools are fast file operations) | The previous defaults (180 s / 300 s) would very likely cause spurious AMBIENTE failures on CPU. The new `--engine-timeout` changes environment limits only, not acceptance criteria |
| Python | 3.12 via `setup-python` | Lockfile `>=3.10,<3.14` (FACTO); 3.13 used locally, 3.13.16 on Kaggle |
| Rust | Not required | **FACTO**: `openjarvis_rust` is absent in the lab venv and all lab tests ran with the real Orchestrator. Gate 1 only records `rustc` |
| Ollama ↔ model ↔ libs | Ollama 0.40.15 + `qwen3.5:4b` + pin `f21d902` | **FACTO** on Kaggle Linux GPU (K02/K03). CPU backend of the same binary: **INFERÊNCIA** |

**Download and permission risks:**
- Ollama comes from the official GitHub release, with the archive SHA-256 verified and no `curl | sh`.
- The model comes from `registry.ollama.ai`; its digest is recorded, but there is **no trusted expected digest yet** (K03B recorded none) → **NÃO VERIFICADO**.
- The three actions are pinned by commit SHA.
- `uv` is pinned to `0.11.32` from PyPI.
- `sudo` is used only to delete preinstalled SDKs on the ephemeral runner when disk is short.

**Verdict:** **plausible but unproven**. RAM and job time look sufficient. The real unknowns are CPU latency per step and Qwen tool-calling quality, and only GATES 3–5 can answer them. Nominal RAM alone is not taken as proof.

## 4. Workflow prepared on `develop` (Phase C)

The workflow is `.github/workflows/work03-cpu-agent.yml`; `actionlint` 1.7.12 reports 0 findings.

**Trigger and access**
- Trigger is `workflow_dispatch` only. Inputs: `sha` (40 hex), `up_to_gate` (2–5, default 3), `gate5_authorization`.
- `permissions: contents: read`; no secrets; checkout with `persist-credentials: false`.
- Inputs are only read through `env:` (no `${{ }}` inside shell).
- `concurrency` is a single group; `timeout-minutes: 345`.

**Gates and steps**
- **GATE 0a:** validates the inputs. GATE 5 needs `AUTORIZO-WORK03-GATE5`.
- **Checkout:** explicit `ref: inputs.sha`, recursive submodules.
- **GATE 0:** `HEAD == sha`, gitlink and submodule == pin, both trees clean, lab files present.
- **GATE 1:** CPU, RAM ≥ 14 GiB, free disk ≥ 15 GiB, Python and Rust versions recorded.
- **Install:** `uv sync --frozen --no-dev` of the pinned OpenJarvis core; imports `OrchestratorAgent`.
- **GATE 2:** Ollama 0.40.15 archive SHA-256 check, GPU libs removed, `serve` with `OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1`, version check, socket must be loopback only.
- **GATE 3:** `ollama pull qwen3.5:4b`, digest from `/api/tags`, one real generation (`think=false`, ctx 8192), `/api/ps`.
- **GATE 4:** `gate4_tool_smoke.py`. One real `list_workspace` call by the model through the Orchestrator; write not authorized.
- **GATE 5:** `run_real.py --expect-sha <sha> --n 10 --security-n 3 --allow-cpu --timeout 1200 --engine-timeout 600`. Criteria unchanged.

**Always-run steps**
- Classification: every gate gets one of the five labels, and «CI/Ollama success is not agent success».
- Server log trimmed to its tail; Ollama stopped.
- Artifact `work03-evidence-<run_id>` uploaded (30 days).

## 5. Gate execution plan (after activation)

1. **Dispatch 1:** `up_to_gate=3`. Proves the environment, Ollama and real generation, and measures first latency, RAM and disk.
2. **Dispatch 2:** `up_to_gate=4`. Proves one real tool call by the model.
3. **Dispatch 3:** `up_to_gate=5` plus `AUTORIZO-WORK03-GATE5`. Full WORK-02: ≥ 8/10, 0 security violations, varied inputs, own-facts match plus cross-run rejection, and model-made read×2/write/verify calls.

Stop and report after any `ENVIRONMENT BLOCKED` or `QWEN REAL FAIL`. Never lower N or the criteria.

## 6. Evidence policy (Phase E)

The artifact contains:
- `gates.jsonl`, `work03-summary.json` (gate table and overall label) and the step summary in the run page;
- `environment.txt`, `ollama-libs.txt`, `ollama-listen.txt`, `ollama-tags.json` (digest), `ollama-ps.json`;
- `gate3-generate.json`, `gate4.json`, and the tail of `ollama-server.tail.log`;
- for GATE 5, `work02-real/`: `manifest.json`, `inputs.json`, `runs.jsonl`, `summary.json`, `SUMMARY.md`, `reports/` and the ZIP.

It is uploaded even when a gate fails. There is no environment dump, the data is synthetic only, and no conversation text is logged.

Only `GATE 5 = QWEN REAL PASS` means WORK-02 passed. A green workflow, a working Ollama or a passing GATE 3/4 are **not** agent success.

## 7. Tests actually run (this session)

| Test | Result |
|---|---|
| Lab suite (WORK-02 S0–S11 + variability + 16 WORK-03 static/local tests) | **59 PASS — FAKE/static** |
| RIGHTWARE suite | 56 OK |
| `actionlint` 1.7.12 on both workflows | 0 findings |
| Local dry-run of the real GATE 0a/0/1 scripts, extracted from the YAML | PASS (4 vCPU, 15 GiB, 29 GiB free); bad SHA and GATE 5 without authorization refused (exit 1) |
| GATE 4 script `--fake` | FAKE PASS |
| GATES 2–5 | **NOT RUN.** This session cannot run the downloaded Ollama binary or reach the model registry, and the workflow is not dispatchable |

**Defects found and fixed during preparation:**
- the loopback check inside a `!` pipeline did not fail under `set -e`;
- the classification would have hidden a GATE 4 model failure;
- two over-broad tests: a comment matched «ollama», and the WORK-02 scope check broke with later authorized work. The scope check is now pinned to the immutable range `7079e18..fa9faa9`.

## 8. Decisions for the operator / CEO

1. **Activation (required):** option A (recommended), B, C or D from §2.
2. **Budget of runner time:** three dispatches (gates 3, 4, then 5). Free for public repos; nothing paid is used.
3. **Model digest:** accept the first recorded `qwen3.5:4b` digest as the reference for later runs (recommended) or supply a trusted one.
4. **Interpretation:** a CPU `QWEN REAL PASS` proves multi-tool capability, not Windows or GPU performance (unchanged from K04).
