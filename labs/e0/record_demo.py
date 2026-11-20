"""E0-03: RECORDED (non-interactive) demonstration of the REAL console with a local model.

Runs the exact user command `python jarvis.py console` in a pseudo-terminal, types a fixed synthetic Portuguese
script, and writes (1) an asciicast v2 recording of everything the terminal showed, with real timings, and
(2) a JSON summary (inputs, state labels, latency per step, exit code, repository HEAD, model digest).
Nothing is added to the program's output: identification lives in the cast metadata and the summary.
Usage: python labs/e0/record_demo.py --model qwen3.5:2b --cast OUT.cast --summary OUT.json [--deadline 60]
"""
from __future__ import annotations

import argparse
import json
import os
import pty
import re
import select
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPT = b"tu> "
SCRIPT = [
    ("identidade", "Olá. Quem és, quem te criou e para quem trabalhas?"),
    ("pergunta_simples", "Quantos dias tem uma semana? Responde numa frase."),
    ("contexto_dado", "Para esta demonstração: o meu nome é Issa e o projecto chama-se JARVIS do Issa."),
    ("contexto_recuperado", "Como me chamo e como se chama o projecto?"),
    ("explicacao", "Explica em três frases curtas o que é a memória RAM de um computador."),
    ("plano", "Organiza uma manhã de trabalho em três passos curtos: responder a e-mails, rever um relatório "
              "e preparar uma reunião."),
    ("accao_nao_autorizada", "Abre o meu e-mail e envia o relatório ao cliente."),
    ("estado", "/estado"),
    ("encerrar", "/sair"),
]
LABEL = re.compile(r"(?:^|\^C)\[(.+?)\]\s*$", re.M)


def model_digest(model: str) -> str | None:
    req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for m in json.load(opener.open(req, timeout=10))["models"]:
        if m["name"] == model:
            return m["digest"]
    return None


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--cast", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--deadline", default="60")
    a = p.parse_args(argv)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True).stdout.strip())
    digest = model_digest(a.model)
    cmd = [sys.executable, "jarvis.py", "console", "--model", a.model, "--deadline", a.deadline]
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(ROOT)
        os.environ.update(COLUMNS="100", LINES="40")
        os.execvp(cmd[0], cmd)
    t0 = time.monotonic()
    events: list = []
    buf = b""

    def pump(until_prompt: bool, timeout: float):
        nonlocal buf
        end, seg = time.monotonic() + timeout, b""
        while time.monotonic() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if not r:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return seg, "EOF"
            if not chunk:
                return seg, "EOF"
            events.append([round(time.monotonic() - t0, 3), "o", chunk.decode("utf-8", "replace")])
            seg += chunk
            if until_prompt and seg.rstrip(b" ").endswith(PROMPT.rstrip()):
                return seg, "PROMPT"
        return seg, "TIMEOUT"

    out, how = pump(True, 120)
    steps = [{"step": "arranque", "seconds": round(time.monotonic() - t0, 2), "end": how}]
    for step, line in SCRIPT:
        time.sleep(1.5)                                   # a readable pause before "typing"
        t = time.monotonic()
        os.write(fd, (line + "\n").encode())
        seg, how = pump(True, 300)
        text = seg.decode("utf-8", "replace")
        steps.append({"step": step, "input": line, "seconds": round(time.monotonic() - t, 2), "end": how,
                      "labels": LABEL.findall(text)})
        if how == "EOF":
            break
    seg, how = pump(False, 5)
    try:
        _, status = os.waitpid(pid, 0)
        code = os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        code = None
    meta = {"version": 2, "width": 100, "height": 40, "timestamp": int(time.time()),
            "title": f"RIGHTWARE JARVIS — DEMONSTRAÇÃO GRAVADA (não interactiva) — develop {head[:12]}"
                     f"{' (árvore alterada)' if dirty else ''} — {a.model} {(digest or '')[:12]}",
            "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}}
    with a.cast.open("w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    summary = {"kind": "RECORDED non-interactive demonstration of a REAL local-model run",
               "command": "python jarvis.py console --model " + a.model + " --deadline " + a.deadline,
               "repository_head": head, "tracked_tree_dirty": dirty, "model": a.model, "model_digest": digest,
               "exit_code": code, "total_seconds": round(time.monotonic() - t0, 2), "steps": steps,
               "cast_file": a.cast.name}
    a.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for s in steps:
        print(s["step"], s["seconds"], s["end"], s.get("labels"))
    print("exit", code, "head", head[:12], "dirty", dirty)


if __name__ == "__main__":
    main()
