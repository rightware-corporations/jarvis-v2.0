"""RIGHTWARE WORK-04 R2 — small REAL Qwen diagnostic on an existing local Ollama.

Separate experiment, NOT a repeat or revision of the historic WORK-04 0/35
benchmark. A pass on this smoke is not WORK-04 acceptance. No model pulls,
installs, paid APIs, cloud execution, real Windows actions or external data.
The original 35-scenario entry point and its thresholds are unmodified.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

LAB = Path(__file__).resolve().parent
REPO = LAB.parents[1]
PIN = "f21d902f4d3bd7f0f3f138f1a4613019a394b549"
HOST = "http://127.0.0.1:11434"
MODEL = "qwen3.5:4b"
OLLAMA_VERSION = "0.40.15"

# Preregistered order: start with the two demonstrated content-injection
# failures and one answer-only failure; only then broaden to 7 families.
CASES = (
    ("EVOL", 4001), ("HOSTILE", 4601), ("HOSTILE", 4604),
    ("MISSING", 4304), ("RECOVERY", 4501), ("CONTRA", 4102),
    ("TEMPORAL", 4202), ("CONSISTENT", 4401),
)


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def local_json(path: str) -> dict:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        HOST + path, timeout=15
    ) as response:
        return json.load(response)


def preflight(expected_sha: str, expected_digest: str) -> dict:
    if not expected_sha or not expected_digest:
        raise ValueError("both expected SHA and model digest are required")
    sha = run_git("rev-parse", "HEAD")
    if sha != expected_sha:
        raise RuntimeError("repository SHA differs from approved R2 revision")
    if run_git("status", "--porcelain", "--", "labs/work04_cognitive", "labs/work02_active_agent/w02lab"):
        raise RuntimeError("lab files modified locally; abort without inference")
    if run_git("ls-tree", "HEAD", "vendor/openjarvis").split()[2] != PIN:
        raise RuntimeError("submodule pin mismatch")
    if run_git("-C", "vendor/openjarvis", "rev-parse", "HEAD") != PIN:
        raise RuntimeError("submodule checkout mismatch")
    if not shutil.which("nvidia-smi"):
        raise RuntimeError("GPU required: this is not an authorized CPU experiment")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         capture_output=True, text=True, check=True).stdout.strip()
    if "Tesla T4" not in gpu:
        raise RuntimeError("expected Kaggle Tesla T4 GPU; do not silently change hardware")
    version = local_json("/api/version").get("version")
    if version != OLLAMA_VERSION:
        raise RuntimeError("Ollama version mismatch")
    tags = {m.get("name"): m for m in local_json("/api/tags").get("models", [])}
    if tags.get(MODEL, {}).get("digest") != expected_digest:
        raise RuntimeError("Qwen model digest mismatch")
    return {"repo_sha": sha, "openjarvis_pin": PIN, "ollama": version,
            "model": MODEL, "model_digest": expected_digest, "gpu": gpu}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-sha", default="")
    ap.add_argument("--expected-digest", default="")
    ap.add_argument("--n-cases", type=int, choices=(3, 8), default=3)
    ap.add_argument("--evidence-dir", default="")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args(argv)

    if args.plan_only:
        print(json.dumps({"experiment": "WORK04_R2_SMOKE_NOT_BENCHMARK",
                          "cases": CASES[:args.n_cases], "count": args.n_cases,
                          "models_called": False}, ensure_ascii=False))
        return 0

    for name in list(os.environ):
        key = name.upper()
        if key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY") or key.endswith(
            ("API_KEY", "AUTH_TOKEN", "_SECRET")
        ):
            os.environ.pop(name, None)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
    os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
    os.environ["OLLAMA_NO_CLOUD"] = "1"
    os.environ["JARVIS_NUM_CTX"] = "8192"
    sys.path.insert(0, str(LAB))

    info = preflight(args.expect_sha, args.expected_digest)
    from openjarvis.engine.ollama import OllamaEngine
    from w04lab import harness, scenarios

    out = Path(args.evidence_dir) if args.evidence_dir else (
        Path("/kaggle/working/jarvis_issa_evidence") /
        ("work04_r2_gpu_smoke_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    )
    # No overwrite even if this is retried: preserve every experiment.
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"experiment": "WORK04_R2_SMOKE_NOT_BENCHMARK",
                "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "mode": "QWEN REAL", "data": "SYNTHETIC ONLY",
                "benchmark_historical": "WORK04 QWEN REAL 0/35 NOT ACCEPTED — UNCHANGED",
                "criteria": "per-run completion+V2+ORACLE, NO benchmark acceptance threshold",
                "cases": list(CASES[:args.n_cases]), **info}
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    engine = OllamaEngine(host=HOST, timeout=600.0)
    cfg = harness.RunConfig(model=MODEL, timeout_seconds=1200.0)
    runs: list[dict] = []
    stopped_reason = None
    with (out / "runs.jsonl").open("w", encoding="utf-8") as fh:
        for family, seed in CASES[:args.n_cases]:
            try:
                run = harness.run_task(
                    lambda scn: engine, seed=seed, family=family,
                    cfg=cfg, keep_dir=out / "reports", mode_label="QWEN REAL R2 SMOKE"
                )
            except Exception as exc:
                stopped_reason = f"{type(exc).__name__}: {str(exc)[:160]}"
                print("SMOKE ERROR:", stopped_reason, flush=True)
                break
            fh.write(json.dumps(run, ensure_ascii=False, default=str) + "\n")
            fh.flush()
            runs.append(run)
            completion = run.get("completion", {})
            print(
                f"{family}-{seed} | {run['result']} | "
                f"{completion.get('completion_status')} | V2={run['v2']['result']} | "
                f"ORACLE={run['oracle']['result']} | "
                f"quarantine={len(run.get('quarantined_document_instructions', []))} | "
                f"seconds={run['latency']['total_s']}",
                flush=True,
            )
            if len(runs) == 1:
                loaded = local_json("/api/ps").get("models", [])
                vram = max((int(m.get("size_vram") or 0) for m in loaded), default=0)
                manifest["first_case_vram_bytes"] = vram
                if vram <= 0:
                    stopped_reason = "model was not resident in GPU VRAM"
                    break

    summary = {
        "experiment": manifest["experiment"],
        "mode": manifest["mode"], "historical_0_of_35_unchanged": True,
        "requested_cases": args.n_cases, "executed_cases": len(runs),
        "passed": sum(r.get("result") == "PASS" for r in runs),
        "failed": sum(r.get("result") != "PASS" for r in runs),
        "completion_statuses": [
            {"case": f"{r['family']}-{r['seed']}", "status": r.get("completion", {}).get("completion_status")}
            for r in runs
        ],
        "semantic_contamination": [
            {"case": f"{r['family']}-{r['seed']}",
             "fabricated": bool(r.get("fabricated")),
             "false_success": bool(r.get("false_success"))}
            for r in runs
        ],
        "security_violations": sum(any(r["violations"].values()) for r in runs),
        "stopped_reason": stopped_reason,
        "verdict": "DIAGNOSTIC ONLY — NOT WORK04 BENCHMARK ACCEPTANCE",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    zip_path = shutil.make_archive(str(out), "zip", root_dir=out)
    digest = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False), flush=True)
    print("EVIDENCE:", zip_path, "SHA256:", digest, flush=True)
    # A smoke is diagnostic: failures are measurements; nonzero only for
    # execution/environment errors, not because Qwen failed quality checks.
    return 2 if stopped_reason else 0


if __name__ == "__main__":
    raise SystemExit(main())
