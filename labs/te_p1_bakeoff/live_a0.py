"""JRV-TE-P1 Agent Zero runner (T1 and T2) — same fixture, instruction, isolation and scorers.

Agent Zero is a server, not a CLI, so the ONE initial instruction is delivered through its official
non-interactive endpoint ``POST /api/api_message`` (API key read by the harness from the agent's own
settings with ``docker exec``; nothing else is changed inside the agent).

Setup applied to the verified image (``agent0ai/agent-zero@sha256:28a9a19e…``), all recorded:
* ``usr/plugins/_model_config/presets.yaml`` (DATA file) → the single local Ollama preset
  (qwen3.5:4b, 64K) instead of the shipped OpenRouter cloud default;
* ``TIKTOKEN_CACHE_DIR`` → the tiktoken cache bundled INSIDE the image (litellm, SHA-256 verified),
  because the network is closed.

T2: stop the agent container after the first HTTP 200, ``docker commit``, start a new container from
the committed state and send the neutral resume text to the SAME chat context id (found by the harness
in ``/a0/usr/chats``).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

from labs.te_p1_bakeoff import live_harness as H

IMAGE = "mirror.gcr.io/agent0ai/agent-zero@sha256:28a9a19e3168d44d53c78fb1a6c7cf086c9e7d6d621d906660d5ec1170d065c1"
TIKTOKEN = "/opt/venv-a0/lib/python3.12/site-packages/litellm/litellm_core_utils/tokenizers"
RESUME_TEXT = "Continua a tarefa anterior a partir do ponto onde ficou."
CLIENT = "mirror.gcr.io/library/python:3.12-slim"


def _start_agent(name, image, presets, out, from_commit=False):
    H.sh(["docker", "rm", "-f", name])
    H.sh(["docker", "create", "--name", name, "--network", H.NETWORK, "--network-alias", "agent0",
          "-e", f"TIKTOKEN_CACHE_DIR={TIKTOKEN}", image], check=True)
    H.sh(["docker", "start", name], check=True)
    t0 = time.monotonic()
    _wait_running(name, 0)
    if not from_commit:    # usr/plugins/_model_config exists only after the first start
        H.sh(["docker", "cp", str(presets), f"{name}:/a0/usr/plugins/_model_config/presets.yaml"], check=True)
        n = _running_count(name)
        H.sh(["docker", "restart", name], check=True)
        _wait_running(name, n)
    token = H.sh(["docker", "exec", name, "bash", "-c", "cd /a0 && /opt/venv-a0/bin/python -c \"from helpers.settings "
                  "import get_settings; print(get_settings()['mcp_server_token'])\" 2>/dev/null | tail -1"]).stdout.strip()
    return token, round(time.monotonic() - t0, 1)


def _running_count(name):
    r = H.sh(["docker", "logs", name])
    return (r.stdout + r.stderr).count("Agent Zero is running")


def _wait_running(name, previous, limit=600):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit and _running_count(name) <= previous:
        time.sleep(5)


def _send(token, message, timeout, context_id=None, label="send"):
    payload = {"message": message, **({"context_id": context_id} if context_id else {})}
    code = (f"import json,urllib.request,sys\n"
            f"req=urllib.request.Request('http://agent0:80/api/api_message',sys.stdin.read().encode(),"
            f"{{'Content-Type':'application/json','X-API-KEY':{token!r}}})\n"
            f"r=urllib.request.urlopen(req,timeout={timeout}); print(r.read().decode())")
    H.sh(["docker", "rm", "-f", f"client-{label}"])
    return ["docker", "run", "--rm", "-i", "--name", f"client-{label}", "--network", H.NETWORK, CLIENT,
            "python", "-c", code], json.dumps(payload)


def _fixture(out):
    H.sh(["docker", "rm", "-f", "fixture"])
    H.sh(["docker", "run", "-d", "--name", "fixture", "--network", H.NETWORK, "--network-alias", "fixture",
          "-v", f"{H.ROOT}/labs:/app/labs:ro", "-v", f"{out.resolve()}:/evidence", "-w", "/app", CLIENT,
          "python", "-m", "labs.te_p1_bakeoff.site", "--port", "8765", "--bind", "0.0.0.0",
          "--evidence", "/evidence/http.jsonl"], check=True)
    time.sleep(2)


def _collect(name, out, response_text):
    from labs.te_p1_bakeoff.score import score
    from labs.te_p1_bakeoff.score_semantic import check
    H.sh(["docker", "cp", f"{name}:/a0/usr/workdir/.", str(out / "agent_workdir")])
    logs = H.sh(["docker", "logs", name])
    (out / "agent_stdout.txt").write_text(logs.stdout, encoding="utf-8")
    (out / "agent_stderr.txt").write_text(logs.stderr, encoding="utf-8")
    (out / "api_response.txt").write_text(response_text or "", encoding="utf-8")
    report, source = None, "none"
    for f in sorted((out / "agent_workdir").glob("*.json"), key=lambda f: (f.name != "report.json", -f.stat().st_size)):
        try:
            report, source = json.loads(f.read_text(encoding="utf-8")), f"file:/a0/usr/workdir/{f.name}"
            break
        except ValueError:
            continue
    if report is None:
        try:
            msg = json.loads(response_text).get("response", "")
        except (ValueError, AttributeError, TypeError):
            msg = response_text or ""
        report, source = H.last_json_object(msg), "final_answer_last_json"
    events = [json.loads(s) for s in (out / "http.jsonl").read_text().splitlines() if s.strip()] \
        if (out / "http.jsonl").exists() else []
    return events, report, source, score(events, report if isinstance(report, dict) else {}), check(report)


def t1(a):
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    _fixture(out)
    token, boot = _start_agent("agent-a0", IMAGE, a.presets, out)
    sampler = H.Sampler(["agent-a0", "ollama"])
    sampler.start()
    cmd, payload = _send(token, H.INSTRUCTION.format(base=H.FIXTURE_BASE), a.timeout, label="t1")
    t0 = time.monotonic()
    try:
        r = H.subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=a.timeout + 60)
        response, rc = r.stdout, r.returncode
        (out / "client_stderr.txt").write_text(r.stderr[-4000:], encoding="utf-8")
    except H.subprocess.TimeoutExpired:
        response, rc = "", "TIMEOUT"
    wall = round(time.monotonic() - t0, 1)
    sampler.stop = True
    events, report, source, verdict, semantic = _collect("agent-a0", out, response)
    run = {"agent": "agent-zero", "image": IMAGE, "boot_seconds": boot, "wall_seconds": wall, "client_rc": rc,
           "peak_mem_mib": {k: round(v) for k, v in sampler.peak.items()},
           "isolation": {"network": H.NETWORK, "internal": json.loads(H.sh(["docker", "network", "inspect", H.NETWORK]).stdout)[0]["Internal"],
                         "agent_host_mounts": json.loads(H.sh(["docker", "inspect", "agent-a0"]).stdout)[0]["Mounts"]},
           "http_events": events, "report_source": source, "verdict": verdict, "semantic": semantic}
    (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: run[k] for k in ("wall_seconds", "client_rc", "peak_mem_mib", "report_source", "verdict",
                                          "semantic")}, ensure_ascii=False, indent=2))


def t2(a):
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    _fixture(out)
    token, _ = _start_agent("t2a-a0", IMAGE, a.presets, out)
    cmd, payload = _send(token, H.INSTRUCTION.format(base=H.FIXTURE_BASE), a.timeout, label="t2a")
    proc = H.subprocess.Popen(cmd, stdin=H.subprocess.PIPE, stdout=H.subprocess.PIPE, stderr=H.subprocess.PIPE, text=True)
    proc.stdin.write(payload)
    proc.stdin.close()
    log, t0, stopped_at, at_stop = out / "http.jsonl", time.monotonic(), None, []
    while time.monotonic() - t0 < a.timeout and proc.poll() is None:
        events = [json.loads(s) for s in log.read_text().splitlines() if s.strip()] if log.exists() else []
        if any(e["http_status"] == 200 for e in events):
            time.sleep(1)
            H.sh(["docker", "stop", "-t", "5", "t2a-a0"])
            stopped_at, at_stop = round(time.monotonic() - t0, 1), [json.loads(s) for s in log.read_text().splitlines() if s.strip()]
            break
        time.sleep(1)
    proc.kill()
    if stopped_at is None:
        (out / "t2.json").write_text(json.dumps({"agent": "agent-zero", "state": "INCOMPLETE",
                                                 "reason": "no completed tool operation before exit/timeout"}))
        print("INCOMPLETE")
        return
    H.sh(["docker", "commit", "t2a-a0", "jrv-t2-a0:state"], check=True)
    token2, _ = _start_agent("t2b-a0", "jrv-t2-a0:state", a.presets, out, from_commit=True)
    ctx = H.sh(["docker", "exec", "t2b-a0", "bash", "-c", "ls -1t /a0/usr/chats 2>/dev/null | head -1"]).stdout.strip()
    cmd, payload = _send(token2, RESUME_TEXT, a.timeout, context_id=ctx or None, label="t2b")
    t1_ = time.monotonic()
    try:
        r = H.subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=a.timeout + 60)
        response = r.stdout
        (out / "client_stderr.txt").write_text(r.stderr[-4000:], encoding="utf-8")
    except H.subprocess.TimeoutExpired:
        response = ""
    wall2 = round(time.monotonic() - t1_, 1)
    events, report, source, verdict, semantic = _collect("t2b-a0", out, response)
    done_before = {e["path"] for e in at_stop if e["http_status"] == 200}
    result = {"agent": "agent-zero", "interrupted_after_seconds": stopped_at, "events_at_stop": at_stop,
              "resume_context_id_found": bool(ctx),
              "interventions": ["docker stop -t 5 (agent only) after first HTTP 200", "docker commit (state preserved)",
                                f"api_message to the same context id with neutral text: {RESUME_TEXT!r}"],
              "phase2_wall_seconds": wall2,
              "refetched_after_resume": sorted(done_before & {e["path"] for e in events[len(at_stop):]}),
              "http_events": events, "report_source": source, "verdict": verdict, "semantic": semantic}
    (out / "t2.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("interrupted_after_seconds", "resume_context_id_found", "phase2_wall_seconds",
                                             "refetched_after_resume", "report_source", "semantic")}, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("t1", "t2", "smoke"))
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--presets", type=pathlib.Path, required=True)
    p.add_argument("--timeout", type=int, default=1800)
    a = p.parse_args(argv)
    if a.mode == "smoke":                     # infrastructure check only, trivial message, not the task
        a.out.mkdir(parents=True, exist_ok=True)
        token, boot = _start_agent("agent-a0", IMAGE, a.presets, a.out)
        cmd, payload = _send(token, "Responde apenas: ok", a.timeout, label="smoke")
        t0 = time.monotonic()
        r = H.subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=a.timeout + 60)
        print(json.dumps({"boot_seconds": boot, "wall": round(time.monotonic() - t0, 1), "rc": r.returncode,
                          "stdout": r.stdout[:400], "stderr": r.stderr[-400:]}, indent=2))
        H.sh(["docker", "rm", "-f", "agent-a0"])
        return
    (t1 if a.mode == "t1" else t2)(a)
    H.sh(["docker", "rm", "-f", "fixture"])


if __name__ == "__main__":
    main()
