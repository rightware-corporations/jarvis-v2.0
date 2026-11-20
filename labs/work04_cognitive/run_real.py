"""WORK-04 — single entry point for the cognitive-robustness benchmark.

    vendor/openjarvis/.venv/bin/python labs/work04_cognitive/run_real.py \
        --expect-sha <commit> --expected-digest <sha256> --allow-cpu

Criteria are fixed in w04lab/assess.py (spec §4), before any real run.
--fake validates the pipeline with scripted agents; its output is labelled
FAKE and is never evidence about the model.
Exit: 0 accepted, 1 not accepted, 2 preflight/environment.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import urllib.request

LAB = Path(__file__).resolve().parent
REPO = LAB.parents[1]
PIN = "f21d902f4d3bd7f0f3f138f1a4613019a394b549"
HOST = "http://127.0.0.1:11434"


def die(msg):
    print(f"PREFLIGHT FAIL: {msg}", file=sys.stderr)
    raise SystemExit(2)


def git(*a):
    return subprocess.check_output(["git", *a], cwd=REPO, text=True).strip()


def local_json(path):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(HOST + path, timeout=10) as r:
        return json.load(r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:4b")
    ap.add_argument("--expect-sha", default="")
    ap.add_argument("--expected-digest", default="")
    ap.add_argument("--n-per-family", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=1200.0)
    ap.add_argument("--engine-timeout", type=float, default=600.0)
    ap.add_argument("--allow-cpu", action="store_true")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--evidence-dir", default="")
    args = ap.parse_args(argv)
    for key in list(os.environ):
        up = key.upper()
        if up in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"} or up.endswith(("API_KEY", "AUTH_TOKEN", "_SECRET")):
            os.environ.pop(key)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
    os.environ.setdefault("JARVIS_NUM_CTX", "8192")

    sys.path.insert(0, str(LAB))
    from w04lab import assess, fake_engines, harness   # noqa: E402

    if args.n_per_family != assess.N_PER_FAMILY and not args.fake:
        die(f"real benchmark requires --n-per-family {assess.N_PER_FAMILY} (criteria fixed)")
    info = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": "FAKE" if args.fake else "QWEN REAL",
            "repo_sha": git("rev-parse", "HEAD"), "openjarvis_pin": PIN, "model": args.model,
            "num_ctx": int(os.environ["JARVIS_NUM_CTX"]), "think": False, "data": "SYNTHETIC ONLY",
            "allow_real_windows_actions": False, "log_transcript_text": False,
            "run_timeout_s": args.timeout, "engine_timeout_s": args.engine_timeout,
            "criteria": {k: getattr(assess, k) for k in dir(assess) if k.isupper()}}
    if args.expect_sha and not info["repo_sha"].startswith(args.expect_sha):
        die("repository SHA differs from --expect-sha")
    if git("status", "--porcelain", "--", "labs/work04_cognitive/w04lab", "labs/work04_cognitive/run_real.py",
           "labs/work02_active_agent/w02lab"):
        die("lab code has local modifications")
    if git("ls-tree", "HEAD", "vendor/openjarvis").split()[2] != PIN or \
            git("-C", "vendor/openjarvis", "rev-parse", "HEAD") != PIN:
        die("OpenJarvis pin drift")
    if not args.fake:
        if not args.expected_digest:
            die("--expected-digest is required for a real run")
        try:
            info["ollama"] = local_json("/api/version").get("version")
            tags = {m["name"]: m for m in local_json("/api/tags").get("models", [])}
        except Exception as exc:
            die(f"Ollama not reachable ({type(exc).__name__})")
        if args.model not in tags:
            die("model not installed; this script never pulls")
        info["model_digest"] = tags[args.model].get("digest")
        if info["model_digest"] != args.expected_digest:
            die(f"model digest {info['model_digest']} != expected {args.expected_digest}")
        gpu = None
        if shutil.which("nvidia-smi"):
            gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                 capture_output=True, text=True).stdout.strip() or None
        if gpu is None and not args.allow_cpu:
            die("no GPU; pass --allow-cpu explicitly")
        info["gpu"] = gpu or "CPU ONLY"

    plan = assess.plan(args.n_per_family)
    variety = assess.input_fingerprints(plan)
    if not variety["distinct"]:
        die("inputs are not pairwise distinct")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.evidence_dir) if args.evidence_dir else LAB / "evidence" / f"{info['mode'].split()[0].lower()}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "inputs.json").write_text(json.dumps(variety, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in info.items() if k != "criteria"}, ensure_ascii=False), flush=True)

    if args.fake:
        factory = fake_engines.honest
    else:
        from openjarvis.engine.ollama import OllamaEngine
        shared = OllamaEngine(host=HOST, timeout=args.engine_timeout)
        factory = lambda scn: shared   # noqa: E731
    cfg = harness.RunConfig(model=args.model, timeout_seconds=args.timeout)
    runs, rows = [], []
    with (out / "runs.jsonl").open("w", encoding="utf-8") as jl:
        for fam, seed in plan:
            ev = harness.run_task(factory, seed=seed, family=fam, cfg=cfg, keep_dir=out / "reports",
                                  mode_label=info["mode"])
            jl.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
            jl.flush()
            runs.append(ev)
            calls = " > ".join(f"{t['tool']}{'' if t['success'] else '✗'}" for t in ev["trace"])
            rows.append((f"{fam}-{seed}", ev["request_style"], calls or "(nenhuma)", ev["v2"]["result"],
                         ev["oracle"]["result"], ev["result"], ev["failure_class"] or "-", ev["latency"]["total_s"]))
            print(" | ".join(map(str, rows[-1])), flush=True)
    verdict = assess.assess(runs, inputs_distinct=variety["distinct"])
    steps = [s["seconds"] for r in runs for s in r["engine_steps"] if not s.get("halted")]
    from w04lab.harness import _pctl
    summary = {"mode": info["mode"], "model": args.model, "digest": info.get("model_digest"),
               "repo_sha": info["repo_sha"], "pin": PIN, "pass": f"{verdict['k']}/{verdict['n']}",
               "gates": verdict["gates"], "evaluator_disagreements": verdict["evaluator_disagreements"],
               "step_latency_s": {"p50": _pctl(steps, .5), "p95": _pctl(steps, .95), "n": len(steps)},
               "run_total_s_mean": round(statistics.mean(r["latency"]["total_s"] for r in runs), 2),
               "verdict": ("SCRIPT VALIDATED (FAKE) — not evidence of model capability" if args.fake else
                           ("ACCEPTED" if verdict["accepted"] else "NOT ACCEPTED") + " (QWEN REAL)")}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    table = ["| RUN | PEDIDO | CHAMADAS | V2 | ORÁCULO | RESULTADO | FALHA | TEMPO (s) |",
             "|---|---|---|---|---|---|---|---:|"] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]
    (out / "SUMMARY.md").write_text(f"# WORK-04 — {info['mode']}\n\n```json\n"
                                    f"{json.dumps(summary, indent=2, ensure_ascii=False, default=str)}\n```\n\n"
                                    + "\n".join(table) + "\n", encoding="utf-8")
    print("SUMMARY:", json.dumps({k: summary[k] for k in ("mode", "pass", "verdict")}, ensure_ascii=False))
    for g, v in verdict["gates"].items():
        print(f"  {g}: {v['value']} (threshold {v['threshold']}) -> {'OK' if v['ok'] else 'FAIL'}")
    shutil.make_archive(str(out), "zip", root_dir=out)
    return 0 if (verdict["accepted"] or args.fake) else 1


if __name__ == "__main__":
    raise SystemExit(main())
