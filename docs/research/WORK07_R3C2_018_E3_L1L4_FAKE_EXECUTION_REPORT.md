# WORK-07 R3-C2-018 — E3 + L1–L4: execution report (synthetic contracts only)

**Data:** 2026-11-13 (Africa/Maputo)  
**Author / provenance:** ChatGPT, under the operator's approval of R3-C2-014 FAKE/test-only experiments. This code was authored directly by ChatGPT rather than Claude Code, to execute the already-authorized limited laboratory stage.  
**Baseline:** `05ad0243bf8f0c08be8218aa669ad3ddadbb9f85`.  
**Test-only commits:** `46b2a3e752dfa7f0b405034f2aa196bdc75cf697` (lab contract), `092b02edb75568d64ea87814b8f798481acb3e59` (27 tests).  
**Product changes:** NONE. `rightware/`, `vendor/`, `_compose()`, `AgentSession.run()`, security/policy/quotas, main, pin and historical evidence unchanged. No Qwen/Ollama/GPU, browser access or external side effects.

## 1. Actual execution

**CI evidence:** [RIGHTWARE WORK-05 product agent tests — run 43466492940](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43466492940), HEAD `092b02ed`, outcome `success`.

- In plain Python, the suite reported **311 tests, OK with 137 skipped** (OpenJarvis-dependent tests intentionally excluded when packages unavailable). The new 27 lab tests **all ran and passed** in plain Python.
- In the pinned OpenJarvis virtual environment, the suite reported **311 tests, OK, no skips**. Each of the 27 new tests logged `... ok`.
- CI foundation Ubuntu job was also `success` in workflow run `43466493010` at observation; a second foundation run `43466504125` was still `in_progress` and cannot be called green until completed.
- The test suite uses `unittest discover -s tests -v` both with plain Python and pinned OpenJarvis venv. No test was inferred from a status badge alone: product-job logs were inspected.

## 2. Artifacts and exact meaning

- `labs/work07_r3c2/contracts_e3_l1l4.py` defines **test-only** `Objective`, `Contract`, `Receipt`, `Assessment`, `protect_trusted` and `assess`. It does not integrate with the runtime and uses synthesized `task_id/run_id/call_id/outcome_id` for fixture inputs.
- `tests/test_work07_r3c2_e3_l1l4.py`: 12 E3 trusted-contract/oracle checks plus 3 L1, 5 L2, 3 L3 and 4 L4 synthetic receipt checks = **27 tests**.
- Gold oracle `docs/research/WORK07_R3C2_017_E3_GOLD_ORACLE.md` and case matrix `docs/research/WORK07_R3C2_014_E3_L1L4_TEST_CONTRACT.md` remain human-authored expected outcomes.

| Family | Tests passing | What is established | What is NOT established |
|---|---:|---|---|
| E3 | 12/12 | Trusted fixture objectives remain represented; T3 conflicting proposal cannot replace T1; empty/ambiguous contract is UNKNOWN | **No extraction of mandatory objectives from natural-language instructions**, including 12 sentences |
| L1 | 3/3 | Missing positive synthetic receipts prevent PASS | Real tool-to-objective binding |
| L2 | 5/5 | Status, synthetic identity/digest and challenge markers can reject known insufficiency | Real document-type verification, semantic original identity, redirect provenance |
| L3 | 3/3 | Missing/REFUSED/NOT_EXECUTED and absent synthetic identifiers are rejected | Strong authenticated receipt IDs from JARVIS execution |
| L4 | 4/4 | Mismatched synthetic task/run/hash scope/verifier version are rejected | Production emission of trustworthy run/version correlation |

**The expression `PASS_OPERATIONAL_ONLY` is strictly the verdict of this synthetic contract checker; it MUST NOT be read as completion verification by the JARVIS product.**

## 3. Material limitations discovered by code review

1. **E3 remains open:** the supplied objectives are annotated by the test author, not extracted by a parser or model. Results **cannot** be cited as measured recall on Portuguese free-form text.
2. **T1 authority is conditional:** the fixture calls a contract `trusted=True`; the code does not authenticate the operator or origin of that contract.
3. **Only positive mandatory objectives are actually enforced by `assess`:** `forbidden`, `after` and `condition` are stored in the test schema but are **not yet checked against a full execution history**. The E3 tests examine schema retention rather than enforcement of these dependencies.
4. **Receipts are simulated:** `receipt()` fabricates synthetic IDs and positive execution flags *inside the controlled test*. L3 checks that empty or false values are rejected, but does **not** prove that a malicious/compromised emitter cannot fabricate a plausible receipt.
5. **Document identity is a declared fixture field:** it is not derived from verified document contents, validated redirect chain or trusted issuer. HTTP 200 + a field named `identity` is not externally proven authenticity.
6. **Hashes are synthetic text markers** (`hash-1`, etc.), not actual SHA-256 digests. Scope mismatch and version mismatch logic are tested, not cryptographic integrity.
7. **No live task correlation:** existing `ToolOutcome`, `PublicBrowser.events` and `TaskTrace` do not yet emit the complete task/run/call/outcome correlation chain required to promote G2/G3 evidence. A new runtime adapter would need separate authorization.
8. **No negative mutation coverage for E3/L1–L4** in this phase; do not repeat the prior E4 unbounded mutant OOM.
9. **No general completion controller:** `_compose()` remains unchanged and still can emit `ANSWERED_WITH_SOURCES` on an incomplete real task.

## 4. Decision gate

**Measured outcome:** `PASS` for 27/27 deterministic contract-level scenarios.  
**E3 extraction objective:** **NOT DEMONSTRATED** (requires a real extraction mechanism and independent gold comparison).  
**L1–L4 full real-runtime provenance:** **NOT DEMONSTRATED** (requires stable identity/correlation from runtime plus relevant verifiers).  
**Production readiness:** **NOT APPROVED / NOT SUPPORTED BY THESE TESTS**.

**Recommended next phase:** design a narrow-class objective extractor with explicit UNKNOWN fallback, and independently audit the minimal runtime-to-receipt correlation adapter. Validate these with existing R3-C1 synthetic browser and real `ToolOutcome` objects, but do not alter product until a separate explicit decision. A follow-up should first assess whether trusted presets/explicit checklists are sufficient for the first product milestone instead of pursuing unrestricted NLP extraction.

## 5. Continuity and constraints

HANDOFF-FIRST applies. Retain prior FAIL/BLOCKED from Qwen and separate E1/E4 results. The Claude Code agent was not invoked by this commit. CI confirmation belongs to the specific SHA/workflow, never to future changes. No continuation outside test-only E3/L1–L4 or automatic production implementation.
