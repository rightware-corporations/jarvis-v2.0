"""JRV-TE-P2D frozen set = TE-P2C frozen set + production SSRF fetcher + TE-P2C evidence/pre-registration.

Baseline ``docs/evidence/te_p2d/frozen_manifest_p2d_g0.json`` computed on ``cf096df`` before any TE-P2D edit.
"""
from __future__ import annotations

import hashlib
import json

from labs.te_p2a_gateway import frozen, frozen_p2c

MANIFEST = frozen.ROOT / "docs/evidence/te_p2d/frozen_manifest_p2d_g0.json"
GROUPS = {
    **frozen_p2c.GROUPS,
    "ssrf_production": ("rightware/agent/web.py",),
    "p2c_evidence": ("docs/research/TE_P2C_RESUME_DESIGN.md", "docs/research/TE_P2C_PREREGISTRATION.md",
                     "docs/research/TE_P2C_RESULTS_2026-11-19.md", "docs/evidence/te_p2c/frozen_manifest_p2c_g0.json",
                     "docs/evidence/te_p2c/mutation_p2c.json", "docs/evidence/te_p2c/harness_fake_dryruns.json",
                     "docs/evidence/te_p2c/te_p2c_trials_evidence_2026-11-19.json"),
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
