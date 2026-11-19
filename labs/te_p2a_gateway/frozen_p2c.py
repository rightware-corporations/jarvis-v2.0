"""JRV-TE-P2C frozen set = the TE-P2B frozen set + what TE-P2B produced and must stay intact.

Baseline manifest ``docs/evidence/te_p2c/frozen_manifest_p2c_g0.json`` computed at preflight on
``c06624c7956a52a7607308c6b6bd6139b10e1bc0`` before any TE-P2C edit. Hashes use ``frozen.sha256_file``
(CRLF normalised). Note: the TE-P2B runner checks its harness hashes against the TE-P2B pre-registration, so
after TE-P2C edits it (correctly) refuses to run; B1–B5 stay reproducible at ``ca9a607``.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from labs.te_p2a_gateway import frozen

MANIFEST = frozen.ROOT / "docs/evidence/te_p2c/frozen_manifest_p2c_g0.json"
GROUPS = {
    **frozen.GROUPS,
    "p2b_contract": ("labs/te_p2a_gateway/report_contract.py",),
    "p2b_evidence": ("docs/research/TE_P2B_PREREGISTRATION.md", "docs/research/TE_P2B_RESULTS_2026-11-19.md",
                     "docs/evidence/te_p2b/frozen_manifest_g0.json", "docs/evidence/te_p2b/mutation_p2b.json",
                     "docs/evidence/te_p2b/harness_fake_dryrun.json",
                     "docs/evidence/te_p2b/te_p2b_trials_evidence_2026-11-19.json"),
    "t2_history": ("labs/te_p1_bakeoff/live_t2.py", "docs/evidence/te_p1_live/te_p1_live_evidence_2026-11-18.json"),
}


def current() -> dict:
    files = {rel: frozen.sha256_file(rel) for rels in GROUPS.values() for rel in rels}
    groups = {g: hashlib.sha256("".join(f"{r}\0{files[r]}\n" for r in sorted(rels)).encode()).hexdigest()
              for g, rels in GROUPS.items()}
    return {"files": files, "groups": groups}


def differences(manifest: dict | None = None) -> list[str]:
    base = manifest if manifest is not None else json.loads(MANIFEST.read_text(encoding="utf-8"))
    now = current()["files"]
    return sorted({r for r, d in base["files"].items() if now.get(r) != d} | {r for r in now if r not in base["files"]})


if __name__ == "__main__":
    print(json.dumps(current(), indent=2, sort_keys=True))
