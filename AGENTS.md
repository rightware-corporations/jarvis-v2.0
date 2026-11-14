# RIGHTWARE JARVIS v2.0 — agent instructions
- **Branch strategy:** three long-lived branches: `main` (approved releases), `develop` (authoritative day-to-day engineering), `demo/issa-20261111` (temporary demonstration). Read `docs/BRANCH_STRATEGY.md` for verified consolidation status and exceptions. Do not open a new feature branch for routine engineering without an explicit isolation need and cleanup plan.
- **Continuity:** before resuming a task, read `docs/HANDOFF.md` and inspect the current remote HEAD/CI. Before every substantial user-visible engineering progress output, append a factual dated HANDOFF checkpoint, commit/push it and verify the remote HEAD. State the checkpoint SHA with the progress. If push fails, say the update is NOT persisted. No secrets, private conversations or personal data in the public repository.
- Product: independent local-first JARVIS, no mandatory paid LLM API or Claude runtime; foundation remains OpenJarvis + Ollama + Qwen.
- `vendor/openjarvis` is pinned by Git submodule/gitlink and `rightware/runtime.py`; do not silently edit the vendor or change the pin.
- RIGHTWARE product code belongs in `rightware/`, configuration in `configs/`, experimental labs in `labs/`, evidence and continuity in `docs/`.
- Never call unit/FAKE tests real Qwen, voice, Windows or full task-acceptance evidence. Real inference requires explicit prior authorization.
- `main` promotion needs its own reviewed and approved release PR. Do not merge `develop` into `main` automatically. Do not delete temporary branches holding unique unmerged work.
- Windows actions, browser effects and filesystem writes require their own capability authorization and verified outcomes; never grant generic shell access.
- Never commit credentials, model weights, conversation transcripts or `.runtime/`; keep implementation focused on usable MVP and audited security.
