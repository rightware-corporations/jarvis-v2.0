"""UI-01 B1.4/B1.6: prove the GUI process starts with NO automatic effects (no outbound traffic, no scheduler/
workers, no child processes, no files written outside its own config dir), under real execution.

Run with the GUI runtime python:  PYTHONPATH=. .runtime/gui/venv/bin/python labs/ui01/startup_audit.py OUT.json
* every outbound HTTP(S) attempt is forced through a local DECOY proxy that records it and answers 403;
* HOME and OPENJARVIS_HOME point to fresh temporary directories, diffed before/after;
* the server is exercised (GUI page, assets, models, health, info, analytics identity, denied routes) and then
  observed idle for 20 s; sockets (/proc/net/tcp + fd inodes), threads and children are sampled.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORT = 8011


class Decoy(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def _any(self):
        Decoy.seen.append({"method": self.command, "target": self.path[:200]})
        self.send_response(403)
        self.end_headers()

    do_GET = do_POST = do_CONNECT = do_PUT = do_HEAD = _any

    def log_message(self, *a):
        pass


def snapshot(d: Path) -> dict:
    return {str(p.relative_to(d)): p.stat().st_size for p in d.rglob("*") if p.is_file()}


def sockets(pid: int) -> list:
    inodes = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            t = os.readlink(fd)
        except OSError:
            continue
        if t.startswith("socket:["):
            inodes.add(t[8:-1])
    out = []
    for table in ("tcp", "tcp6"):
        tf = Path(f"/proc/net/{table}")
        for line in (tf.read_text().splitlines()[1:] if tf.exists() else []):
            f = line.split()
            if f[9] in inodes:
                out.append({"local": f[1], "remote": f[2], "state": f[3], "table": table})
    return out


def hexaddr_is_loopback(a: str) -> bool:
    ip = a.split(":")[0]
    return ip in ("0100007F", "00000000") or ip.endswith("0100007F") or set(ip) <= {"0"}


def main(out_path: str) -> int:
    decoy = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Decoy)
    threading.Thread(target=decoy.serve_forever, daemon=True).start()
    proxy = f"http://127.0.0.1:{decoy.server_address[1]}"
    home, ojhome = Path(tempfile.mkdtemp(prefix="ui01-home-")), Path(tempfile.mkdtemp(prefix="ui01-oj-"))
    shutil.copyfile(ROOT / "configs/gui/openjarvis-gui.toml", ojhome / "config.toml")
    rt = ROOT / ".runtime/gui"
    before_home, before_oj = snapshot(home), snapshot(ojhome)
    git_before = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
    env = {**{k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")},
           "HOME": str(home), "HTTPS_PROXY": proxy, "HTTP_PROXY": proxy, "https_proxy": proxy, "http_proxy": proxy,
           "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "PYTHONPATH": str(ROOT)}
    code = ("import sys; from pathlib import Path; from rightware.gui import server as S, runtime as R;"
            f"p=R.paths(); p['home']=Path({str(ojhome)!r});"
            "R.paths=lambda runtime=None, _p=p: _p;"
            f"app,_=S.build_app(port={PORT}, models=['qwen3.5:2b','qwen3.5:4b'], trial=True);"
            f"S.serve(app,{PORT})")
    proc = subprocess.Popen([str(rt / "venv/bin/python"), "-c", code], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    t0 = time.time()
    while time.time() - t0 < 60:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    startup_s = round(time.time() - t0, 2)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    exercised = {}
    for method, path in (("GET", "/"), ("GET", "/v1/models"), ("GET", "/health"), ("GET", "/v1/info"),
                         ("GET", "/v1/analytics/identity"), ("GET", "/v1/managed-agents"), ("POST", "/v1/agents"),
                         ("GET", "/v1/telemetry/stats"), ("POST", "/api/research")):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                     data=b"{}" if method == "POST" else None,
                                     headers={"Content-Type": "application/json"})
        try:
            exercised[f"{method} {path}"] = opener.open(req, timeout=10).status
        except urllib.error.HTTPError as e:
            exercised[f"{method} {path}"] = e.code
    samples = []
    for _ in range(4):
        time.sleep(5)
        threads = sorted(Path(f"/proc/{proc.pid}/task/{t}/comm").read_text().strip()
                         for t in os.listdir(f"/proc/{proc.pid}/task"))
        children = subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True, text=True).stdout.split()
        samples.append({"threads": threads, "children": children, "sockets": sockets(proc.pid)})
    proc.terminate()
    try:
        log = proc.communicate(timeout=15)[0]
    except subprocess.TimeoutExpired:
        proc.kill()
        log = proc.communicate()[0]
    decoy.shutdown()
    after_home, after_oj = snapshot(home), snapshot(ojhome)
    git_after = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
    non_loopback = [s for smp in samples for s in smp["sockets"]
                    if not hexaddr_is_loopback(s["remote"]) or not hexaddr_is_loopback(s["local"])]
    result = {
        "kind": "UI-01 startup audit (REAL process, decoy proxy, temp HOME/OPENJARVIS_HOME)",
        "startup_seconds": startup_s, "exercised": exercised,
        "outbound_attempts_via_proxy": Decoy.seen,
        "non_loopback_sockets": non_loopback,
        "thread_names_last_sample": samples[-1]["threads"], "max_threads": max(len(s["threads"]) for s in samples),
        "child_processes": sorted({c for s in samples for c in s["children"]}),
        "files_created_in_HOME": sorted(set(after_home) - set(before_home)),
        "files_created_in_OPENJARVIS_HOME": sorted(set(after_oj) - set(before_oj)),
        "repository_status_changed": git_before != git_after,
        "server_log_tail": log.splitlines()[-12:],
    }
    result["clean"] = (not result["outbound_attempts_via_proxy"] and not non_loopback
                       and not result["child_processes"] and not result["files_created_in_HOME"]
                       and not result["repository_status_changed"])
    Path(out_path).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: result[k] for k in ("clean", "outbound_attempts_via_proxy", "non_loopback_sockets",
                                             "child_processes", "files_created_in_HOME",
                                             "files_created_in_OPENJARVIS_HOME", "max_threads", "exercised")},
                     indent=1))
    shutil.rmtree(home, ignore_errors=True)
    shutil.rmtree(ojhome, ignore_errors=True)
    return 0 if result["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
