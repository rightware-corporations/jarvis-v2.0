"""JRV-TE-P1 T2: interrupt after the first completed tool operation, then resume natively.

Phase 1: start the agent with the fixed T1 instruction in a fresh internal-only sandbox. As soon as the
independent fixture log shows the first HTTP 200, stop ONLY the agent container (SIGTERM, grace 5 s).
Its filesystem (session store) is preserved with ``docker commit``.
Phase 2: start a new container FROM that committed image with the agent's own resume command and
the neutral message RESUME_TEXT (no task content, no solution). Same fixture instance (its 503 state is
kept), same network, still no host mounts. Every intervention is recorded in t2.json.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

from labs.te_p1_bakeoff import live_harness as H

RESUME_TEXT = "Continua a tarefa anterior a partir do ponto onde ficou."


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--agent", required=True)
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--image", required=True)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--copy", action="append", default=[])
    p.add_argument("--env", action="append", default=[])
    p.add_argument("--start", required=True, help="phase-1 command (JSON list, {INSTRUCTION} substituted)")
    p.add_argument("--resume", required=True, help="phase-2 command (JSON list, {RESUME} substituted)")
    a = p.parse_args(argv)
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    instr = H.INSTRUCTION.format(base=H.FIXTURE_BASE)
    start = [c.replace("{INSTRUCTION}", instr) for c in json.loads(a.start)]
    resume = [c.replace("{RESUME}", RESUME_TEXT) for c in json.loads(a.resume)]
    ag1, ag2, img = f"t2a-{a.agent}", f"t2b-{a.agent}", f"jrv-t2-{a.agent}:state"
    for n in (ag1, ag2, "fixture"):
        H.sh(["docker", "rm", "-f", n])
    H.sh(["docker", "run", "-d", "--name", "fixture", "--network", H.NETWORK, "--network-alias", "fixture",
          "-v", f"{H.ROOT}/labs:/app/labs:ro", "-v", f"{out.resolve()}:/evidence", "-w", "/app",
          "mirror.gcr.io/library/python:3.12-slim", "python", "-m", "labs.te_p1_bakeoff.site", "--port", "8765",
          "--bind", "0.0.0.0", "--evidence", "/evidence/http.jsonl"], check=True)
    time.sleep(2)
    envs = sum((["-e", e] for e in a.env), [])
    H.sh(["docker", "create", "--name", ag1, "--network", H.NETWORK, "--workdir", "/work",
          "--security-opt", "no-new-privileges", *envs, a.image, *start], check=True)
    for spec in a.copy:
        src, dst = spec.split(":", 1)
        H.sh(["docker", "cp", src, f"{ag1}:{dst}"], check=True)
    log = out / "http.jsonl"
    t0 = time.monotonic()
    H.sh(["docker", "start", ag1])
    interrupted_at, events_at_stop = None, None
    while time.monotonic() - t0 < a.timeout:
        events = [json.loads(s) for s in log.read_text().splitlines() if s.strip()] if log.exists() else []
        if any(e["http_status"] == 200 for e in events):
            time.sleep(1)
            H.sh(["docker", "stop", "-t", "5", ag1])
            interrupted_at = round(time.monotonic() - t0, 1)
            events_at_stop = [json.loads(s) for s in log.read_text().splitlines() if s.strip()]
            break
        if H.sh(["docker", "inspect", "-f", "{{.State.Running}}", ag1]).stdout.strip() != "true":
            break
        time.sleep(1)
    l1 = H.sh(["docker", "logs", ag1])
    (out / "phase1_stdout.txt").write_text(l1.stdout, encoding="utf-8")
    (out / "phase1_stderr.txt").write_text(l1.stderr, encoding="utf-8")
    if interrupted_at is None:
        (out / "t2.json").write_text(json.dumps({"agent": a.agent, "state": "INCOMPLETE",
                                                 "reason": "no completed tool operation before exit/timeout"}))
        print("INCOMPLETE: no interruption point")
        return 1
    H.sh(["docker", "commit", ag1, img], check=True)
    H.sh(["docker", "create", "--name", ag2, "--network", H.NETWORK, "--workdir", "/work",
          "--security-opt", "no-new-privileges", *envs, img, *resume], check=True)
    t1 = time.monotonic()
    H.sh(["docker", "start", ag2])
    H.sh(["docker", "wait", ag2], timeout=a.timeout + 30)
    wall2 = round(time.monotonic() - t1, 1)
    if H.sh(["docker", "inspect", "-f", "{{.State.Running}}", ag2]).stdout.strip() == "true":
        H.sh(["docker", "kill", ag2])
    l2 = H.sh(["docker", "logs", ag2])
    (out / "phase2_stdout.txt").write_text(l2.stdout, encoding="utf-8")
    (out / "phase2_stderr.txt").write_text(l2.stderr, encoding="utf-8")
    H.sh(["docker", "cp", f"{ag2}:/work/.", str(out / "agent_workdir")])
    events = [json.loads(s) for s in log.read_text().splitlines() if s.strip()]
    report, source = None, "none"
    for f in sorted((out / "agent_workdir").glob("*.json"), key=lambda f: (f.name != "report.json", -f.stat().st_size)):
        try:
            report, source = json.loads(f.read_text(encoding="utf-8")), f"file:/work/{f.name}"
            break
        except ValueError:
            continue
    if report is None:
        report, source = H.last_json_object(l2.stdout), "final_answer_last_json"
    from labs.te_p1_bakeoff.score import score
    from labs.te_p1_bakeoff.score_semantic import check
    paths_after = [e["path"] for e in events[len(events_at_stop):]]
    done_before = {e["path"] for e in events_at_stop if e["http_status"] == 200}
    result = {
        "agent": a.agent, "interrupted_after_seconds": interrupted_at, "events_at_stop": events_at_stop,
        "interventions": ["docker stop -t 5 (agent only) after first HTTP 200", "docker commit (state preserved)",
                          f"resume command with neutral text: {RESUME_TEXT!r}"],
        "resume_command": [c if len(c) < 200 else c[:80] + "…" for c in resume], "phase2_wall_seconds": wall2,
        "refetched_after_resume": sorted(done_before & set(paths_after)),
        "resumed_context_evidence": "see phase2_stdout.txt (does the agent refer to work done before the stop?)",
        "http_events": events, "report_source": source,
        "verdict": score(events, report if isinstance(report, dict) else {}), "semantic": check(report),
    }
    (out / "t2.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("agent", "interrupted_after_seconds", "phase2_wall_seconds",
                                             "refetched_after_resume", "report_source", "semantic")},
                     ensure_ascii=False, indent=2))
    H.sh(["docker", "rm", "-f", "fixture"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
