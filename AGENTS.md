# RIGHTWARE JARVIS v2.0 — Repository engineering rules

- Product: independent local-first Portuguese personal assistant; no mandatory paid LLM API or Claude runtime.
- Protect main and develop. Use isolated feature branches and Draft PR review; never merge, force-push, retarget a PR, or change protected branches without explicit authorization. Before writing, read current remote branch SHA and avoid another agent's active branch.
- vendor/openjarvis is a pinned Git submodule (rightware/runtime.py and Git gitlink). Do not edit or silently change the upstream pin.
- RIGHTWARE product code lives under rightware/, configuration under configs/, lab experiments under labs/, evidence and continuity under docs/.
- Read docs/HANDOFF.md, docs/WORK05_CONTINUITY.md (when present), current open PR and recent CI before starting.
- **After each completed engineering checkpoint, append to docs/HANDOFF.md** the exact branch/HEAD, changed files, tested commands/CI run and outcome, remaining risks, next gate. Do not rewrite, truncate, or mislabel historical evidence. Also update the active Draft PR. Partial work is NOT a tested pass.
- Never claim unit tests, configuration checks or CI compilation prove real-model inference, actual voice, real Windows target acceptance or cognitive success. No Qwen/GPU/real inference without fresh explicit authorization.
- Windows effects require allowlisted actions, explicit session authorization and human per-action confirmation. Tool data is untrusted; model prose cannot certify execution.
- New tool integration must use closed names and schema, approval checked again at execution, bounded quotas, cancellation, trustworthy result check and sanitized audit. No generic shell or arbitrary file/network operations.
- Do not commit credentials, model weights, personal conversations, chat transcripts, user data, local runtime state, or raw unredacted tool output into this public repo.
- Keep changes limited to a usable MVP and reviewable feature slices. Shared Intelligence is a separate project and must not be merged in without scoped integration and authorization.
