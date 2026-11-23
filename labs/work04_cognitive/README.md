# WORK-04 lab — cognitive robustness and semantic validation (EXPERIMENTAL)

Separate from WORK-02. It imports the WORK-02 sandbox, fail-closed policy, tools and open-audit **read-only**: no WORK-02 file is modified, and the WORK-03 Gate 5 evidence is untouched. The specification and the pre-registered criteria are in `docs/research/WORK04_COGNITIVE_ROBUSTNESS_SPEC.md`; the criteria are also constants in `w04lab/assess.py`.

| Path | Content |
|---|---|
| `w04lab/scenarios.py` | 7 families (EVOL, CONTRA, TEMPORAL, MISSING, CONSISTENT, RECOVERY, HOSTILE). Per seed it varies: 4 layouts, file names, 5 request phrasings, a distractor document and 5 injection variants |
| `w04lab/verifier_v2.py` | Primary evaluator: structured report, provenance per row, missing fields, findings set, negation-aware narrative, exact sources, hostile content |
| `w04lab/oracle.py` | Independent evaluator: whole-text sentences, its own number/date/field/negation logic, sentence-level provenance. Never parses the table |
| `w04lab/harness.py` | Real OrchestratorAgent, transient-read fault (RECOVERY), `verify_report` backed by V2 (categories only), `_v2` correction rule, false-success detection |
| `w04lab/assess.py` | Fixed thresholds, all-pairs cross-run rejection (V2 and factual), hard gates |
| `w04lab/factual.py` | Spec rev. 1 §5.1: name-agnostic cross-run factual compatibility (file roles A/B/D, facts, findings, polarity, forbidden content) |
| `w04lab/human_review.py`, `build_review_packet.py` | Spec rev. 1 §5.2: fixed blind sample (one per family) and reviewer packet without verdicts or truth; the key is written outside the packet |
| `w04lab/fake_reports.py`, `fake_engines.py` | FAKE honest and adversarial reports and agents (tests only) |
| `run_real.py` | Single benchmark entry: in-process digest check, 35 runs, evidence, ZIP; `--fake` for script validation |
| `tests/` | `test_w04_fake.py` (rules, harness, criteria) and `test_w04_workflow.py` |

FAKE tests (no model):

```bash
cd labs/work04_cognitive/tests && ../../../vendor/openjarvis/.venv/bin/python -m unittest -v test_w04_fake test_w04_workflow
```

The real benchmark is **not authorized yet**. It runs only through `.github/workflows/work04-cognitive.yml`, which is dispatch-only and inert until registered on `main`. It needs `run_benchmark=yes` and `AUTORIZO-WORK04-BENCHMARK`.
