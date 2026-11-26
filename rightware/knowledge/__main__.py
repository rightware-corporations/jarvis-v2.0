"""Host CLI for the document library (operator/lab use; same validation as the future upload route).

    python -m rightware.knowledge add  --owner lab:alfa FILE [--db PATH]
    python -m rightware.knowledge list --owner lab:alfa [--db PATH]
    python -m rightware.knowledge delete --owner lab:alfa d-xxxxxxxx [--db PATH]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rightware.knowledge.library import DocumentLibrary
from rightware.knowledge.store import DEFAULT_PATH, KnowledgeStore
from rightware.memory.identity import StaticOwner


def main(argv=None):
    a = argparse.ArgumentParser(prog="rightware.knowledge")
    a.add_argument("cmd", choices=("add", "list", "delete"))
    a.add_argument("arg", nargs="?")
    a.add_argument("--owner", required=True)
    a.add_argument("--db", default=str(DEFAULT_PATH))
    x = a.parse_args(argv)
    lib = DocumentLibrary(KnowledgeStore(x.db), StaticOwner(x.owner, "lab-synthetic" if x.owner.startswith("lab:")
                                                                     else "operator-config"))
    if x.cmd == "add":
        p = Path(x.arg or "")
        if not p.is_file():
            a.error("ficheiro inexistente")
        print(json.dumps(lib.upload(p.name, p.read_bytes()), ensure_ascii=False))
    elif x.cmd == "list":
        print(json.dumps([{"id": d.id, "name": d.name, "kind": d.kind, "units": d.units}
                          for d in lib.store.list(lib.owner())], ensure_ascii=False))
    else:
        print(json.dumps({"deleted": lib.store.delete(lib.owner(), x.arg or "")}))


if __name__ == "__main__":
    main()
