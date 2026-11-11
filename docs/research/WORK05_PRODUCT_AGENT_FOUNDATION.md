# RIGHTWARE JARVIS — WORK-05-A Product Agent Foundation

**Date:** 2026-11-11. **Classification:** ACTIVE IMPLEMENTATION in an isolated feature branch; not production-ready.
**Base:** WORK-04 R2 handoff at dd5dbd6. Original benchmark evidence and verifiers are unchanged.

## Objective

Provide an auditable boundary for tool calls proposed by a future OpenJarvis/Qwen agent. Never import benchmark ORACLE, truth fixtures, or scoring hints into the product.

Desired sequence:

1. Portuguese text/voice user instruction.
2. Local Qwen and pinned OpenJarvis propose a strictly typed tool call.
3. RIGHTWARE authorizes the entire batch (closed registry, schema, quotas, deadline and session permission).
4. RIGHTWARE issues single-use tickets bound to hashes of canonical arguments.
5. An independent execution gate checks the request again and invokes the allowlisted tool.
6. Actual tool outcomes determine task truth; read content remains untrusted.

**Only steps 3–6 are implemented by WORK-05-A**, with deterministic callers. Steps 1–2 require a separate adapter. No Qwen inference was executed.

## Implemented

- **rightware/agent_tools.py**: closed registry with read_document and open_windows_action, exact schema, at most two calls per batch, fail-closed preflight, deadline, cancellation, SHA-256-bound single-use approval, independent execution gate.
- **Scoped read:** simple .md/.txt names only, explicit trusted directory, 20,000-byte limit, no links/reparse points, inode and size/mtime recheck. A successful read verifies the file bytes and digest, **not factual correctness**.
- **Untrusted result:** unpredictable begin/end frame markers; matching end marker neutralized. Future adapter must pass these as tool data, never as system/user instructions.
- **Windows effects:** reuse the existing WindowsActions.run, fixed allowlist, session flag, per-action confirmation and process check. No shell or arbitrary executable.
- **Audit:** caller-supplied local append-only path with tool id, hash of arguments and outcome; no conversation content. If audit cannot be written before a call, no effect is executed.
- **tests/test_agent_tools.py**: deterministic positive/negative/adversarial tests for malformed calls, swaps/replay, quota, cancellation, symlink, oversized content, forged marker, unwritable audit and non-leakage.
- **.github/workflows/work05-product.yml**: Python compilation and product unit tests. No Ollama, GPU, Qwen, browser network or real desktop effects.

## Remaining risks / status

| Capability | Status |
|---|---|
| Product tool authorization / replay rejection | Implemented; deterministic tests |
| Scoped read of file bytes | Implemented; not a fact checker |
| Windows app actions | Existing implementation reused; recipient Windows acceptance still pending |
| OpenJarvis function-call adapter | **NOT IMPLEMENTED** |
| Qwen independent selection of correct tool | **NOT VERIFIED** |
| Public web navigation | **NOT IMPLEMENTED**; first audit SSRF, DNS, redirects, TLS, authentication and size limits |
| Portuguese voice/dictation using same tool core | **NOT IMPLEMENTED**; existing voice remains SimpleAgent plus deterministic actions |
| Durable task ledger and recovery | **PLANNED** |
| Shared Intelligence (Mem0 / pgvector) | Independent project; **NOT CONNECTED** |
| Real-model reliability | **NOT VERIFIED** by unit tests |

Content framing alone does not prove semantic prompt-injection resistance. Windows filesystem checks need real recipient-PC validation. An initially invalid batch is denied as a whole, but a later runtime failure cannot reverse an earlier valid effect.

## Sequential next gates

**WORK-05-B:** inspect pinned OrchestratorAgent and ToolExecutor signatures; build a narrow adapter into AgentToolRuntime. Use fake models first; preserve untrusted source roles and pinned submodule.

**WORK-05-C:** restricted public-site reader / navigation, with authorization and SSRF/redirect/DNS threat model; no authenticated browsing effects by default.

**WORK-05-D:** one explicitly authorized real Qwen vertical slice, with independently checked tool result. One PASS does not mean general reliability.

**WORK-05-E:** converge text, Portuguese voice, dictation, desktop actions and durable task state. Integrate RIGHTWARE Shared Intelligence later through scoped REST/MCP permission checks.

## Continuity

Before and after each engineering checkpoint, append to docs/HANDOFF.md: branch/HEAD, changed files, actual test run IDs and verdicts, risks, and exact next gate. Preserve historical evidence. See docs/WORK05_CONTINUITY.md.
