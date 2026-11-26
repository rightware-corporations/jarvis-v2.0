"""JRV-K01 real-model acceptance (LAB): one step per FRESH process and NEW conversation through the product chat core
(ToolChatAdapter: router/direct/tools + PersonalMemory + DocumentLibrary). Synthetic owners and documents only.

    python -m labs.k01.acceptance --kdb K --mdb M --owner lab:alfa --step 2 --out OUT.jsonl [--upload NAME] --say "..."
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from labs.k01.fixtures import MALICIOUS, REPORT_2024, REPORT_2025, make_pdf
from labs.m01.acceptance import build
from rightware.knowledge.library import DocumentLibrary
from rightware.knowledge.store import KnowledgeStore

DOCS = {"relatorio-anual-2025.pdf": lambda: make_pdf(REPORT_2025),
        "relatorio-anual-2024.pdf": lambda: make_pdf(REPORT_2024),
        "nota-fornecedores.pdf": lambda: make_pdf(MALICIOUS)}


def main():
    a = argparse.ArgumentParser()
    for k in ("--kdb", "--mdb", "--owner", "--step", "--out"):
        a.add_argument(k, required=True)
    a.add_argument("--upload")
    a.add_argument("--say")
    a.add_argument("--model", default="qwen3.5:2b")
    x = a.parse_args()
    adapter, memory = build(x.model, x.mdb, x.owner)
    lib = DocumentLibrary(KnowledgeStore(x.kdb), memory.owner_provider)
    adapter.documents = lib
    rec = {"step": x.step, "pid": os.getpid(), "owner": x.owner}
    if x.upload:                                   # host upload path (same validation as the future route)
        rec["upload"] = lib.upload(x.upload, DOCS[x.upload]())
    if x.say:
        t0 = time.monotonic()
        rec["said"] = x.say
        rec["reply"] = adapter.reply(x.say, ())
        rec["seconds"] = round(time.monotonic() - t0, 1)
        last = adapter._last or {}
        rec.update(route=last.get("route"), tools=last.get("tools"), documents=last.get("documents"),
                   memory=last.get("memory"))
    rec["docs_after"] = [{"id": d.id, "name": d.name} for d in lib.store.list(x.owner)]
    rec["memories_after"] = [m.content for m in memory.store.active(x.owner)]
    with Path(x.out).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({k: rec.get(k) for k in ("step", "pid", "seconds", "route", "tools", "docs_after")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
