"""R02-A evaluation runner (LAB). Offline: the network is the synthetic corpus (``CorpusFetcher``); the model is the
REAL local Qwen via Ollama (loopback) unless ``--scripted`` is given. The agent path is the product one:
``ToolChatAdapter`` → ``AgentSession`` (policy, receipts) + ``ResearchToolkit`` (provenance, citations) + the pinned
OpenJarvis ``CalculatorTool``. No expected answer is ever given to the model; the scorer reads ``expect`` afterwards.

    .runtime/gui/venv/bin/python -m labs.r02.run_eval --model qwen3.5:2b --out docs/evidence/r02a/qwen2b.json
    ... --mode closed   # destination NOT verifiable: only the closed host list is readable (R02-B proxy scenario)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from labs.r02.corpus import CorpusFetcher
from labs.r02.score import score
from rightware.agent.policy import Budgets, ToolDef
from rightware.assistant_tools import ToolChatAdapter
from rightware.persona import RuntimeFacts, system_prompt
from rightware.research.toolkit import ResearchToolkit

HERE = Path(__file__).resolve().parent
C_DEF = ToolDef("calculator", "Calcula uma expressão matemática exacta (ex.: (50000-35000)/50000*100). Usa para "
                "qualquer conta com números; não faças contas de cabeça.",
                {"expression": {"type": "string", "maxLength": 200, "description": "expressão matemática"}},
                ("expression",), session_flag="calc", consequential=False, max_calls=4)
CLOSED = ("www.bm-boletins.example", "www.ine-mz.example", "www.at-mz.example", "www.boletim-republica.example")


def calc_tools():
    from rightware.agent.session import ToolOutcome

    def run_c(args):
        from openjarvis.tools.calculator import CalculatorTool
        r = CalculatorTool().execute(expression=str(args.get("expression", ""))[:200])
        return ToolOutcome("calculator", "OK" if r.success else "FAILED", r.content, {"success": r.success})
    return {"calculator": (C_DEF, run_c)}, (lambda: [])


def run(model: str, ids: list[str] | None, mode: str, engine_factory=None) -> list[dict]:
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))["questions"]
    persona = system_prompt(RuntimeFacts(model=model, environment="cloud", tools=(
        "pesquisa geral na Internet com leitura de páginas e documentos PDF (web_search, web_read, doc_read)",
        "calculadora exacta (calculator)")))
    out = []
    for q in qs:
        if ids and q["id"] not in ids:
            continue
        fetcher = CorpusFetcher()
        if mode == "closed":
            fetcher.verifies_destination = False
        holder = {}

        def factory():
            holder["k"] = ResearchToolkit(fetcher, closed_hosts=CLOSED if mode == "closed" else ())
            return holder["k"]
        adapter = ToolChatAdapter(model, sites=(), persona=persona, allow=("websearch", "calc"),
                                  extra_tools_factory=calc_tools, research_factory=factory,
                                  budgets=Budgets(max_calls=10, deadline_seconds=420.0), max_turns=10,
                                  timeout_seconds=300, engine_factory=engine_factory)
        t0 = time.monotonic()
        try:
            text = adapter.reply(q["question"], ())
            err = None
        except Exception as exc:                                   # recorded, never hidden
            text, err = "", type(exc).__name__
        secs = round(time.monotonic() - t0, 1)
        last = adapter._last or {}
        k = holder.get("k")
        rec = {"id": q["id"], "domain": q["domain"], "difficulty": q["difficulty"], "kind": q.get("kind", "functional"),
               "question": q["question"], "answer": text, "error": err, "seconds": secs,
               "completion": last.get("completion"), "flags": last.get("flags"), "tools": last.get("tools"),
               "denials": last.get("denials"),
               "research": k.records() if k else None,
               "fetch_log": fetcher.log}
        rec["score"] = score(q, rec)
        out.append(rec)
        print(f"{q['id']} {secs:>6}s {rec['score']['verdict']:<8} tools={rec['tools']}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:2b")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--mode", choices=("verified", "closed"), default="verified")
    ap.add_argument("--out", required=True)
    x = ap.parse_args()
    res = run(x.model, x.ids, x.mode)
    from labs.r02.score import aggregate
    Path(x.out).parent.mkdir(parents=True, exist_ok=True)
    Path(x.out).write_text(json.dumps({"model": x.model, "mode": x.mode, "corpus": "synthetic offline (labs/r02)",
                                       "summary": aggregate(res), "results": res}, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
    print(json.dumps(aggregate(res), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
