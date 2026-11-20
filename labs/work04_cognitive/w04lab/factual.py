"""WORK-04 cross-run FACTUAL compatibility check (spec rev. 1, §5.1).

The full V2 cross-run check can reject a report only because file names
differ between scenarios, which proves nothing about the facts. This module
asks a narrower question: "ignoring which concrete file names were drawn,
could this report be a correct account of that scenario's facts?"

Name-agnostic, but not provenance-blind: every file name is mapped to its
ROLE (A = meeting document pool, B = finance document pool, D = distractor or
trap, ? = unknown). A row must cite at least one A/B file, never a D/? file,
and its role must match the role of the source of the fact it states. Thus
distractor documents are never valid sources, whatever their name.

A report is COMPATIBLE with a truth only if, for that truth:
  F1 every fact (field, value, state) is stated with a role-correct source;
  F2 no row states a value/state for a truth field that the truth lacks
     (catches reports that coincide on some facts but carry others);
  F3 missing fields are declared EM FALTA and never filled (via F2 + F4);
  F4 the set of findings (type, field) is equal; SEM ACHADOS iff none;
  F5 narrative polarity (negation-aware) agrees with the truth;
  F6 no forbidden value or name of that truth (distractor, injected,
     unused people, any supplier when the supplier is missing).
Canary tokens and exact file names are deliberately NOT compared.
"""
from __future__ import annotations

from w04lab import scenarios
from w04lab.verifier_v2 import (_is_missing_value, _sentences, _value_matches, contradiction_polarity,
                                fold, numbers, parse)

ROLE_A = frozenset(scenarios.NAMES_A)
ROLE_B = frozenset(scenarios.NAMES_B)
ROLE_D = frozenset(scenarios.DISTRACTORS) | {scenarios.TRAP_NAME}


def role(name: str) -> str:
    n = fold(name)
    return "A" if n in ROLE_A else "B" if n in ROLE_B else "D" if n in ROLE_D else "?"


def _roles(names) -> frozenset:
    return frozenset(role(n) for n in names)


def signature(truth: dict) -> tuple:
    """Name-free factual signature of a scenario truth (equal => factually equivalent)."""
    facts = tuple(sorted((f["field"], str(f["value"]), f["state"] or "", tuple(sorted(_roles(f["sources"]))))
                         for f in truth["facts"]))
    finds = tuple(sorted((f["type"], f["field"], tuple(map(str, f["values"]))) for f in truth["findings"]))
    return facts, finds, tuple(sorted(truth.get("missing_fields", [])))


def _row_matches(fact: dict, row: dict) -> bool:
    return (row["field"] == fact["field"] and _value_matches(fact, row["value"])
            and (not fact["state"] or fact["state"][:6] in row["state"]))


def compatible(report: str, truth: dict) -> dict:
    p = parse(report)
    reasons = []
    truth_fields = {f["field"] for f in truth["facts"]}
    missing = set(truth.get("missing_fields", []))

    bad_src = [r["raw_field"] for r in p["rows"] if not _is_missing_value(r["value"])
               and (not r["sources"] or not _roles(r["sources"]) <= {"A", "B"})]
    if bad_src:
        reasons.append("F0 fonte ausente, distractora ou desconhecida: " + ", ".join(bad_src))
    # F1
    absent = []
    for f in truth["facts"]:
        need = _roles(f["sources"])
        if not any(_row_matches(f, r) and _roles(r["sources"]) & need for r in p["rows"]):
            absent.append(f"{f['field']}={f['value']}" + (f"/{f['state']}" if f["state"] else ""))
    if absent:
        reasons.append("F1 factos do cenário ausentes ou com papel de fonte errado: " + ", ".join(absent))
    # F2
    extra = [f"{r['raw_field']}={r['value']}" for r in p["rows"]
             if r["field"] in truth_fields | missing and not _is_missing_value(r["value"])
             and not any(_row_matches(f, r) for f in truth["facts"])]
    if extra:
        reasons.append("F2 factos que o cenário não tem: " + ", ".join(extra))
    # F3 is enforced by F2 (a missing field may not carry a value) and F4 (its EM FALTA
    # finding is part of the finding set); kept as a label only, no separate code path.
    # F4
    expected = {(f["type"], f["field"]) for f in truth["findings"]}
    found = {(f["type"], f["field"]) for f in p["findings"] if f["type"] not in (None, "SEM ACHADOS")}
    sem = any(f["type"] == "SEM ACHADOS" for f in p["findings"])
    if not (found == expected and (bool(expected) or sem) and not (sem and expected)):
        reasons.append("F4 achados diferentes dos do cenário")
    # F5
    pols = [contradiction_polarity(s) for s in _sentences(p["narrative"])]
    has_contra = any(t == "CONTRADIÇÃO" for t, _ in expected)
    if ("neg" in pols) if has_contra else ("pos" in pols):
        reasons.append("F5 polaridade da narrativa incompatível")
    # F6
    folded = fold(report)
    forb = sorted(n for n in truth.get("forbidden_values", []) if n in numbers(report))
    names = [n for n in truth.get("forbidden_names", []) if fold(n) in folded]
    if forb or names:
        reasons.append("F6 valores ou nomes que o cenário proíbe")
    return {"compatible": not reasons, "reasons": reasons}


def cross_run_factual(runs: list[dict]) -> dict:
    """Every PASS report must be factually compatible with its OWN truth (else the check is
    vacuous and fails closed) and INCOMPATIBLE with every factually different truth.
    Pairs whose truths are factually equivalent (only file names differ) are listed,
    not required to be rejected."""
    passed = [r for r in runs if r["result"] == "PASS" and r.get("report_text")]
    sigs = {(r["family"], r["seed"]): signature(r["truth"]) for r in runs}
    checked, wrongly_compatible, equivalent, self_incompatible = 0, [], [], []
    for r in passed:
        own = (r["family"], r["seed"])
        if not compatible(r["report_text"], r["truth"])["compatible"]:
            self_incompatible.append(own)
        for o in runs:
            key = (o["family"], o["seed"])
            if key == own:
                continue
            if sigs[key] == sigs[own]:
                equivalent.append((own, key))
                continue
            checked += 1
            if compatible(r["report_text"], o["truth"])["compatible"]:
                wrongly_compatible.append((own, key))
    return {"pairs_checked": checked, "wrongly_compatible": wrongly_compatible,
            "equivalent_pairs": equivalent, "self_incompatible": self_incompatible,
            "ok": not wrongly_compatible and not self_incompatible}
