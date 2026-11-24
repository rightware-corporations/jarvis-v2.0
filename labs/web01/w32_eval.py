"""W3.2 evaluation with the REAL local Qwen — NO network. Three suites, reported separately:
  S1 fixture regression : W3.1 questions Q1–Q9 on the original fixture corpus (compare with W3.1 eval v2);
  S2 independent        : 8 frozen questions G1–G8 on a FICTIONAL corpus (labs/web01/w32_eval/pages);
  S3 revalidation       : the stored REAL bytes of W3.1 missions R1–R5 re-processed offline (retrieval + synthesis
                          only; same pages, no new requests). NOT a new real execution.
Expected answers live only in the frozen evaluator files. Usage:
  PYTHONPATH=. vendor/openjarvis/.venv/bin/python labs/web01/w32_eval.py <outdir> [qwen3.5:2b] [S1,S2,S3]"""
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

from rightware.web01 import evidence as EV
from rightware.web01 import fixture as FX
from rightware.web01.egress import EgressPolicy
from rightware.web01.free_research import FreeResearchMission
from rightware.web01.llm import local_model
from rightware.web01.planner import make_plan

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "labs/web01/w32_eval"
R_RUNS = {"R1": "livre-20261124T073653-4f1734", "R2": "livre-20261124T073836-2dfe1a", "R3": "livre-20261124T073923-630323",
          "R4": "livre-20261124T074005-e3964d", "R5": "livre-20261124T074050-f8efe0"}


def nnum(s: str) -> str:
    return re.sub(r"(?<=\d)[ . ](?=\d{3}\b)", "", s.lower())


def judge(answer: str, report: dict, required_all=(), required_any=(), false_terms=(), expect="answer") -> bool:
    a = nnum(answer)
    false_hit = any(nnum(f) in a for f in false_terms)
    req = all(nnum(t) in a for t in required_all) and all(any(nnum(x) in a for x in grp) for grp in required_any)
    if expect == "answer":
        return req and not false_hit and bool(report.get("accepted"))
    if expect == "answer-or-conflict":
        return (req and not false_hit) or bool(report.get("conflicts"))
    return not false_hit                                     # abstain / abstain-or-correct / no-obey


def summary_row(cid, cat, q, ok, o, r, extra=None):
    v = r["validation"]
    return {"id": cid, "category": cat, "question": q, "adequate": ok, "state": o.state.value, "final": v["final"],
            "answer_lines": v.get("answer_lines", []), "unanswered_parts": v.get("unanswered_parts", []),
            "accepted": len(v.get("accepted", [])), "rejected": len(v.get("rejected", [])),
            "rejected_reasons": [x["why"] for x in v.get("rejected", [])], "conflicts": v.get("conflicts", []),
            "iterations": len(r["iterations"]), "early_stop": "antecipada" in r["stop_reason"], "stop_reason": r["stop_reason"],
            "requests": r["requests"], "requests_avoided": r["requests_avoided"], "model_calls": r["model_calls"],
            "ignored_instructions": len(r.get("ignored_external_instructions", [])),
            "plan_valid_model": (r.get("plan_meta") or {}).get("valid_model_plan"),
            "plan_normalised": (r.get("plan_meta") or {}).get("normalised"), "timing": r["timing"], **(extra or {})}


def run_loop(model, call, policy, q, root=None):
    m = FreeResearchMission(policy, model=model, model_call=call, runtime=Path(tempfile.mkdtemp()),
                            fetcher_factory=(lambda stop: FX.fixture_fetcher(cancel=stop, root=root)))
    t0 = time.monotonic()
    plan, meta = m.plan(q)
    o = m.run(threading.Event(), params={"plan": plan, "plan_meta": meta})
    r = json.loads((m.last_run / "result.json").read_text())
    r["timing"]["total_with_plan_s"] = round(time.monotonic() - t0, 2)
    answer = " ".join(a["text"] for a in r["validation"].get("accepted", []))
    return o, r, answer


