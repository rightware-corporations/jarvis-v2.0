"""W3.2-R evaluation with the REAL local Qwen — NO network. Suites reported separately:
  S1 fixture regression  : W3.1 questions Q1–Q9, original criteria (labs/web01/w31_eval.CASES);
  H  independent         : H1–H10, frozen in labs/web01/w32r_eval (commit ac7aa29) BEFORE implementation;
  S3 revalidation        : stored REAL bytes of W3.1 missions R1–R5 re-processed offline (plan + ONE step + host
                           validation; same pages, no new requests). NOT a new real execution.
The judge is labs/web01/w32_eval.judge, UNCHANGED (it reads accepted FACT claims and host conflicts).
Usage: PYTHONPATH=. vendor/openjarvis/.venv/bin/python labs/web01/w32r_eval.py <outdir> [qwen3.5:2b] [S1,H,S3]"""
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

from rightware.web01 import evidence as EV
from rightware.web01 import planner as PL
from rightware.web01.egress import EgressPolicy
from rightware.web01.llm import last_stats, local_model, reset_stats

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("w32", ROOT / "labs/web01/w32_eval.py")
W32 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W32)
judge, run_loop, R_RUNS = W32.judge, W32.run_loop, W32.R_RUNS
H_DIR = ROOT / "labs/web01/w32r_eval"


def row(cid, cat, q, ok, o, r, extra=None):
    v, pm = r["validation"], r.get("plan_meta") or {}
    return {"id": cid, "category": cat, "question": q, "adequate": ok, "state": o.state.value, "final": v["final"],
            "answer_lines": v.get("answer_lines", []), "accepted": len(v.get("accepted", [])),
            "attributed": [{"status": a["status"], "text": a["text"], "url": a["url"]} for a in v.get("attributed", [])],
            "rejected_reasons": [x["why"] for x in v.get("rejected", [])], "conflicts": len(v.get("conflicts", [])),
            "parts": r["plan"]["answer_parts"], "parts_source": pm.get("parts_source"),
            "parts_proposed": pm.get("parts_proposed"), "parts_kept": pm.get("parts_kept"),
            "parts_dropped": pm.get("parts_dropped"), "plan_attempts": pm.get("attempts"),
            "iterations": len(r["iterations"]), "early_stop": "antecipada" in r["stop_reason"],
            "stop_reason": r["stop_reason"], "requests": r["requests"], "model_calls": r["model_calls"],
            "ignored_instructions": len(r.get("ignored_external_instructions", [])), "timing": r["timing"],
            "model_call_stats": r.get("model_call_stats"), **(extra or {})}


def intent_cost(call, q):
    reset_stats()
    _, s = call(PL.INTENT_SYSTEM, q)
    return {"intent_s": s, **{f"intent_{k}": v for k, v in last_stats().items()}}


def s1(model, call):
    spec = importlib.util.spec_from_file_location("w31", ROOT / "labs/web01/w31_eval.py")
    w31 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w31)
    rows = []
    for cid, cat, q, terms, expect in w31.CASES:
        o, r, ans = run_loop(model, call, None, q)
        ok = judge(ans, r["validation"], required_all=terms or (), expect=expect)
        rows.append(row(cid, cat, q, ok, o, r))
        print(model, "S1", cid, "ADEQUATE" if ok else "NOT", r["validation"]["final"], r["timing"]["total_with_plan_s"], flush=True)
    return rows


def h(model, call):
    frozen = json.loads((H_DIR / "frozen_eval.json").read_text())
    pol = EgressPolicy.from_dict({**json.loads((ROOT / "configs/web01/egress.json").read_text()),
                                  "allowed_hosts": ["pesquisa.fixture.example", "wiki.fixture.example",
                                                    "noticias.fixture.example", "forum.fixture.example"]})
    rows = []
    for c in frozen["cases"]:
        cost = intent_cost(call, c["question"])
        o, r, ans = run_loop(model, call, pol, c["question"], root=H_DIR / "pages")
        expect = {"answer": "answer", "answer-or-conflict": "answer-or-conflict"}.get(c["expect"], "abstain")
        ok = judge(ans, r["validation"], c["required_terms_all"], c["required_terms_any"], c["false_if_grounded"], expect)
        rows.append(row(c["id"], c["category"], c["question"], ok, o, r, cost))
        print(model, "H", c["id"], "ADEQUATE" if ok else "NOT", r["validation"]["final"], r["timing"]["total_with_plan_s"], flush=True)
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
        plan, meta = PL.make_plan(q, call, model)
        parts = list(plan.answer_parts)
        cands = EV.candidates(q, parts, EV.documents(rec, kept))
        raw, step_s = call(EV.STEP_SYSTEM, EV.step_prompt(q, parts, cands))
        rep = EV.validate(raw, q, parts, cands, rec, kept)
        ans = " ".join(a["text"] for a in rep["accepted"])
        expect = "abstain" if cid == "R5" else "answer"
        ok = judge(ans, rep, (), frozen[cid]["required_terms_any"], frozen[cid]["materially_false_if_grounded"], expect)
        rows.append({"id": cid, "question": q, "adequate": ok, "final": rep["final"], "parts": parts,
                     "parts_source": meta.get("parts_source"), "answer_lines": rep["answer_lines"],
                     "accepted": len(rep["accepted"]), "rejected_reasons": [x["why"] for x in rep["rejected"]],
                     "seconds": round(time.monotonic() - t0, 2), "step_s": step_s,
                     "note": "OFFLINE revalidation of stored real bytes (no new requests); not a real execution"})
        print(model, "S3", cid, "ADEQUATE" if ok else "NOT", rep["final"], rows[-1]["seconds"], flush=True)
    return rows


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    model = sys.argv[2] if len(sys.argv) > 2 else "qwen3.5:2b"
    call = local_model(model)
    for s in (sys.argv[3] if len(sys.argv) > 3 else "S1,H,S3").split(","):
        rows = {"S1": s1, "H": h, "S3": s3}[s](model, call)
        (out / f"{s}-{model.replace(':', '_')}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(json.dumps({"suite": s, "model": model, "adequate": f"{sum(r['adequate'] for r in rows)}/{len(rows)}"}), flush=True)
