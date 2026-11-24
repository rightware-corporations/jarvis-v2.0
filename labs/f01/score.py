"""F01-A independent scoring. Gold records are computed HERE by the evaluator (tool over the verified bulletin), not
taken from the agent. The model's text is scored WITHOUT the host attribution line. Criteria: frozen_eval.json.
Usage: python -m labs.f01.score <rundir>"""
import json
import re
import statistics as st
import sys
from pathlib import Path

from labs.f01.bm_fx import ExchangeRateTool, fold
from labs.f01.integrity import _dates, check
from labs.f01.offline import replay_source

ROOT = Path(__file__).resolve().parents[2]
ACK = re.compile(r"(nao tenho|nao esta disponivel|indisponivel|nao consigo|nao encontrei|nao foi possivel|nao posso|"
                 r"nao ha (dados|informacao|registo)|sem (dados|acesso)|nao disponho|nao tenho acesso|i (do not|don't|cannot)|"
                 r"not available|unable|nao existe|nao consta|nao foi obtid|nao e possivel)")
WEB = ("web_open", "web_follow", "web_search", "web_find", "web_type", "web_submit", "web_read")
GOLD_CODES = ("USD", "ZAR", "EUR", "JPY", "GBP", "BWP", "CNY", "CHF")


def has(ans: str, term: str) -> bool:
    a = fold(ans)
    t = fold(term)
    return t in a or t.replace(",", ".") in a or t.replace(" ", "") in a.replace(" ", "")


def score_row(r, turn, gold):
    ans, cfg, tools = r["answer"] or "", r["config"], r["tools"]
    s = {"id": r["id"], "config": cfg, "model": r["model"], "seconds": r["seconds"], "tool_calls": len(tools),
         "model_calls": r["model_calls"], "prompt_tokens": r["prompt_tokens"], "error": r["error"]}
    ack = bool(ACK.search(fold(ans)))
    if turn["kind"].startswith("fx"):
        integ = check(ans, gold, turn["q"])
        qd = set(_dates(turn["q"]))
        issues = [i for i in integ["issues"] if not (i["problem"] == "WRONG_DATE" and i["value"] in qd)]
        s["invented"] = len(issues)
        s["issues"] = issues
    else:
        s["invented"] = 0
        if turn["id"] == "G4":
            s["invented"] = sum(1 for y in re.findall(r"\b(1[0-9]{3})\b", ans) if y != "1488")
    if turn.get("must_acknowledge_unavailable"):
        false = any(fold(f) in fold(ans) for f in turn.get("false_claims", []))
        s["correct"] = ack and not false and s["invented"] == 0
    elif turn["any_of"]:
        s["correct"] = any(all(has(ans, t) for t in grp) for grp in turn["any_of"]) and s["invented"] == 0
    else:                                             # G1: conversation
        s["correct"] = bool(ans.strip()) and not r["error"]
    if turn.get("unavailable_without_web") and cfg in "AC":
        s["correct_if_no_web"] = ack and not any(has(ans, t) for grp in turn["any_of"] for t in grp)
    exp = turn["expect_tool"]
    if exp == "none":
        s["tool_ok"] = not tools
    elif exp == "fx_or_context":
        s["tool_ok"] = None
    elif exp == "fx":
        s["tool_ok"] = ("get_exchange_rate" in tools) if cfg in "CD" else (any(t in WEB for t in tools) if cfg == "B" else None)
    elif exp == "web":
        s["tool_ok"] = any(t in WEB for t in tools) if cfg in "BD" else None
    s["acknowledged"] = ack
    return s


def summary(rows):
    out = {}
    for cfg in sorted({r["config"] for r in rows}):
        for model in sorted({r["model"] for r in rows if r["config"] == cfg}):
            rs = [r for r in rows if r["config"] == cfg and r["model"] == model]
            fx = [r for r in rs if r["id"].startswith("F")]
            gen = [r for r in rs if r["id"].startswith("G")]
            tool = [r for r in rs if r["tool_ok"] is not None]
            out[f"{cfg}/{model}"] = {
                "correct_total": f"{sum(bool(r.get('correct')) for r in rs)}/{len(rs)}",
                "correct_fx": f"{sum(bool(r.get('correct')) for r in fx)}/{len(fx)}",
                "correct_general": f"{sum(bool(r.get('correct') or r.get('correct_if_no_web')) for r in gen)}/{len(gen)}",
                "tool_selection_ok": f"{sum(bool(r['tool_ok']) for r in tool)}/{len(tool)}",
                "invented_financial_or_factual": sum(r["invented"] for r in rs),
                "errors": sum(1 for r in rs if r["error"]),
                "mean_seconds": round(st.mean(r["seconds"] for r in rs), 1) if rs else None,
                "mean_tool_calls": round(st.mean(r["tool_calls"] for r in rs), 2) if rs else None,
                "mean_prompt_tokens": round(st.mean(r["prompt_tokens"] for r in rs)) if rs else None}
    return out


if __name__ == "__main__":
    d = Path(sys.argv[1])
    frozen = json.loads((ROOT / "labs/f01/frozen_eval.json").read_text())
    turns = {t["id"]: t for c in frozen["conversations"] for t in c["turns"]}
    gt = ExchangeRateTool(replay_source(), today="2026-11-24")
    gold = [gt(c, "MZN") for c in GOLD_CODES]
    scored = []
    for f in sorted(d.glob("[ABCD]-*.json")):
        for r in json.loads(f.read_text()):
            scored.append(score_row(r, turns[r["id"]], gold))
    (d / "scored.json").write_text(json.dumps(scored, ensure_ascii=False, indent=1))
    s = summary(scored)
    (d / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))
    print(json.dumps(s, ensure_ascii=False, indent=1))
