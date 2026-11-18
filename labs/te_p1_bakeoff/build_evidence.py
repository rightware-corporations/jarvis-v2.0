"""Rebuild the compact, transcript-free JRV-TE-P1 evidence JSON from the ORIGINAL run directories.

* Both stdout AND stderr are read (JRV-BP-039: Hermes writes its pause notice to stderr; the first
  builder looked only at stdout and wrote ``paused_requiring_operator: false``). The SHA-256 and size of
  every log consulted are recorded, so each flag can be traced to its source.
* The strict ``score.py`` verdict is the one stored by the run (never recomputed or edited).
* The semantic verdict is recomputed with the audited ``score_semantic.check`` for EVERY candidate.

Usage: python -m labs.te_p1_bakeoff.build_evidence RUNS_DIR OUT_JSON
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
import sys

from labs.te_p1_bakeoff.score_semantic import check


def _log(path: pathlib.Path) -> tuple[str, dict]:
    if not path.exists():
        return "", {"file": path.name, "present": False}
    data = path.read_bytes()
    return data.decode("utf-8", "replace"), {"file": path.name, "bytes": len(data),
                                             "sha256": hashlib.sha256(data).hexdigest()}


def _events(d):
    return [(e["path"], e["http_status"]) for e in d or []]


def _workdir_report(run: pathlib.Path):
    files = sorted((run / "agent_workdir").glob("*.json"), key=lambda f: (f.name != "report.json", -f.stat().st_size))
    for f in files:
        try:
            return json.loads(f.read_text(encoding="utf-8")), f"file:/work/{f.name}"
        except ValueError:
            continue
    return None, None


def _plain(text: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _a0_counts(text: str) -> dict:
    t = _plain(text)
    return {"tool_uses": t.count("A0: Using tool"), "browser_tool_uses": t.count("A0: Using tool 'browser'"),
            "browser_click_reference_errors": t.count("could not find reference"),
            "thoughts_claiming_success": t.count("successfully completed"),
            "huggingface_egress_attempts_blocked": t.count("huggingface.co")}


def _ollama_summary(path: pathlib.Path, since: str | None = None) -> dict:
    """Numbers from the Ollama server access log (status, endpoint, duration); no prompts."""
    import re
    rows = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            m = re.search(r"\[GIN\] \S+ - (\d\d:\d\d:\d\d) \| (\d{3}) \|\s+([\dhmsµ.]+) \|.*\"(/api/[a-z]+)\"", line)
            if m and (since is None or m.group(1) >= since):
                rows.append(m.groups())
    gen = [r for r in rows if r[3] in ("/api/generate", "/api/chat")]
    return {"requests": len(rows), "generate_or_chat": len(gen),
            "generate_status_counts": {c: sum(1 for r in gen if r[1] == c) for c in sorted({r[1] for r in gen})},
            "generate_durations": [r[2] for r in gen][-12:]}


def _agent_zero(runs: pathlib.Path) -> dict:
    """Agent Zero runs (live_a0.py): same fields where they exist; counts instead of transcripts."""
    out = {}
    run = runs / "a0-t1"
    if (run / "run.json").exists():
        r = json.loads((run / "run.json").read_text())
        so, so_meta = _log(run / "agent_stdout.txt")
        se, se_meta = _log(run / "agent_stderr.txt")
        api, api_meta = _log(run / "api_response.txt")
        report, source = _workdir_report(run)
        if report is None:
            source = r.get("report_source")
        out["agent-zero-t1"] = {
            "wall_seconds": r["wall_seconds"], "timed_out": r["client_rc"] != 0 and r["wall_seconds"] >= 1800,
            "client_rc": r["client_rc"], "boot_seconds": r["boot_seconds"], "peak_mem_mib": r["peak_mem_mib"],
            "isolation": r["isolation"], "http_events": _events(r["http_events"]), "report_source": source,
            "score_py_as_recorded": r["verdict"], "semantic": check(report), "agent_report": report,
            "counts": _a0_counts(so + se), "logs": [so_meta, se_meta, api_meta],
            "ollama": _ollama_summary(run / "ollama_server.log", since="16:35:40")}
    run = runs / "a0-t2"
    if (run / "t2.json").exists():
        d = json.loads((run / "t2.json").read_text())
        so, so_meta = _log(run / "agent_stdout.txt")
        se, se_meta = _log(run / "agent_stderr.txt")
        api, api_meta = _log(run / "api_response.txt")
        report, source = _workdir_report(run)
        if report is None:
            source = d.get("report_source")
        out["agent-zero-t2"] = {k: d.get(k) for k in ("interrupted_after_seconds", "phase2_wall_seconds",
                                                      "interventions", "refetched_after_resume",
                                                      "resume_context_id_found", "state", "reason")}
        out["agent-zero-t2"].update({
            "events_at_stop": _events(d.get("events_at_stop")), "http_events": _events(d.get("http_events")),
            "report_source": source, "score_py_as_recorded": d.get("verdict"), "semantic": check(report),
            "agent_report": report, "api_response_bytes": len(api), "counts_phase2": _a0_counts(so + se),
            "logs": [so_meta, se_meta, api_meta],
            "ollama_after_t2_start": _ollama_summary(run / "ollama_server.log", since="17:05:47"),
            "phase1_outcome": ("every model generation hit Agent Zero's 600 s litellm timeout (HTTP 500 at 10m0s); "
                               "no fixture request; resume path not exercised")})
    return out


def build(runs: pathlib.Path) -> dict:
    out = {}
    for name in ("goose-t1", "goose-t1-run2", "hermes-t1"):
        run = runs / name
        r = json.loads((run / "run.json").read_text())
        so, so_meta = _log(run / "agent_stdout.txt")
        se, se_meta = _log(run / "agent_stderr.txt")
        report, source = _workdir_report(run)
        if report is None:
            report = json.loads((run / "report.json").read_text()) if (run / "report.json").exists() else None
            source = r.get("report_source")
        out[name] = {
            "wall_seconds": r["wall_seconds"], "timed_out": r["timed_out"], "exit_code": r["exit_code"],
            "peak_mem_mib": r["peak_mem_mib"],
            "isolation": {k: r["isolation"][k] for k in ("network", "internal", "agent_host_mounts")},
            "http_events": _events(r["http_events"]), "report_source": source,
            "score_py_as_recorded": r["verdict"], "semantic": check(report), "agent_report": report,
            "output_token_limit_hit": "output-token limit" in so + se,
            "logs": [so_meta, se_meta],
        }
        if name.startswith("goose"):
            out[name]["goose_shell_tool_calls"] = (so + se).count("▸ shell")
    for name in ("goose-t2", "hermes-t2"):
        run = runs / name
        d = json.loads((run / "t2.json").read_text())
        texts, metas = [], []
        for f in ("phase1_stdout.txt", "phase1_stderr.txt", "phase2_stdout.txt", "phase2_stderr.txt"):
            t, m = _log(run / f)
            texts.append(t)
            metas.append(m)
        p2 = texts[2] + texts[3]
        report, source = _workdir_report(run)
        if report is None:
            source = d.get("report_source")
        out[name] = {
            "interrupted_after_seconds": d.get("interrupted_after_seconds"),
            "phase2_wall_seconds": d.get("phase2_wall_seconds"),
            "interventions": d.get("interventions"), "events_at_stop": _events(d.get("events_at_stop")),
            "http_events": _events(d.get("http_events")), "refetched_after_resume": d.get("refetched_after_resume"),
            "report_source": source, "score_py_as_recorded": d.get("verdict"), "semantic": check(report),
            "agent_report": report,
            "resumed_same_session": "resuming" in p2,
            "paused_requiring_operator": "This chat is paused" in p2,
            "pause_notice_stream": ("stderr" if "This chat is paused" in texts[3] else
                                    "stdout" if "This chat is paused" in texts[2] else None),
            "logs": metas,
        }
    out.update(_agent_zero(runs))
    c = sqlite3.connect(runs / "goose-t1-run2/collect_root_.local_share_goose/sessions/sessions.db")
    out["goose-t1-run2"]["tokens"] = dict(zip(("input", "output", "total"), c.execute(
        "select accumulated_input_tokens,accumulated_output_tokens,accumulated_total_tokens from sessions").fetchone()))
    c = sqlite3.connect(runs / "hermes-t1/collect_root_.hermes_state.db")
    out["hermes-t1"]["tokens"] = dict(zip(("messages", "tool_calls", "input", "output", "cache_read"), c.execute(
        "select message_count,tool_call_count,input_tokens,output_tokens,cache_read_tokens from sessions").fetchone()))
    c = sqlite3.connect(runs / "goose-t1/collect_root_.local_share_goose/sessions/sessions.db")
    out["goose-t1"]["tokens"] = dict(zip(("session_total_last", "input", "output"), c.execute(
        "select total_tokens,accumulated_input_tokens,accumulated_output_tokens from sessions").fetchone()))
    out["goose-t1"]["invalid_for_comparison"] = ("Ollama effective context was 4096 tokens (harness misconfiguration, "
                                                 "GOOSE_INPUT_LIMIT not applied); last request truncated")
    return out


if __name__ == "__main__":
    runs, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    target.write_text(json.dumps(build(runs), ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: {"semantic": v["semantic"]["semantic_gate"],
                          "strict": (v.get("score_py_as_recorded") or {}).get("http_level_gate"),
                          **({"paused": v.get("paused_requiring_operator"), "stream": v.get("pause_notice_stream"),
                              "resumed": v.get("resumed_same_session")} if k.endswith("t2") else {})}
                      for k, v in json.loads(target.read_text()).items()}, indent=1))
