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
# CPU is allowed only when requested explicitly (--device cpu), on a runner
# comparable to the WORK-03 GitHub-hosted CPU proof (4 vCPU, ~15.6 GiB RAM).
MIN_CPU_RAM_GIB = 14
MIN_CPU_COUNT = 4

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


def loopback_only(listeners: list[str]) -> bool:
    """A serving socket must exist and bind only on the local loopback."""
    return bool(listeners) and all(ip in ("127.0.0.1", "::1") for ip in listeners)


def validate_ollama_binding() -> list[str]:
    # OpenJarvis's pinned environment includes psutil, so examine socket
    # listeners rather than trusting environment variables alone.
    import psutil
    addresses = [
        conn.laddr.ip for conn in psutil.net_connections(kind="inet")
        if conn.status == psutil.CONN_LISTEN
        and conn.laddr and conn.laddr.port == 11434
    ]
    if not loopback_only(addresses):
        raise RuntimeError("Ollama must LISTEN exclusively on 127.0.0.1/::1")
    return addresses


def residency_ok(models: list[dict], device: str) -> tuple[bool, int, int]:
    """Qwen must be loaded; on GPU with VRAM, on CPU with NO VRAM (no silent offload)."""
    match = [m for m in models if m.get("name") == MODEL]
    size = max((int(m.get("size") or 0) for m in match), default=0)
    vram = max((int(m.get("size_vram") or 0) for m in match), default=0)
    ok = size > 0 and (vram > 0 if device == "gpu" else vram == 0)
    return ok, size, vram


