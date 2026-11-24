"""F01-A offline document sources (NO network).
* ``replay_source``: bytes collected in OP01-FX-REAL-PROXY (``.runtime/op01-fx``), addressed by the exact URL in the
  audit log; anything not collected returns None (→ NOT_RETRIEVED), never a substitute.
* ``fixture_source``: independent FICTIONAL bulletins (labs/f01/fixtures) for mechanism tests."""
import json
from pathlib import Path

from labs.f01.bm_fx import Source

ROOT = Path(__file__).resolve().parents[2]


def replay_source(store: Path = ROOT / ".runtime/op01-fx") -> Source:
    docs = {}
    for line in (store / "requests.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("status") == 200 and r.get("sha256") and (store / f"{r['sha256']}.bin").is_file():
            docs[r["url"]] = (store / f"{r['sha256']}.bin", r.get("content_type", ""), r["utc"])

    def get(url):
        hit = docs.get(url)
        return (hit[0].read_bytes(), hit[1], hit[2]) if hit else None
    return Source(get, "OFFLINE replay de documentos reais recolhidos em OP01-FX-REAL-PROXY (24/11/2026)")


def fixture_source(root: Path) -> Source:
    files = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    def get(url):
        f = files.get(url)
        return ((root / f["file"]).read_bytes(), f["type"], f["retrieved_at"]) if f else None
    return Source(get, "FIXTURE fictícia (testes de mecanismo)")
