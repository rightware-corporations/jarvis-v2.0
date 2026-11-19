"""JRV-TE-P2B frozen set: files whose content must NOT change during TE-P2B (hash-checked).

The baseline manifest (``docs/evidence/te_p2b/frozen_manifest_g0.json``) was computed at preflight on
``6302246f7aef0ba1ed498b4443ae77b600a73af9`` BEFORE any TE-P2B edit. Tests and the trial runner compare
the working tree against it and fail closed on any difference.

Groups:
* ``verifier``   — the RIGHTWARE verifier (sole authority on the verdict) and what it judges with;
* ``policy``     — authority, receipts, browser allowlist, fixture transport, model-boundary tool filter;
* ``scenario``   — synthetic fixture (ground truth source) and the fixed T1 instruction;
* ``historical`` — committed A1–A4 evidence;
* ``permissions``— CI workflows.
The OpenJarvis pin (gitlink) is checked separately with ``git ls-files -s``.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/evidence/te_p2b/frozen_manifest_g0.json"
OPENJARVIS_PIN = "f21d902f4d3bd7f0f3f138f1a4613019a394b549"

GROUPS = {
    "verifier": ("labs/te_p2a_gateway/verify.py", "labs/te_p1_bakeoff/score_semantic.py",
                 "rightware/agent/completion.py", "rightware/agent/task_contract.py"),
    "policy": ("rightware/agent/policy.py", "rightware/agent/receipts.py", "rightware/agent/browser.py",
               "rightware/agent/session.py", "labs/te_p2a_gateway/fixture_transport.py",
               "labs/te_p2a_gateway/model_tap.py"),
    "scenario": ("labs/te_p1_bakeoff/site.py", "labs/te_p1_bakeoff/live_harness.py"),
    "historical": ("docs/evidence/te_p2a/te_p2a_live_evidence_2026-11-19.json",
                   "docs/evidence/te_p2a/te_p2a_review_evidence_2026-11-19.json"),
    "permissions": tuple(sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / ".github/workflows").glob("*.yml"))),
}


def sha256_file(rel: str) -> str:
    """SHA-256 of the file with CRLF normalised to LF (a Windows checkout with autocrlf must hash the same;
    for the LF files in the repository this equals the plain SHA-256)."""
    return hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def current() -> dict:
    files = {rel: sha256_file(rel) for group in GROUPS.values() for rel in group}
    groups = {g: hashlib.sha256("".join(f"{r}\0{files[r]}\n" for r in sorted(rels)).encode()).hexdigest()
              for g, rels in GROUPS.items()}
    return {"files": files, "groups": groups}


def openjarvis_gitlink() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s", "vendor/openjarvis"], capture_output=True,
                             text=True, check=True).stdout.split()
        return out[1] if len(out) >= 2 else None
    except (OSError, subprocess.CalledProcessError):
        return None


def differences(manifest: dict | None = None) -> list[str]:
    """Every frozen file whose hash differs from the manifest (fail closed: missing = different)."""
    base = manifest if manifest is not None else json.loads(MANIFEST.read_text(encoding="utf-8"))
    now = current()["files"]
    diffs = [rel for rel, digest in base["files"].items() if now.get(rel) != digest]
    diffs += [rel for rel in now if rel not in base["files"]]
    return sorted(set(diffs))


if __name__ == "__main__":
    print(json.dumps({**current(), "openjarvis_gitlink": openjarvis_gitlink()}, indent=2, sort_keys=True))