def validate_model_residency(device: str = "gpu") -> dict:
    """Warm the local model and confirm where it is resident before case 1.

    This is an extra short REAL Qwen call for environment preflight, not a
    benchmark case; it is recorded in the manifest.
    """
    req = urllib.request.Request(
        HOST + "/api/generate",
        data=json.dumps({
            "model": MODEL, "prompt": "Responde apenas: pronto.",
            "stream": False, "think": False, "keep_alive": "10m",
            "options": {"num_ctx": 8192, "num_predict": 8},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=180 if device == "gpu" else 600) as response:
        warm = json.load(response)
    if warm.get("error"):
        raise RuntimeError(f"Ollama returned an error during {device.upper()} preflight")
    ok, size, vram = residency_ok(local_json("/api/ps").get("models", []), device)
    if not ok:
        raise RuntimeError("Qwen not resident in GPU VRAM after preflight generation" if device == "gpu"
                           else "Qwen not resident on CPU-only memory after preflight generation")
    return {
        "warmup_real_inference": True,
        "preflight_model_bytes": size,
        "preflight_vram_bytes": vram,
        "warmup_response_tokens": warm.get("eval_count"),
    }


def cpu_resources() -> dict:
    """Explicit CPU mode: verify the runner matches the authorised CPU envelope."""
    mem_kib = 0
    with open("/proc/meminfo", encoding="ascii") as fh:
        for line in fh:
            if line.startswith("MemTotal:"):
                mem_kib = int(line.split()[1])
    ram_gib = mem_kib / 1048576
    cpus = os.cpu_count() or 0
    if ram_gib < MIN_CPU_RAM_GIB or cpus < MIN_CPU_COUNT:
        raise RuntimeError(f"CPU runner below envelope ({cpus} CPU, {ram_gib:.1f} GiB RAM)")
    model = ""
    with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break
    return {"cpu_count": cpus, "ram_gib": round(ram_gib, 1), "cpu_model": model}


def preflight(expected_sha: str, expected_digest: str, device: str = "gpu") -> dict:
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
    if device == "gpu":
        if not shutil.which("nvidia-smi"):
            raise RuntimeError("GPU required: pass --device cpu explicitly for a CPU experiment")
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, check=True).stdout.strip()
        if "Tesla T4" not in gpu:
            raise RuntimeError("expected Kaggle Tesla T4 GPU; do not silently change hardware")
        hardware = {"gpu": gpu}
    elif device == "cpu":
        hardware = {"gpu": "CPU ONLY (explicit --device cpu)", **cpu_resources()}
    else:
        raise ValueError(f"unknown device {device!r}")
    version = local_json("/api/version").get("version")
    if version != OLLAMA_VERSION:
        raise RuntimeError("Ollama version mismatch")
    tags = {m.get("name"): m for m in local_json("/api/tags").get("models", [])}
    if tags.get(MODEL, {}).get("digest") != expected_digest:
        raise RuntimeError("Qwen model digest mismatch")
    bind_addresses = validate_ollama_binding()
    warmed = validate_model_residency(device)
    return {"repo_sha": sha, "openjarvis_pin": PIN, "ollama": version,
            "model": MODEL, "model_digest": expected_digest, "device": device, **hardware,
            "ollama_listen_addresses": bind_addresses, **warmed}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-sha", default="")
    ap.add_argument("--expected-digest", default="")
    ap.add_argument("--n-cases", type=int, choices=(1, 3, 8), default=3)
    ap.add_argument("--device", choices=("gpu", "cpu"), default="gpu",
                    help="gpu (Kaggle T4, default) or cpu (explicit; GitHub-hosted runner)")
    ap.add_argument("--evidence-dir", default="")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--preflight-only", action="store_true",
                    help="run the full preflight (incl. one short warm-up generation), record it, run no scenario")
    args = ap.parse_args(argv)

    if args.plan_only:
        print(json.dumps({"experiment": "WORK04_R2_SMOKE_NOT_BENCHMARK",
                          "cases": CASES[:args.n_cases], "count": args.n_cases,
                          "device": args.device, "models_called": False}, ensure_ascii=False))
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

    if args.device == "cpu" and not args.evidence_dir:
        raise SystemExit("--device cpu requires an explicit --evidence-dir")
    info = preflight(args.expect_sha, args.expected_digest, args.device)
    from openjarvis.engine.ollama import OllamaEngine
    from w04lab import harness_r2 as harness, smoke_metrics_r2

    out = Path(args.evidence_dir) if args.evidence_dir else (
        Path("/kaggle/working/jarvis_issa_evidence") /
        ("work04_r2_gpu_smoke_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    )
    # No overwrite even if this is retried: preserve every experiment.
    out.mkdir(parents=True, exist_ok=False)
    if args.preflight_only:
        (out / "preflight.json").write_text(json.dumps(
            {"experiment": "WORK04_R2_SMOKE_PREFLIGHT_ONLY", "scenarios_run": 0,
             "utc": dt.datetime.now(dt.timezone.utc).isoformat(), **info},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print("PREFLIGHT OK:", json.dumps(info, ensure_ascii=False), flush=True)
        return 0
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
                stub = {
                    "family": family, "seed": seed, "result": "NOT_EVALUATED",
                    "failure_class": "HARNESS", "error": stopped_reason,
                    "mode": "QWEN REAL R2 SMOKE",
                    "trace": [], "completion": {"completion_status": "NOT_EVALUATED"},
                    "semantic_audit": {"report_evaluated": False},
                    "violations": {},
                }
                fh.write(json.dumps(stub, ensure_ascii=False) + "\n")
                fh.flush()
                runs.append(stub)
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
                ok, size, vram = residency_ok(local_json("/api/ps").get("models", []), args.device)
                manifest["first_case_vram_bytes"] = vram
                manifest["first_case_model_bytes"] = size
                if not ok and args.device == "gpu":
                    stopped_reason = "model was not resident in GPU VRAM"
                    break
                if not ok and size > 0:   # CPU mode: unexpected VRAM offload
                    stopped_reason = "CPU experiment unexpectedly offloaded to VRAM"
                    break

    summary = smoke_metrics_r2.summarize(
        runs, requested=args.n_cases, stopped_reason=stopped_reason
    )
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
