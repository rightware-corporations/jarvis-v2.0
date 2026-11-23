# Validation — foundation

Executed in this implementation session on Linux, Python 3.12.14:

| Check | Result |
|---|---|
| Exact upstream f21d902f4d3bd7f0f3f138f1a4613019a394b549 | PASS |
| No tracked upstream edits | PASS |
| uv sync --frozen --no-dev at pinned revision | PASS, 59 installed packages |
| python jarvis.py setup (submodule + dependency/config path) | PASS |
| Upstream CLI --help | PASS |
| Upstream loads RIGHTWARE configuration | PASS: ollama, local loopback, simple |
| Anthropic Python SDK | Not installed |
| Four targeted launcher unit tests | PASS |
| Real inference through new wrapper | NOT RUN: no Ollama service/model set up in this session |
| Voice, Windows actions, GUI, cancellation | NOT RUN |
| Remote GitHub CI | Consult current workflow run; local PASS is not remote PASS |

The previous 06/11/2026 inference experiment is historical evidence only. This setup uses the upstream lockfile; rerun the short real-model conversation before claiming the new foundation works end to end. No large test suite was run. No hardware or two-day delivery guarantee is inferred from these checks.
