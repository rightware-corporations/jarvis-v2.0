"""JRV-P3A: reproducible, verifiable build of the RIGHTWARE Gateway runtime image.

    python -m rightware.gateway.image build [--ca BUNDLE] [--network host] [--no-cache]
    python -m rightware.gateway.image check        # is the local image the one this source tree describes?
    python -m rightware.gateway.image digest       # print the source digest

* Base image pinned by digest (same digest as the mission's other containers).
* Runtime dependencies ONLY from the pinned OpenJarvis ``uv.lock`` (``uv sync --frozen``, hash-verified); the
  build tool ``uv`` is installed with ``pip --require-hashes``. The vendor is taken with ``git archive`` at the
  pin recorded in ``rightware/runtime.py`` (never from a working tree), after checking the gitlink matches it.
* Minimal context staged in a temporary directory: the RIGHTWARE runtime module closure (``RUNTIME_FILES``),
  ``configs/gateway/*`` and the vendor paths the package build needs. No tests, labs, docs, .git or .runtime.
* Unprivileged user 10001, no setuid/setgid binaries; run with read-only root fs, all capabilities dropped,
  no-new-privileges (see ``hardening_args``).
* The image carries ``org.rightware.gateway.*`` labels (source digest, pin, base, lock hash). The product starts
  the Gateway ONLY by the image id of a local image whose labels match the CURRENT source tree; anything else is
  refused (missing / stale / unverified). Nothing is pushed to any registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_IMAGE = "mirror.gcr.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
IMAGE_TAG = "rightware/jarvis-gateway:p3a"
LABEL = "org.rightware.gateway."
RUNTIME_USER = "10001:10001"
MANIFEST = ROOT / ".runtime" / "gateway-image.json"
BUILD_FILES = ("configs/gateway/Dockerfile", "configs/gateway/build-requirements.txt")
# Import closure of rightware.gateway.{mcp_http,model_tap,verify,synthetic.site} (checked by a test).
RUNTIME_FILES = (
    "rightware/__init__.py", "rightware/windows_actions.py",
    *(f"rightware/agent/{m}.py" for m in ("__init__", "browser", "completion", "diagnostics", "file_task", "policy",
                                          "receipts", "session", "task_contract", "trace", "web")),
    *(f"rightware/gateway/{m}" for m in ("__init__.py", "PARITY.json", "gateway.py", "mcp_http.py", "model_tap.py",
                                         "report_contract.py", "verify.py", "image.py")),
    *(f"rightware/gateway/synthetic/{m}.py" for m in ("__init__", "fixture_transport", "score_semantic", "site")),
)
VENDOR_PATHS = ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "src", "scripts/install", "deploy/windows")


class ImageError(RuntimeError):
    """Code-only messages (they become Control Plane error codes)."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def vendor_pin() -> str:
    from rightware.runtime import PIN
    return PIN


def source_digest(root: Path = ROOT) -> str:
    """Identity of everything that determines the image: RIGHTWARE runtime files, build files, vendor pin and its
    lock, and the base digest."""
    h = hashlib.sha256()
    for rel in sorted(RUNTIME_FILES + BUILD_FILES):
        h.update(f"{rel}\0{_sha((root / rel).read_bytes())}\n".encode())
    h.update(f"vendor_pin\0{vendor_pin()}\nuv.lock\0{_sha((root / 'vendor/openjarvis/uv.lock').read_bytes())}\n"
             f"base\0{BASE_IMAGE}\n".encode())
    return h.hexdigest()


def expected_labels(root: Path = ROOT) -> dict:
    return {LABEL + "source_digest": source_digest(root), LABEL + "vendor_pin": vendor_pin(),
            LABEL + "base_image": BASE_IMAGE,
            LABEL + "uv_lock_sha256": _sha((root / "vendor/openjarvis/uv.lock").read_bytes())}


def hardening_args() -> list[str]:
    """Run flags for every container started from this image."""
    return ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m"]


def _run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def inspect(ref: str) -> dict | None:
    r = _run(["docker", "image", "inspect", ref])
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)[0]
    except (ValueError, IndexError):
        return None


def label_problems(info: dict, root: Path = ROOT) -> list[str]:
    labels = (info.get("Config") or {}).get("Labels") or {}
    problems = [f"label {k} = {labels.get(k)!r}, expected {v!r}" for k, v in expected_labels(root).items()
                if labels.get(k) != v]
    if (info.get("Config") or {}).get("User") != RUNTIME_USER:
        problems.append("image does not run as the unprivileged gateway user")
    return problems


