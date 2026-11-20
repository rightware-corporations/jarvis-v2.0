# WORK-02 — Preflight evidence (09/11/2026, Claude Code cloud session)

| Gate | Observed | Result |
|---|---|---|
| G0.1 remote / branch | `origin = github.com/rightware-corporations/jarvis-v2.0`, branch `develop`, no pending rebase/merge/cherry-pick | PASS |
| G0.1 working tree | `git status --porcelain --untracked-files=all` empty | PASS |
| G0.1 HEAD vs remote | local `c906d7b` was 6 behind; fast-forward `--ff-only` to `6bac396a5c9db65879feccfb064fdb502d814c7e` = `git ls-remote origin refs/heads/develop` | PASS (initial HEAD for this mission: `6bac396a`) |
| G0.2 pin | gitlink `160000 f21d902f4d3bd7f0f3f138f1a4613019a394b549 vendor/openjarvis`; submodule HEAD identical; `status --porcelain` empty | PASS |
| G0.3 documents | `docs/HANDOFF.md` (all addenda) and `docs/research/WORK01_ACTIVE_ASSISTANT_AUDIT.md` read | PASS |
| G0.4 contracts | `JAR-CONF`, `JAR-COG`, `JAR-INFER`, `VEXEL`, `log_transcript_text`, `allow_real_windows_actions`, `Wyzer 182/182`: no artefact in repo or pin (only mentioned by WORK-01 / HANDOFF as not found) | NOT FOUND (recorded, not invented) |
| G0.5 Python / install | Python 3.13.18; disposable venv outside the repo from the pinned lockfile: `uv sync --frozen --no-dev --extra dev` (pytest 9.1.1 from lock); `openjarvis 1.0.5.dev168+gf21d902f`; `OrchestratorAgent` imports | PASS |
| G0.5 baseline | RIGHTWARE `python -m unittest discover -s tests`: 56 OK. Upstream subset (`tests/agents/test_orchestrator.py`, `tests/tools/test_stubs.py`, `tests/security/test_tool_confirmation.py`, `tests/engine/test_ollama.py`, `tests/engine/test_ollama_runtime_options.py`): **172 passed, 0 failed, 0 skipped** (isolated HOME, no pytest cache; submodule still clean) | PASS |
| G0.6 inference | No `ollama`, no `nvidia-smi`, `127.0.0.1:11434` refused; Ubuntu 24.04.5, 4 vCPU, 15 GiB RAM; `registry.ollama.ai` and Hugging Face blocked by this session's proxy | BLOCKED → real inference NOT RUN here |
| G0.7 integrity | No Wyzer layer migrated in this repo (HANDOFF line 23) → no 182/182 check exists | N/A |
