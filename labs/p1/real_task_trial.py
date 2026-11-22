"""JRV-P1 Gate 4: REAL local-model supervised task through the exact product entry, in a pseudo-terminal.

Runs `python jarvis.py console --model M --tarefa-ensaio`, lists capabilities, requests the synthetic comparison,
reads the host code from the screen and types `/autorizar <code>`, then `/estado` and `/sair`. Records the whole
terminal output and per-step latency. Synthetic files only (host-written temp dir); no personal data.
Usage: python labs/p1/real_task_trial.py --model qwen3.5:4b --out OUT.json
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPT = b"tu> "
LABEL = re.compile(r"(?:^|\^C)\[(.+?)\]", re.M)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True).stdout.strip())
    cmd = [sys.executable, "jarvis.py", "console", "--model", a.model, "--tarefa-ensaio", "--deadline", "120"]
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(ROOT)
        os.execvp(cmd[0], cmd)
    t0 = time.monotonic()

    def pump(timeout):
        seg, end = b"", time.monotonic() + timeout
        while time.monotonic() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if not r:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return seg.decode("utf-8", "replace"), "EOF"
            if not chunk:
                return seg.decode("utf-8", "replace"), "EOF"
            seg += chunk
            if seg.rstrip(b" ").endswith(PROMPT.rstrip()):
                return seg.decode("utf-8", "replace"), "PROMPT"
        return seg.decode("utf-8", "replace"), "TIMEOUT"

    banner, _ = pump(60)
    steps, transcript = [], banner
    plan = ["/tarefas", "/tarefa comparar-versoes-ensaio", "<code>", "/estado", "/sair"]
    for line in plan:
        if line == "<code>":
            codes = re.findall(r"/autorizar ([0-9A-F]{6})", transcript)
            line = f"/autorizar {codes[-1]}" if codes else "/autorizar 000000"
        t = time.monotonic()
        os.write(fd, (line + "\n").encode())
        out, how = pump(600)
        transcript += out
        steps.append({"input": line if not line.startswith("/autorizar") else "/autorizar <código mostrado pelo anfitrião>",
                      "seconds": round(time.monotonic() - t, 2), "end": how, "labels": LABEL.findall(out),
                      "output": out.replace("\r", "")})
        if how == "EOF":
            break
    try:
        _, status = os.waitpid(pid, 0)
        code = os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        code = None
    res = {"kind": "REAL local-model supervised task (JRV-P1 Gate 4)", "command": " ".join(cmd[1:]),
           "repository_head": head, "tracked_tree_dirty": dirty, "model": a.model, "exit_code": code,
           "total_seconds": round(time.monotonic() - t0, 2), "steps": steps}
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    for s in steps:
        print(s["input"], s["seconds"], s["end"], s["labels"])
    print("exit", code, "head", head[:12], "dirty", dirty)


if __name__ == "__main__":
    main()
