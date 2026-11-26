"""LIVE02 — explicit, cloud-only recovery checks. No tunnel, downloads, tokens or automatic restarts.

Run from the checkout with the prepared GUI venv. State is on an operator-provisioned
private persistent volume, not in Git. Readiness does not prove storage durability or inference.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import shutil
import sqlite3
import stat
import time
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = {"memory": "mem.sqlite3", "documents": "docs.sqlite3"}
TABLES = {"memory": {"memories", "memory_events"},
          "documents": {"documents", "segments", "segments_fts", "document_events"}}


def absolute_expiry(minutes: float, deadline: float | None = None, *, now: float | None = None) -> float:
    """Never extend an absolute authorised window on restart. Legacy relative mode remains available."""
    now = time.time() if now is None else now
    if not math.isfinite(minutes) or not 1 <= minutes <= 60:
        raise ValueError("private access needs 1..60 minutes")
    if deadline is not None:
        if not math.isfinite(deadline) or not now < deadline <= now + 3600:
            raise ValueError("absolute access deadline expired or exceeds 60 minutes")
        return min(now + minutes * 60, deadline)
    return now + minutes * 60


def private_root(path: Path | str, *, existing: bool = True) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute() or p.is_symlink():
        raise ValueError("state directory must be an absolute non-symlink path")
    p = p.resolve(strict=existing)
    if p == ROOT or p.is_relative_to(ROOT):
        raise ValueError("state directory must be outside the repository checkout")
    if existing:
        s = p.stat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
            raise ValueError("state directory must be owned by this host user and private (0700)")
    return p


def validate_database(path: Path, kind: str) -> None:
    """Open read-only (WAL-aware). Missing data is a hard failure, not a fresh database."""
    s = path.lstat()
    if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.getuid()
            or stat.S_IMODE(s.st_mode) & 0o077 or s.st_size == 0):
        raise ValueError("unsafe or empty database")
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(path) + suffix)
        if sidecar.is_symlink():
            raise ValueError("database sidecar must not be a symlink")
        if sidecar.exists():
            ss = sidecar.lstat()
            if (not stat.S_ISREG(ss.st_mode) or ss.st_uid != os.getuid()
                    or ss.st_nlink != 1 or stat.S_IMODE(ss.st_mode) & 0o077):
                raise ValueError("unsafe database sidecar")
    with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)) as con:
        con.execute("PRAGMA query_only=ON")
        names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not TABLES[kind].issubset(names):
            raise ValueError("database schema does not match the expected store")
        if con.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("database integrity check failed")


def state_files(path: Path | str) -> dict[str, Path]:
    p = private_root(path)
    result = {kind: p / filename for kind, filename in FILES.items()}
    for kind, file in result.items():
        validate_database(file, kind)
    return result


def initialize(path: Path | str) -> None:
    """Explicit new installation only. Never overwrite, restore, or delete data."""
    p = private_root(path, existing=False)
    p.mkdir(mode=0o700, parents=False, exist_ok=False)
    # Private from first byte; a partial init is deliberately left for operator review.
    previous = os.umask(0o077)
    try:
        from rightware.memory.store import MemoryStore
        from rightware.knowledge.store import KnowledgeStore
        MemoryStore(p / FILES["memory"])
        KnowledgeStore(p / FILES["documents"])
        state_files(p)
    finally:
        os.umask(previous)


def model_present(model: str) -> bool:
    """Loopback only, no inherited proxy, no redirect, no generation or pull."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open("http://127.0.0.1:11434/api/tags", timeout=5) as res:
        body = res.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        return False
    data = json.loads(body)
    return any(row.get("name") == model or row.get("model") == model for row in data.get("models", []))


def preflight(path: Path | str, model: str, *, voice: bool) -> dict:
    """Report metadata only. No personal content, paths, session links or environment secrets."""
    from rightware.gui import runtime as R
    checks = {}
    def check(name, fn):
        try:
            checks[name] = bool(fn())
        except Exception:
            checks[name] = False

    check("private_state_and_integrity", lambda: bool(state_files(path)))
    check("state_free_space", lambda: shutil.disk_usage(private_root(path)).free >= 512 * 1024**2)
    p = R.paths()
    check("runtime_free_space", lambda: shutil.disk_usage(p["runtime"]).free >= 512 * 1024**2)
    check("gui_runtime", lambda: p["python"].is_file() and (p["static"] / "index.html").is_file())
    check("bundle_matches_source", lambda: R.build_stamp()["match"])
    check("ollama_loopback_config", lambda: tomllib.loads((p["home"] / "config.toml").read_text())
          ["engine"]["ollama"]["host"] == "http://127.0.0.1:11434")
    check("ollama_model_present", lambda: model_present(model))
    if voice:
        from rightware.gui import voice as V
        check("voice_assets_present", lambda: V.available()[0])
    return {"ready": all(checks.values()), "checks": checks, "storage_durability": "NOT_VERIFIED",
            "inference_and_physical_voice": "NOT_RUN", "tunnel": "NOT_CHECKED"}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__)
    sub = a.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init", help="explicitly create NEW stores; never use to recover missing data")
    init.add_argument("--state-dir", required=True)
    check = sub.add_parser("check", help="readiness checks; does not start or expose anything")
    check.add_argument("--state-dir", required=True)
    check.add_argument("--model", default="qwen3.5:2b")
    check.add_argument("--voice", action="store_true")
    x = a.parse_args(argv)
    if x.cmd == "init":
        try:
            initialize(x.state_dir)
        except Exception:
            print(json.dumps({"initialized": False, "reason": "STATE_INIT_REFUSED_OR_INCOMPLETE"}))
            return 2
        print(json.dumps({"initialized": True, "storage_durability": "NOT_VERIFIED"}))
        return 0
    report = preflight(x.state_dir, x.model, voice=x.voice)
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
