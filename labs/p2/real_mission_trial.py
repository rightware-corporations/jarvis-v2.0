"""JRV-P2 Gate 5: REAL goose mission through the exact product entry, in a pseudo-terminal.

`python jarvis.py console --model M --missao-goose --goose-bin B --goose-ollama-dir O --goose-models-dir D
 --goose-model G` → /tarefas → /tarefa pesquisa-fixture-goose → /autorizar <code read from the screen> →
/estado → /sair. Records terminal output + latency; the adapter's evidence dir is reported by path (local only).
Usage: python labs/p2/real_mission_trial.py --goose-bin B --ollama-dir O --models-dir D --out OUT.json
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


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--goose-bin", required=True)
    p.add_argument("--ollama-dir", required=True)
    p.add_argument("--models-dir", required=True)
    p.add_argument("--goose-model", default="qwen3.5:4b")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True).stdout.strip())
    cmd = [sys.executable, "jarvis.py", "console", "--model", "qwen3.5:2b", "--missao-goose", "--goose-bin", a.goose_bin,
           "--goose-ollama-dir", a.ollama_dir, "--goose-models-dir", a.models_dir, "--goose-model", a.goose_model]
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(ROOT)
        os.execvp(cmd[0], cmd)
    t0 = time.monotonic()

    def pump(timeout):
        seg, end = b"", time.monotonic() + timeout
        while time.monotonic() < end:
            r, _, _ = select.select([fd], [], [], 0.2)
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

    transcript, _ = pump(60)
    steps = []
    for line in ["/tarefas", "/tarefa pesquisa-fixture-goose", "<code>", "/estado", "/sair"]:
        if line == "<code>":
            codes = re.findall(r"/autorizar ([0-9A-F]{6})", transcript)
            line = f"/autorizar {codes[-1]}" if codes else "/autorizar 000000"
        t = time.monotonic()
        os.write(fd, (line + "\n").encode())
        out, how = pump(1800)
        transcript += out
        steps.append({"input": "/autorizar <código mostrado pelo anfitrião>" if line.startswith("/autorizar") else line,
                      "seconds": round(time.monotonic() - t, 2), "end": how,
                      "labels": re.findall(r"\[(.+?)\]", out), "output": out.replace("\r", "")})
        print(steps[-1]["input"], steps[-1]["seconds"], how, steps[-1]["labels"], flush=True)
        if how == "EOF":
            break
    try:
        _, status = os.waitpid(pid, 0)
        code = os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        code = None
    missions = sorted((ROOT / ".runtime" / "goose-missions").glob("p2-*"), key=lambda p: p.stat().st_mtime)
    res = {"kind": "REAL goose mission through the product console (JRV-P2 Gate 5)", "repository_head": head,
           "tracked_tree_dirty": dirty, "goose_model": a.goose_model, "exit_code": code,
           "total_seconds": round(time.monotonic() - t0, 2), "steps": steps,
           "evidence_dir_local": str(missions[-1]) if missions else None}
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("exit", code, "head", head[:12], "dirty", dirty, "evidence", res["evidence_dir_local"])


if __name__ == "__main__":
    main()
