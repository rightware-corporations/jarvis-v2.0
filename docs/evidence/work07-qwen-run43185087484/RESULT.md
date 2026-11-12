# WORK-07 Phase 5 — Request 2 blocked at authorisation

**Historical status: BLOCKED at GATE 0; Qwen never ran.** This is *not* an autonomous research result or a cognitive FAIL.

- GitHub run: https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43185087484
- Run ID: `43185087484`, attempt 1, job `131070154832`
- Original artifact: https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43185087484/artifacts/13928530143
- Artifact ID: `13928530143`; ZIP SHA256 `42e57fad78dd76db09b186546bedcbdb65e48dcf6a51e2e337e27cf481dd2422`
- Approved code SHA: `911d05d97c6b6a583489f705699f491bf69d7e6b`
- Trigger SHA: `8b9371247abb23a026a24ddeb49b15e13e152432` (only `ops/work07_qwen_request.json` changed)
- Fixed plan: `44d9664812cd98648f17691508f4adf9710463ef20354b09ed4d12e144a02d94`
- Request ID 2: **consumed** by a commit/run; do not replay it.

## Cause

The authorisation payload used a `202`-character `authorized_by` string.
The validator limits it to `200` characters and disallows newline/blank text.

The persisted `authorisation.json` is:

```json
{"ok":false,"problems":["authorized_by must be a short single-line text"],"request_id":2}
```

GitHub Actions stopped at GATE 0 with exit code `2`. GATE 1, 2, 3, Ollama model downloads and the inference runner **did not execute**. The acceptance step ran (as designed) to preserve a machine-readable result:

```json
{"operation":"qwen","technical_execution":"ERROR","technical_exit":-1,"verdict":"NO_VERDICT","accepted":false,"required_verdict":"PASS","reasons":["no readable verdict evidence"]}
```

This was an operator-side payload construction mistake; not a defect in Qwen or the browser. The policy stopped it correctly.

## Evidence integrity

Original ZIP digest matches GitHub artifact metadata. Its `SHA256SUMS` verified **4/4** internal files: `acceptance.json`, `authorisation.json`, `gates.jsonl`, and `request.json`.

No model response was produced, no browser events exist, and no inference request may be inferred from the GitHub Actions failure colour.

## Follow-up

This checkpoint adds a boundary regression to the deterministic suite, but that alone does **not** authorize another run. For a future request, validate the complete proposed JSON with the real authorisation function **before** pushing it, including `len(authorized_by) <= 200`.

Next eligible single-use Qwen request: **request_id 3**, with a newly approved exact `develop` HEAD and the unchanged plan digest. **Explicit operator authorization is required**. No auto-rerun or retcon of request 2.