def local_image(ref: str = IMAGE_TAG, root: Path = ROOT) -> str:
    """Image id (sha256:…) of the verified local Gateway image for THIS source tree, else ImageError."""
    info = inspect(ref)
    if info is None:
        raise ImageError("GATEWAY_IMAGE_MISSING")
    labels = (info.get("Config") or {}).get("Labels") or {}
    if not labels.get(LABEL + "source_digest"):
        raise ImageError("GATEWAY_IMAGE_UNVERIFIED")       # not built by this procedure (e.g. a committed image)
    if label_problems(info, root):
        raise ImageError("GATEWAY_IMAGE_STALE")            # built from other sources than this tree
    image_id = info.get("Id") or ""
    if not image_id.startswith("sha256:"):
        raise ImageError("GATEWAY_IMAGE_UNVERIFIED")
    return image_id


# ------------------------------------------------------------------------------------------ build
def check_vendor(root: Path = ROOT) -> None:
    gitlink = _run(["git", "-C", str(root), "ls-tree", "HEAD", "vendor/openjarvis"]).stdout.split()
    if len(gitlink) < 3 or gitlink[2] != vendor_pin():
        raise ImageError("VENDOR_GITLINK_NOT_PIN")
    if _run(["git", "-C", str(root / "vendor/openjarvis"), "cat-file", "-e", vendor_pin() + "^{commit}"]).returncode:
        raise ImageError("VENDOR_PIN_COMMIT_UNAVAILABLE")


def pin_epoch(root: Path = ROOT) -> int:
    return int(_run(["git", "-C", str(root / "vendor/openjarvis"), "show", "-s", "--format=%ct", vendor_pin()]).stdout)


def stage_context(dest: Path, root: Path = ROOT) -> None:
    """Minimal, deterministic build context (explicit file lists; vendor from git at the pin; every timestamp set
    to the pin's commit time)."""
    for rel in RUNTIME_FILES:
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, dest / rel)
    for rel in BUILD_FILES:
        shutil.copyfile(root / rel, dest / Path(rel).name)
    archive = dest / "vendor.tar"
    r = _run(["git", "-C", str(root / "vendor/openjarvis"), "archive", "--format=tar", "-o", str(archive),
              vendor_pin(), *VENDOR_PATHS])
    if r.returncode:
        raise ImageError("VENDOR_ARCHIVE_FAILED")
    with tarfile.open(archive) as t:
        t.extractall(dest / "vendor/openjarvis", filter="data")
    archive.unlink()
    epoch = pin_epoch(root)
    for p in sorted(dest.rglob("*"), reverse=True):
        os.utime(p, (epoch, epoch), follow_symlinks=False)


