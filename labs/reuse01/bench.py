"""JRV-REUSE01-B latency benchmark (LAB, REAL local Ollama + qwen3.5:2b, offline, synthetic prompts only).

Same machine, same model, same prompts:
  A. raw Ollama /api/chat — cost of a runner reload when num_ctx alternates (4096 ↔ 16384) vs constant num_ctx;
  B. stock OpenJarvis path — pinned ``OllamaEngine.generate`` (upstream defaults: think=False, num_ctx default);
  C. RIGHTWARE product chat core — ToolChatAdapter (ModelRouter → direct LocalSimpleTextAdapter | AgentSession with
     calculator), in mode ``legacy`` (router/direct without the shared num_ctx = pre-REUSE01 behaviour) and ``shared``.
Each RIGHTWARE turn records the router seconds, route, total seconds and the number of runner loads Ollama logged.

    .runtime/gui/venv/bin/python -m labs.reuse01.bench --ollama-log <ollama.log> --out docs/evidence/reuse01/bench.json

No content of real conversations; prompts below are synthetic. Timings are 4 vCPU cloud CPU-only, not operator PC.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import time
import urllib.request
from pathlib import Path

MODEL = "qwen3.5:2b"
OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PROMPTS = [("conversa", "Olá JARVIS, como estás hoje?"),
           ("ferramenta", "Quanto é 12 vezes 7?"),
           ("conversa", "Dá-me uma dica curta para organizar o meu dia."),
           ("ferramenta", "Calcula 15% de 240."),
           ("conversa", "Obrigado, até logo.")]


def ollama(messages, num_ctx=None, num_predict=64):
    opts = {"temperature": 0, "num_predict": num_predict}
    if num_ctx:
        opts["num_ctx"] = num_ctx
    body = json.dumps({"model": MODEL, "stream": False, "think": False, "messages": messages,
                       "options": opts}).encode()
    t0 = time.monotonic()
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with OPEN.open(req, timeout=600) as r:
        d = json.loads(r.read())
    ns = 1e9
    return {"num_ctx": num_ctx or "ollama-default", "wall_s": round(time.monotonic() - t0, 2),
            "load_s": round(d.get("load_duration", 0) / ns, 2),
            "prompt_tokens": d.get("prompt_eval_count"), "prompt_s": round(d.get("prompt_eval_duration", 0) / ns, 2),
            "eval_tokens": d.get("eval_count"), "eval_s": round(d.get("eval_duration", 0) / ns, 2)}


def loads(log: Path | None) -> int:
    if not log or not log.exists():
        return -1
    return len(re.findall(r"loading model via llama-server", log.read_text(errors="replace")))


def part_a():
    msg = [{"role": "user", "content": "Responde numa frase: o que é um assistente pessoal?"}]
    alternating = [ollama(msg, n) for n in (16384, 4096, 16384, 4096)]
    constant = [ollama(msg, 16384) for _ in range(3)]
    return {"alternating_num_ctx": alternating, "constant_num_ctx": constant}


def part_b():
    from openjarvis.core.types import Message, Role
    from openjarvis.engine.ollama import OllamaEngine
    eng = OllamaEngine(host="http://127.0.0.1:11434", timeout=600)
    out = []
    for kind, text in PROMPTS:
        t0 = time.monotonic()
        r = eng.generate([Message(role=Role.USER, content=text)], model=MODEL, temperature=0.2, max_tokens=256)
        out.append({"kind": kind, "seconds": round(time.monotonic() - t0, 2),
                    "usage": r.get("usage") if isinstance(r, dict) else None})
    return out


def part_c(mode: str, log: Path | None):
    import rightware.assistant_tools as at
    from labs.m01 import acceptance as m01
    orig_shared = at.shared_num_ctx
    if mode == "legacy":
        at.shared_num_ctx = lambda: None  # type: ignore[assignment]
    # labs.m01.acceptance.build = same ToolChatAdapter + router + direct composition as the launcher (calculator)
    orig_direct = m01.LocalSimpleTextAdapter

    def direct(*a, **k):
        if mode == "shared":
            k["num_ctx"] = orig_shared()
        return orig_direct(*a, **k)
    m01.LocalSimpleTextAdapter = direct
    if mode == "legacy":
        orig_call = at.ModelRouter._ollama

        def legacy(self, user):  # pre-REUSE01 router body: no num_ctx (Ollama default)
            body = json.dumps({"model": self.model, "stream": False, "format": "json", "think": False,
                               "messages": [{"role": "system", "content": self.system},
                                            {"role": "user", "content": user}],
                               "options": {"temperature": 0, "num_predict": 20}}).encode()
            req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
            with OPEN.open(req, timeout=60) as r:
                return json.loads(r.read())["message"]["content"]
        at.ModelRouter._ollama = legacy
    import tempfile
    db = Path(tempfile.mkdtemp()) / "mem.sqlite3"
    adapter, _ = m01.build(MODEL, str(db), "lab:bench")
    out = []
    for kind, text in PROMPTS:
        l0 = loads(log)
        t0 = time.monotonic()
        reply = adapter.reply(text, ())
        last = adapter._last or {}
        out.append({"kind": kind, "route": last.get("route"), "router_s": (adapter.router.last or {}).get("seconds"),
                    "seconds": round(time.monotonic() - t0, 2), "runner_loads": loads(log) - l0 if l0 >= 0 else None,
                    "reply_chars": len(reply or "")})
    if mode == "legacy":
        at.ModelRouter._ollama = orig_call
    m01.LocalSimpleTextAdapter = orig_direct
    at.shared_num_ctx = orig_shared
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--ollama-log", type=Path)
    a.add_argument("--parts", default="a,b,c-legacy,c-shared")
    a.add_argument("--out", required=True)
    x = a.parse_args()
    res = {"mission": "JRV-REUSE01-B", "classification": "REAL local inference (lab, synthetic prompts, offline)",
           "model": MODEL, "machine": {"cpus": __import__("os").cpu_count(), "arch": platform.machine()},
           "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    parts = x.parts.split(",")
    Path(x.out).parent.mkdir(parents=True, exist_ok=True)

    def save():
        Path(x.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    if "a" in parts:
        res["A_raw_ollama"] = part_a()
        save()
    if "b" in parts:
        res["B_stock_openjarvis_engine"] = part_b()
        save()
    for mode in ("legacy", "shared"):
        if f"c-{mode}" in parts:
            res[f"C_rightware_{mode}"] = part_c(mode, x.ollama_log)
            save()
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save()
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
