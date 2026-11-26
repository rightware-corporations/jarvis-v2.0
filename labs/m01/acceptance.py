"""JRV-M01 real-model acceptance (LAB). Each invocation is ONE step in a FRESH process with a NEW conversation (no
history), through the product chat core: ToolChatAdapter (ModelRouter → direct LocalSimpleTextAdapter or
AgentSession with tools) + PersonalMemory on a SQLite file. Synthetic lab owners only (lab:alfa, lab:beta).

    .runtime/gui/venv/bin/python -m labs.m01.acceptance --db <file> --owner lab:alfa --say "..." --out <jsonl>

The verdicts are computed afterwards by ``labs/m01/run_acceptance.sh`` output review + the DB state recorded here.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from labs.presentation.serve import C_DEF
from rightware.agent.session import ToolOutcome
from rightware.assistant_tools import ModelRouter, ToolChatAdapter
from rightware.memory.identity import StaticOwner
from rightware.memory.personal import PersonalMemory
from rightware.memory.store import MemoryStore
from rightware.persona import RuntimeFacts, system_prompt
from rightware.text_adapter import LocalSimpleTextAdapter


def build(model: str, db: str, owner: str) -> tuple[ToolChatAdapter, PersonalMemory]:
    unavailable = tuple(u for u in RuntimeFacts.__dataclass_fields__["unavailable"].default if "memória" not in u)
    persona = system_prompt(RuntimeFacts(model=model, environment="cloud", unavailable=unavailable, tools=(
        "calculadora exacta (calculator)",
        "memória pessoal permanente (memory_save, memory_update, memory_forget, memory_list) — só quando o utilizador "
        "pedir para lembrar, corrigir ou esquecer")))
    memory = PersonalMemory(MemoryStore(db), StaticOwner(owner, "lab-synthetic"))

    def calc():
        def run(args):
            from openjarvis.tools.calculator import CalculatorTool
            r = CalculatorTool().execute(expression=str(args.get("expression", ""))[:200])
            return ToolOutcome("calculator", "OK" if r.success else "FAILED", r.content, {"success": r.success})
        return {"calculator": (C_DEF, run)}, (lambda: [])
    router = ModelRouter(model, "calculadora, memória pessoal")
    direct = LocalSimpleTextAdapter(model, timeout_seconds=240, max_tokens=768, system_prompt=persona)
    return ToolChatAdapter(model, sites=(), persona=persona, allow=("calc",), extra_tools_factory=calc,
                           router=router, direct=direct, memory=memory, timeout_seconds=240), memory


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--db", required=True)
    a.add_argument("--owner", required=True)
    a.add_argument("--say", required=True)
    a.add_argument("--step", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--model", default="qwen3.5:2b")
    x = a.parse_args()
    adapter, memory = build(x.model, x.db, x.owner)
    t0 = time.monotonic()
    reply = adapter.reply(x.say, ())
    rec = {"step": x.step, "pid": os.getpid(), "owner": x.owner, "said": x.say, "reply": reply,
           "seconds": round(time.monotonic() - t0, 1), "route": (adapter._last or {}).get("route"),
           "tools": (adapter._last or {}).get("tools"), "memory": (adapter._last or {}).get("memory"),
           "db_after": [{"id": m.id, "category": m.category, "topic": m.topic, "content": m.content}
                        for m in memory.store.active(x.owner)]}
    with Path(x.out).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({k: rec[k] for k in ("step", "pid", "seconds", "route", "tools", "db_after")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
