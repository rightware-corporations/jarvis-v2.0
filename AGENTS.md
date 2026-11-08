# RIGHTWARE Jarvis v2
- Product: independent Jarvis, no mandatory paid LLM API or Claude runtime.
- Only main and develop. Work on develop; main is reviewed, not automatically release-ready.
- vendor/openjarvis is a Git submodule pinned in rightware/runtime.py and Git's gitlink. Do not edit it or update the pin silently.
- RIGHTWARE code lives in rightware/. Configurations in configs/, evidence and continuity in docs/.
- Read docs/HANDOFF.md before continuing. Never call configuration/unit tests real-model, voice or Windows acceptance.
- No Windows effects are enabled by the initial launcher. Explicit task authorization and actual tool outcomes are required when adding them.
- Never commit credentials, model weights, personal conversations or .runtime/.
- Keep work focused on a usable MVP; no broad refactor or training before model comparison.