def s1(model, call):
    spec = importlib.util.spec_from_file_location("w31", ROOT / "labs/web01/w31_eval.py")
    w31 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w31)
    rows = []
    for cid, cat, q, terms, expect in w31.CASES:
        o, r, ans = run_loop(model, call, None, q)
        e = {"answer": "answer", "answer-or-conflict": "answer-or-conflict", "abstain": "abstain", "no-obey": "no-obey"}[expect]
        ok = judge(ans, r["validation"], required_all=terms or (), expect=e)
        rows.append(summary_row(cid, cat, q, ok, o, r))
        print(model, "S1", cid, "ADEQUATE" if ok else "NOT", r["validation"]["final"], r["timing"]["total_with_plan_s"], flush=True)
    return rows


def s2(model, call):
    frozen = json.loads((EVAL / "frozen_eval.json").read_text())
    pol = EgressPolicy.from_dict({**json.loads((ROOT / "configs/web01/egress.json").read_text()),
                                  "allowed_hosts": ["pesquisa.fixture.example", "wiki.fixture.example",
                                                    "noticias.fixture.example", "forum.fixture.example"]})
    rows = []
    for c in frozen["cases"]:
        o, r, ans = run_loop(model, call, pol, c["question"], root=EVAL / "pages")
        ok = judge(ans, r["validation"], c["required_terms_all"], (), c["false_if_grounded"],
                   {"answer": "answer", "answer-or-conflict": "answer-or-conflict"}.get(c["expect"], "abstain"))
        opened = [x for s in r["iterations"] for x in s["opened"]]
        extra = {"news_page_opened": any("noticias" in x["url"] for x in opened)} if c["id"] == "G4" else {}
        rows.append(summary_row(c["id"], c["category"], c["question"], ok, o, r, extra))
        print(model, "S2", c["id"], "ADEQUATE" if ok else "NOT", r["validation"]["final"], r["timing"]["total_with_plan_s"], flush=True)
    return rows


def s3(model, call):
    frozen = {c["id"]: c for c in json.loads((ROOT / "labs/web01/w31_real/frozen_eval.json").read_text())["cases"]}
    rows = []
    for cid, d in R_RUNS.items():
        base = ROOT / ".runtime/web01-missions" / d
        rec = [json.loads(x) for x in (base / "receipts.jsonl").read_text().splitlines()]
        kept = {r["seq"]: (base / "pages" / f"{r['seq']}.bin").read_bytes() for r in rec if r["status"] == "OK"}
        assert all(hashlib.sha256(kept[r["seq"]]).hexdigest() == r["sha256"] for r in rec if r["status"] == "OK")
        q = frozen[cid]["question"]
        t0 = time.monotonic()
        plan, meta = make_plan(q, call, model)
        parts = list(plan.answer_parts)
        cands = EV.candidates(q, parts, EV.documents(rec, kept))
        raw, synth_s = call(EV.SYNTH_SYSTEM, EV.synthesis_prompt(q, parts, cands))
        rep = EV.validate(raw, q, parts, cands, rec, kept)
        ans = " ".join(a["text"] for a in rep["accepted"])
        req_any = frozen[cid]["required_terms_any"]
        expect = "abstain" if cid == "R5" else "answer"
        ok = judge(ans, rep, (), req_any, frozen[cid]["materially_false_if_grounded"], expect)
        rows.append({"id": cid, "question": q, "adequate": ok, "final": rep["final"], "parts": parts,
                     "answer_lines": rep["answer_lines"], "accepted": len(rep["accepted"]), "rejected": len(rep["rejected"]),
                     "rejected_reasons": [x["why"] for x in rep["rejected"]], "candidates": len(cands),
                     "plan_valid_model": meta["valid_model_plan"], "plan_normalised": meta["normalised"],
                     "seconds": round(time.monotonic() - t0, 2), "synthesis_s": synth_s,
                     "note": "OFFLINE revalidation of stored real bytes (no new requests); not a real execution"})
        print(model, "S3", cid, "ADEQUATE" if ok else "NOT", rep["final"], rows[-1]["seconds"], flush=True)
    return rows


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    model = sys.argv[2] if len(sys.argv) > 2 else "qwen3.5:2b"
    suites = (sys.argv[3] if len(sys.argv) > 3 else "S1,S2,S3").split(",")
    call = local_model(model)
    for s in suites:
        rows = {"S1": s1, "S2": s2, "S3": s3}[s](model, call)
        (out / f"{s}-{model.replace(':', '_')}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(json.dumps({"suite": s, "model": model, "adequate": f"{sum(r['adequate'] for r in rows)}/{len(rows)}"}), flush=True)
