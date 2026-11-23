"""UI-01: reproducible, isolated runtime for the ORIGINAL OpenJarvis GUI (nothing written inside the vendor).

    python -m rightware.gui setup      # stage .runtime/gui/{oj,venv,static,home} from the pinned vendor

* ``oj/``: ``git archive`` of the pinned vendor commit (``rightware.runtime.PIN``) — never the working tree.
* ``venv/``: ``uv sync --frozen --extra server --no-dev --no-editable`` from the pin's ``uv.lock`` (hash-checked).
* ``static/``: the original React frontend built from the pin's ``package-lock.json`` with the npm version the
  frontend declares (``npx npm@<packageManager>``, nothing installed system-wide) into ``static/`` (outside both
  the vendor and the installed package, so the original server's own static mount is never active).
* ``home/``: OpenJarvis config dir (``OPENJARVIS_HOME``) with ``configs/gui/openjarvis-gui.toml``.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime" / "gui"
VENDOR = ROOT / "vendor" / "openjarvis"
VENDOR_PATHS = ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "src", "scripts/install", "deploy/windows",
                "frontend")
CONFIG = ROOT / "configs" / "gui" / "openjarvis-gui.toml"


def pin() -> str:
    from rightware.runtime import PIN
    return PIN


def paths(runtime: Path = RUNTIME) -> dict:
    return {"oj": runtime / "oj", "venv": runtime / "venv", "static": runtime / "static",
            "home": runtime / "home", "python": runtime / "venv" / "bin" / "python",
            "manifest": runtime / "manifest.json", "audit": runtime / "audit.jsonl"}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _tree_sha(d: Path) -> tuple[int, str]:
    h, n = hashlib.sha256(), 0
    for p in sorted(x for x in d.rglob("*") if x.is_file()):
        h.update(p.relative_to(d).as_posix().encode() + b"\0" + bytes.fromhex(_sha(p)))
        n += 1
    return n, h.hexdigest()


def _run(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode:
        raise RuntimeError(f"GUI_SETUP_FAILED: {' '.join(map(str, cmd[:3]))}")
    return r


def setup(runtime: Path = RUNTIME) -> dict:
    p = paths(runtime)
    gitlink = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "HEAD", "vendor/openjarvis"],
                             capture_output=True, text=True).stdout.split()
    if len(gitlink) < 3 or gitlink[2] != pin():
        raise RuntimeError("VENDOR_GITLINK_NOT_PIN")
    shutil.rmtree(p["oj"], ignore_errors=True)
    p["oj"].mkdir(parents=True)
    archive = runtime / "vendor.tar"
    _run(["git", "-C", str(VENDOR), "archive", "--format=tar", "-o", str(archive), pin(), *VENDOR_PATHS])
    with tarfile.open(archive) as t:
        t.extractall(p["oj"], filter="data")
    archive.unlink()
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("UV_NOT_FOUND")
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(p["venv"]), "UV_PYTHON_DOWNLOADS": "never",
           "SETUPTOOLS_SCM_PRETEND_VERSION": f"0.0.0+g{pin()[:7]}"}
    _run([uv, "sync", "--frozen", "--extra", "server", "--no-dev", "--no-editable"], cwd=p["oj"], env=env)
    fe = p["oj"] / "frontend"
    npm_version = json.loads((fe / "package.json").read_text())["packageManager"].split("@", 1)[1]
    npx = shutil.which("npx")
    if npx is None:
        raise RuntimeError("NPX_NOT_FOUND")
    fenv = {**os.environ, "VITE_API_URL": "", "VITE_SUPABASE_ANON_KEY": "", "npm_config_update_notifier": "false"}
    _run([npx, "-y", f"npm@{npm_version}", "ci", "--no-audit", "--no-fund"], cwd=fe, env=fenv)
    shutil.rmtree(p["static"], ignore_errors=True)
    _run([npx, "-y", f"npm@{npm_version}", "exec", "--", "vite", "build", "--outDir", str(p["static"]),
          "--emptyOutDir"], cwd=fe, env=fenv)
    p["home"].mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONFIG, p["home"] / "config.toml")
    n, tree = _tree_sha(p["static"])
    manifest = {"vendor_pin": pin(), "uv_lock_sha256": _sha(p["oj"] / "uv.lock"),
                "package_lock_sha256": _sha(fe / "package-lock.json"), "npm": npm_version,
                "static_files": n, "static_tree_sha256": tree, "config_sha256": _sha(CONFIG)}
    p["manifest"].write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
