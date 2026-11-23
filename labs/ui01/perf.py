"""UI-01 B2.5: response times of the GUI conversation path (REAL Qwen), cold and warm, N per condition.

python3 labs/ui01/perf.py OUT.json [--n 10] [--model qwen3.5:2b] [--port 8000]

* GUI path: POST /v1/chat/completions (stream=true) on the RIGHTWARE GUI server — exactly what the original GUI
  sends. Measured: time to first content chunk (the RIGHTWARE bridge is not token-streaming, so TTFT == time to the
  whole answer; reported as such) and total time.
* cold: the model is unloaded from Ollama (keep_alive=0) before EACH request; warm: model kept loaded.
* model throughput: the same prompts sent directly to Ollama /api/chat with the bridge's generation options
  (num_ctx 4096, num_predict 256, temperature 0.2) to read eval_count/eval_duration (tokens/s). Labelled as model
  level, not GUI level.
* Distinct inputs: each prompt asks a different sum; the correct number in the answer is checked (evidence that
  answers are generated per input, not canned).
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(url, payload, timeout=600):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    return NOPROXY.open(req, timeout=timeout)


def unload(model):
    post(f"{OLLAMA}/api/generate", {"model": model, "keep_alive": 0}).read()
    for _ in range(60):
        ps = json.loads(NOPROXY.open(f"{OLLAMA}/api/ps", timeout=10).read())
        if not any(m.get("name") == model for m in ps.get("models", [])):
            return
        time.sleep(0.5)


def gui_request(port, model, prompt):
    t0 = time.monotonic()
    first, text, rid = None, "", None
    with post(f"http://127.0.0.1:{port}/v1/chat/completions",
              {"model": model, "stream": True, "messages": [{"role": "user", "content": prompt}]}) as r:
        rid = r.headers.get("x-rightware-request-id")
        for raw in r:
            line = raw.decode("utf-8").strip()
            if line.startswith("data: {") and '"choices"' in line:
                delta = json.loads(line[6:])["choices"][0]["delta"].get("content")
                if delta:
                    first = first or time.monotonic() - t0
                    text += delta
    return {"rid": rid, "ttft_s": round(first or 0, 3), "total_s": round(time.monotonic() - t0, 3),
            "answer_head": text.split("\n")[0][:160], "error": "Erro de inferência" in text}


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, max(0, round(p / 100 * len(xs) + 0.5) - 1))], 3) if xs else None


def summary(rows, key):
    xs = [r[key] for r in rows if not r.get("error")]
    return {"n_ok": len(xs), "n_err": sum(1 for r in rows if r.get("error")), "p50": pct(xs, 50), "p95": pct(xs, 95),
            "min": min(xs) if xs else None, "max": max(xs) if xs else None,
            "mean": round(statistics.mean(xs), 3) if xs else None}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("out")
    a.add_argument("--n", type=int, default=10)
    a.add_argument("--model", default="qwen3.5:2b")
    a.add_argument("--port", type=int, default=8000)
    args = a.parse_args()
    prompts = [f"Responde numa frase curta em português: quanto é {10 + i} mais {20 + 2 * i}?" for i in range(args.n)]
    expect = [str(30 + 3 * i) for i in range(args.n)]
    res = {"kind": "UI-01 B2.5 performance (REAL qwen via the RIGHTWARE GUI API)", "model": args.model,
           "host": {"cpu_count": __import__("os").cpu_count(), "machine": platform.machine(), "gpu": "none detected"},
           "options": {"num_ctx": 4096, "num_predict": 256, "temperature": 0.2, "bridge_streaming": False}}
    tags = json.loads(NOPROXY.open(f"{OLLAMA}/api/tags", timeout=10).read())
    res["model_digest"] = next((m["digest"] for m in tags["models"] if m["name"] == args.model), None)
    cold = []
    for i, p in enumerate(prompts):
        unload(args.model)
        r = gui_request(args.port, args.model, p)
        r["correct"] = expect[i] in r["answer_head"]
        cold.append(r)
        print("cold", i, r, flush=True)
    warm = []
    gui_request(args.port, args.model, "Olá.")                           # make sure it is loaded
    for i, p in enumerate(prompts):
        r = gui_request(args.port, args.model, p)
        r["correct"] = expect[i] in r["answer_head"]
        warm.append(r)
        print("warm", i, r, flush=True)
    direct = []
    for p in prompts:
        d = json.loads(post(f"{OLLAMA}/api/chat", {"model": args.model, "stream": False,
                                                   "messages": [{"role": "user", "content": p}],
                                                   "options": {"num_ctx": 4096, "num_predict": 256,
                                                               "temperature": 0.2}}).read())
        direct.append({"eval_count": d.get("eval_count"), "eval_s": round(d.get("eval_duration", 0) / 1e9, 3),
                       "tokens_per_s": round(d["eval_count"] / (d["eval_duration"] / 1e9), 2)
                       if d.get("eval_duration") else None,
                       "load_s": round(d.get("load_duration", 0) / 1e9, 3)})
    res.update({"cold": cold, "warm": warm, "direct_ollama": direct,
                "summary": {"cold_total": summary(cold, "total_s"), "cold_ttft": summary(cold, "ttft_s"),
                            "warm_total": summary(warm, "total_s"), "warm_ttft": summary(warm, "ttft_s"),
                            "tokens_per_s": summary([{"v": d["tokens_per_s"]} for d in direct if d["tokens_per_s"]], "v"),
                            "correct_answers": {"cold": sum(r["correct"] for r in cold),
                                                "warm": sum(r["correct"] for r in warm), "n": args.n},
                            "distinct_answers_warm": len({r["answer_head"] for r in warm})}})
    Path(args.out).write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(res["summary"], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
