# RIGHTWARE JARVIS v2.0 — R2-D: structured-output contract for the product

**Date:** 2026-11-11. **Status:** specification only. Nothing is implemented in `rightware/`. **No new inference.** It extends contract items C6 and C8 of `R2_RUNTIME_INTEGRATION_CONTRACT.md`. No new framework: OpenJarvis + Ollama + Qwen stay.

Labels: **FACTO** (code or evidence), **INFERÊNCIA**, **NOT VERIFIED**.

## 1. Why

**FACTO:** run 43066548100 had correct content (7/7 facts, correct EVOLUÇÃO, ORACLE PASS) but failed V2 on finding-line syntax. In all three CPU runs the model never wrote `- [TIPO] campo:`.

**Principle:** structure that code checks must be produced by code. The model supplies typed values; RIGHTWARE code renders the Markdown and the user-facing text.

## 2. What the pinned stack offers (FACTO, verified in `vendor/openjarvis` @ `f21d902`)

| Mechanism | Status |
|---|---|
| `ResponseFormat(type="json_schema", schema=…)` (`engine/_stubs.py:39`) | Declared |
| `OllamaEngine.generate` (`engine/ollama.py:184-191`) | Maps **any** `response_format`, including `json_schema`, to `payload["format"] = "json"`. **The schema is dropped**: only generic JSON mode reaches Ollama |
| Ollama server 0.40.15 `format: <JSON schema object>` | Supported by the Ollama API (INFERÊNCIA from Ollama documentation; **NOT VERIFIED** in this repository with `qwen3.5:4b`) |
| Tool calling (`function_calling`, already used) | Arguments arrive as JSON; the policy validates names and types (`w02lab/policy.py` `SCHEMAS`, `validate`). Nested schemas are not validated today |

**Consequence:** through the pinned engine, schema-constrained decoding is not available. Editing the submodule is not allowed. Two compliant routes exist:
- **(A) Typed tool arguments (recommended first).** The model already emits JSON tool arguments. The product defines the tool parameters as a JSON Schema and validates them in RIGHTWARE code, fail-closed. Nothing changes in the engine.
- **(B) Direct schema-constrained call.** A RIGHTWARE-owned call to the local Ollama `/api/chat` with `format: <schema>`, outside the OpenJarvis engine, only for a final «compose» step. It needs a separate authorisation and its own real-model check (**NOT VERIFIED**).

## 3. Product schemas (route A)

All strings are bounded and enumerations are closed. `additionalProperties: false` everywhere. RIGHTWARE code validates before any use and rejects the whole call on any violation (fail-closed, as C2/C3).

```json
{
  "report_fact": {"type": "object", "additionalProperties": false,
    "required": ["field", "value", "state", "source"],
    "properties": {
      "field":  {"type": "string", "maxLength": 40},
      "value":  {"type": "string", "maxLength": 200},
      "state":  {"enum": ["estimado", "aprovado", "nenhum"]},
      "source": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,58}\\.(md|txt)$"}}},
  "finding": {"type": "object", "additionalProperties": false,
    "required": ["type", "field", "description", "evidence"],
    "properties": {
      "type":  {"enum": ["CONTRADICAO", "EVOLUCAO", "INCONSISTENCIA_TEMPORAL", "EM_FALTA", "SEM_ACHADOS"]},
      "field": {"type": "string", "maxLength": 40},
      "description": {"type": "string", "maxLength": 300},
      "evidence": {"type": "array", "maxItems": 4, "items": {"$ref": "#/report_fact"}}}},
  "tool_result": {"type": "object", "additionalProperties": false,
    "required": ["tool", "outcome", "detail"],
    "properties": {
      "tool": {"type": "string"},
      "outcome": {"enum": ["OK", "REFUSED", "FAILED", "NOT_VERIFIED"]},
      "detail": {"type": "string", "maxLength": 300}}},
  "completion": {"enum": ["TASK_COMPLETED", "NOT_PERSISTED", "NOT_VERIFIED", "VERIFICATION_FAILED", "REFUSED", "NO_PATH"]}
}
```

- **Facts and states:** `report_fact`. The `source` must be a file the tool actually delivered in this session; code checks that against the read log (C7).
- **Findings and categories:** `finding`. Code derives date order (C8, as in `chronology_r2`) and rejects an `INCONSISTENCIA_TEMPORAL` whose dates are not actually impossible. It does not invent the finding.
- **Tool results:** produced by RIGHTWARE code from the real outcome (as `ActionResult`), never by the model.
- **Completion:** set only by code from the verified outcome (C6). The model's prose cannot set it.
- **Rendering:** a pure function `render_report(facts, findings, sources) -> Markdown` in RIGHTWARE code. The same typed data gives byte-identical Markdown. User-facing text such as `describe()` follows the same rule.

## 4. Lab protocol vs product protocol (kept separate)

| | Lab (WORK-04 rev.1 / R2) | Product |
|---|---|---|
| Report format | Markdown written by the model; **this is part of the benchmark task**. Criteria frozen | Typed arguments; Markdown rendered by code |
| Evaluators | V2, ORACLE, hidden truth (synthetic) | None of these. Schema validation, provenance against the read log, deterministic checks, user confirmation for effects |
| Feedback | Rule names, fixed hints, own-text lint and chronology (R2) | Schema-validation errors (field path and constraint), never hidden answers |
| Changing it | A new, separately authorised experiment; never retro-scored | Product spec and tests first; no `main`/`develop` change without review |

A structured-output variant of the benchmark would be a **new** experiment («R3-structured»). It must not be reported as a WORK-04 or R2 pass.

## 5. Risks and checks before adoption

- **Tool-argument size.** Nested arrays raise token use. The 12-call and `num_ctx` 8192 limits apply. **NOT VERIFIED** for Qwen3.5:4b.
- **Schema-valid but wrong.** A schema guarantees shape, not truth. Provenance checks (C7) and deterministic checks (C8) remain mandatory.
- **Route B is NOT VERIFIED.** It needs one authorised local test showing that `format: <schema>` with this model and Ollama version produces conforming output.
- **First product tool:** read-only. For example, «resumir documentos de uma pasta escolhida», returning `report_fact[]`/`finding[]` rendered by code. It goes through C1–C11. Effects stay limited to `WindowsActions` with confirmation.