def build(*, ca: Path | None = None, network: str | None = None, no_cache: bool = False, tag: str = IMAGE_TAG,
          root: Path = ROOT) -> dict:
    check_vendor(root)
    labels = expected_labels(root)
    with tempfile.TemporaryDirectory(prefix="rw-gw-ctx-") as tmp:
        ctx = Path(tmp)
        stage_context(ctx, root)
        ctx_files = sorted(str(p.relative_to(ctx)) for p in ctx.rglob("*") if p.is_file())
        context_digest = _sha("".join(f"{f}\0{_sha((ctx / f).read_bytes())}\n" for f in ctx_files).encode())
        cmd = ["docker", "buildx", "build", "-f", str(ctx / "Dockerfile"),
               "--build-arg", f"BASE_IMAGE={BASE_IMAGE}",
               "--build-arg", f"VENDOR_VERSION=0.0.0+g{vendor_pin()[:7]}",
               *sum((["--label", f"{k}={v}"] for k, v in sorted(labels.items())), [])]
        for var in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy"):
            if os.environ.get(var):              # Docker's predefined proxy args: not persisted in the image
                cmd += ["--build-arg", f"{var}={os.environ[var]}"]
        if ca:
            cmd += ["--secret", f"id=ca,src={Path(ca).resolve()}"]
        if network:
            cmd += ["--network", network]
        if no_cache:
            cmd.append("--no-cache")
        # Deterministic timestamps: the pin's commit time (layers re-stamped by BuildKit).
        cmd += ["--build-arg", f"SOURCE_DATE_EPOCH={pin_epoch(root)}",
                "--output", f"type=docker,name={tag},rewrite-timestamp=true"]
        r = subprocess.run(cmd + [str(ctx)], capture_output=True, text=True,
                           env={**os.environ, "DOCKER_BUILDKIT": "1"})
        if r.returncode:
            sys.stderr.write(r.stderr[-4000:])
            raise ImageError("GATEWAY_IMAGE_BUILD_FAILED")
    image_id = local_image(tag, root)
    checks = security_checks(image_id)
    manifest = {"image_tag": tag, "image_id": image_id, "source_digest": labels[LABEL + "source_digest"],
                "context_digest": context_digest, "context_files": len(ctx_files), "base_image": BASE_IMAGE,
                "vendor_pin": vendor_pin(), "uv_lock_sha256": labels[LABEL + "uv_lock_sha256"],
                "build_requirements": (root / BUILD_FILES[1]).read_text().splitlines()[1:],
                "runtime_user": RUNTIME_USER, "size_bytes": (inspect(image_id) or {}).get("Size"),
                "security_checks": checks,
                "repository_head": _run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    if checks["problems"]:
        raise ImageError("GATEWAY_IMAGE_SECURITY_CHECK_FAILED")
    return manifest


_PROBE = r"""
import importlib, importlib.metadata as md, importlib.util, json, os, stat, sys
out = {"uid": os.getuid(), "gid": os.getgid()}
setuid = []
for top in ("/usr", "/bin", "/sbin", "/opt", "/app", "/etc"):
    for d, _, files in os.walk(top):
        for f in files:
            p = os.path.join(d, f)
            try:
                m = os.lstat(p).st_mode
            except OSError:
                continue
            if stat.S_ISREG(m) and m & (stat.S_ISUID | stat.S_ISGID):
                setuid.append(p)
out["setuid_files"] = setuid
for mod in ("rightware.gateway.mcp_http", "rightware.gateway.model_tap", "rightware.gateway.verify",
            "rightware.gateway.synthetic.site"):
    importlib.import_module(mod)
out["imports_ok"] = True
out["labs_importable"] = importlib.util.find_spec("labs") is not None
try:
    open("/app/probe-write", "w").close(); out["app_writable"] = True
except OSError:
    out["app_writable"] = False
dists = sorted(f"{d.metadata['Name']}=={d.version}" for d in md.distributions())
out["distributions"] = len(dists)
out["distributions_sha256"] = __import__("hashlib").sha256("\n".join(dists).encode()).hexdigest()
out["python"] = sys.version.split()[0]
tree = __import__("hashlib").sha256()
for top in ("/opt/ojvenv", "/app/rightware"):          # content identity (paths + bytes, not timestamps)
    for d, dirs, files in sorted(os.walk(top)):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(d, f)
            if os.path.islink(p):
                tree.update(f"{p}->{os.readlink(p)}\n".encode())
            else:
                with open(p, "rb") as fh:
                    tree.update(f"{p}\0".encode() + __import__("hashlib").sha256(fh.read()).digest())
out["runtime_tree_sha256"] = tree.hexdigest()
print(json.dumps(out))
"""


def security_checks(image_id: str) -> dict:
    """Run the image offline with the production hardening flags and check its invariants."""
    r = _run(["docker", "run", "--rm", "--network", "none", *hardening_args(), image_id, "python", "-c", _PROBE])
    try:
        res = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"problems": ["probe did not run"], "stderr_tail": r.stderr[-500:]}
    problems = []
    if (res.get("uid"), res.get("gid")) != (10001, 10001):
        problems.append("runs as a privileged/unexpected user")
    if res.get("setuid_files"):
        problems.append("setuid/setgid files present")
    if not res.get("imports_ok"):
        problems.append("runtime modules not importable")
    if res.get("labs_importable"):
        problems.append("labs/ present in the runtime image")
    if res.get("app_writable"):
        problems.append("application directory writable")
    return {**res, "problems": problems}


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m rightware.gateway.image")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--ca", type=Path, help="TLS trust bundle for an outbound proxy (build secret, not stored)")
    b.add_argument("--network", default=None)
    b.add_argument("--no-cache", action="store_true")
    sub.add_parser("check")
    sub.add_parser("digest")
    a = p.parse_args(argv)
    try:
        if a.cmd == "digest":
            print(source_digest())
        elif a.cmd == "check":
            print(json.dumps({"image_id": local_image(), "source_digest": source_digest()}))
        else:
            print(json.dumps(build(ca=a.ca, network=a.network, no_cache=a.no_cache), indent=2))
    except ImageError as e:
        print(json.dumps({"error": str(e)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
