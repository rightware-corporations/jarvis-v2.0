"""JRV-TE-P2A Phase B: goose v1.60.1 → RIGHTWARE Tool Gateway (MCP) → AgentPolicy → tools → receipts.

Topology (two Docker ``--internal`` networks, no route outside):
* ``jrv-agent``   : goose, model tap, Ollama, gateway
* ``jrv-fixture`` : gateway, fixture
goose has NO route to the fixture: the gateway is its only way to act. goose runs with ``--no-profile``
and ONLY ``--with-streamable-http-extension http://gateway:8790/mcp`` (no ``developer``, no shell). The
model tap records the tool names actually offered to the model in every request (inventory evidence).
The goose container has no host mounts (binary copied in). Completion is decided by ``verify.verify``
from the gateway's receipts — never from goose's answer.

Usage: python -m labs.te_p2a_gateway.live_goose {probe,smoke,t1} --out DIR --goose BIN --models DIR --ollama DIR
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

from labs.te_p1_bakeoff.live_harness import INSTRUCTION, ROOT, Sampler, last_json_object, sh

BASE = "https://catalog.fixture.example/"
PY = "mirror.gcr.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
GW_IMAGE = "jrv-gateway:te-p2a"
GATEWAY_TOOL_NAMES = ("web_open", "web_follow", "web_find", "submit_report")   # BP-043: + receipted report
AGENT_SUBNET, GOOSE_IP = "172.30.10.0/24", "172.30.10.10"   # BP-043: gateway accepts only this client
NETS = ("jrv-agent", "jrv-fixture")
GOOSE_ENV = {"HOME": "/root", "GOOSE_DISABLE_KEYRING": "1", "GOOSE_PROVIDER": "ollama", "GOOSE_MODEL": "qwen3.5:4b",
             "OLLAMA_HOST": "http://ollama-tap:11434", "GOOSE_INPUT_LIMIT": "65536", "GOOSE_MODE": "auto",
             "GOOSE_TEMPERATURE": "0.2", "GOOSE_TELEMETRY_ENABLED": "false"}


def infra(out: pathlib.Path, a, attempt: str):
    for n in ("ollama", "ollama-tap", "fixture", "gateway", "goose"):
        sh(["docker", "rm", "-f", n])
    for net in NETS:                      # recreated per run; jrv-agent with a fixed subnet for the client allowlist
        sh(["docker", "network", "rm", net])
        extra = ["--subnet", AGENT_SUBNET] if net == "jrv-agent" else []
        sh(["docker", "network", "create", "--internal", *extra, net], check=True)
    ev = str(out.resolve())
    sh(["docker", "run", "-d", "--name", "ollama", "--network", "jrv-agent", "-v", f"{a.ollama}:/opt/ollama:ro",
        "-v", f"{a.models}:/models", "-e", "OLLAMA_MODELS=/models", "-e", "OLLAMA_HOST=0.0.0.0:11434",
        "-e", "OLLAMA_NO_CLOUD=1", "-e", "OLLAMA_KEEP_ALIVE=30m", "-e", "OLLAMA_CONTEXT_LENGTH=65536",
        PY, "/opt/ollama/bin/ollama", "serve"], check=True)
    sh(["docker", "run", "-d", "--name", "ollama-tap", "--network", "jrv-agent", "-v", f"{ROOT}/labs:/app/labs:ro",
        "-v", f"{ev}:/evidence", "-w", "/app", PY, "python", "-m", "labs.te_p2a_gateway.model_tap",
        "--upstream", "http://ollama:11434", "--log", "/evidence/model_requests.jsonl",
        *sum((["--allow-suffix", "__" + t] for t in GATEWAY_TOOL_NAMES), [])], check=True)
    sh(["docker", "run", "-d", "--name", "fixture", "--network", "jrv-fixture", "-v", f"{ROOT}/labs:/app/labs:ro",
        "-v", f"{ev}:/evidence", "-w", "/app", PY, "python", "-m", "labs.te_p1_bakeoff.site", "--port", "8765",
        "--bind", "0.0.0.0", "--evidence", "/evidence/http.jsonl"], check=True)
    # TE-P2C: the supervisor control token is passed by NAME (value from the runner's environment, never argv)
    control = ["-e", "JRV_CONTROL_TOKEN"] if getattr(a, "control_token", False) else []
    sh(["docker", "run", "-d", "--name", "gateway", "--network", "jrv-fixture", "-v", f"{ROOT}:/app:ro",
        "-v", f"{ev}:/evidence", "-w", "/app", "-e", "PYTHONPATH=/app", *control, GW_IMAGE, "/opt/ojvenv/bin/python", "-m",
        "labs.te_p2a_gateway.mcp_http", "--task", getattr(a, "task", "TE-P2A-T1"), "--attempt", attempt,
        "--evidence", "/evidence", "--allow-client", GOOSE_IP,
        *(["--report-contract", a.report_contract] if getattr(a, "report_contract", None) else ["--submit-report"])],
       check=True)
    sh(["docker", "network", "connect", "--alias", "gateway", "jrv-agent", "gateway"], check=True)
    time.sleep(6)


def probe(out: pathlib.Path) -> dict:
    """Topology evidence from a container placed exactly like goose (jrv-agent only)."""
    code = ("import urllib.request,json,socket\nres={}\n"
            "for name,u in [('fixture','http://fixture:8765/'),('internet','https://pypi.org/'),"
            "('gateway','http://gateway:8790/mcp'),('ollama-tap','http://ollama-tap:11434/api/version')]:\n"
            "  try:\n    r=urllib.request.urlopen(u,timeout=5); res[name]='REACHED %s'%r.status\n"
            "  except urllib.error.HTTPError as e: res[name]='REACHED %s'%e.code\n"
            "  except Exception as e: res[name]='BLOCKED '+type(e).__name__\nprint(json.dumps(res))")
    r = sh(["docker", "run", "--rm", "--network", "jrv-agent", PY, "python", "-c", code])
    result = json.loads(r.stdout.strip().splitlines()[-1])
    post = ("import urllib.request,json\nreq=urllib.request.Request('http://gateway:8790/mcp',json.dumps({'jsonrpc':'2.0',"
            "'id':1,'method':'initialize','params':{}}).encode(),{'Content-Type':'application/json'})\n"
            "try:\n  print(urllib.request.urlopen(req,timeout=5).status)\nexcept urllib.error.HTTPError as e: print(e.code)")
    result["gateway_initialize_from_non_goose_ip"] = sh(["docker", "run", "--rm", "--network", "jrv-agent", PY, "python",
                                                         "-c", post]).stdout.strip()
    (out / "topology_probe.json").write_text(json.dumps(result, indent=2))
    return result


def run_goose(out, a, text, max_turns=40, timeout=1800):
    sh(["docker", "create", "--name", "goose", "--network", "jrv-agent", "--ip", GOOSE_IP, "--workdir", "/work",
        "--security-opt", "no-new-privileges", *sum((["-e", f"{k}={v}"] for k, v in GOOSE_ENV.items()), []),
        PY, "goose", "run", "--no-profile", "--with-streamable-http-extension", "http://gateway:8790/mcp",
        "--max-turns", str(max_turns), "--name", "te-p2a", "--text", text], check=True)
    sh(["docker", "cp", str(a.goose), "goose:/usr/local/bin/goose"], check=True)
    sampler = Sampler(["goose", "ollama", "gateway"])
    sampler.start()
    t0 = time.monotonic()
    sh(["docker", "start", "goose"])
    try:
        sh(["docker", "wait", "goose"], timeout=timeout)
        timed_out = False
    except Exception:
        sh(["docker", "kill", "goose"])
        timed_out = True
    wall = round(time.monotonic() - t0, 1)
    sampler.stop = True
    logs = sh(["docker", "logs", "goose"])
    (out / "goose_stdout.txt").write_text(logs.stdout, encoding="utf-8")
    (out / "goose_stderr.txt").write_text(logs.stderr, encoding="utf-8")
    sh(["docker", "cp", "goose:/work/.", str(out / "agent_workdir")])
    sh(["docker", "cp", "goose:/root/.local/share/goose", str(out / "goose_state")])
    mounts = json.loads(sh(["docker", "inspect", "goose"]).stdout)[0]["Mounts"]
    return {"wall_seconds": wall, "timed_out": timed_out, "peak_mem_mib": {k: round(v) for k, v in sampler.peak.items()},
            "goose_host_mounts": mounts, "goose_networks": sorted(json.loads(sh(["docker", "inspect", "goose"]).stdout)[0]
                                                                  ["NetworkSettings"]["Networks"])}


def inventory(out: pathlib.Path) -> dict:
    rows = [json.loads(s) for s in (out / "model_requests.jsonl").read_text().splitlines() if s.strip()] \
        if (out / "model_requests.jsonl").exists() else []
    offered = sorted({n for r in rows for n in (r.get("tool_names") or []) if n})
    forwarded = sorted({n for r in rows for n in (r.get("forwarded_tool_names") or []) if n})
    gw = lambda n: n.startswith("gateway_8790_mcp__") and n.split("__")[-1] in GATEWAY_TOOL_NAMES
    return {"model_requests": len(rows), "tool_names_offered_by_goose": offered,
            "tool_names_forwarded_to_model": forwarded,
            "only_gateway_tools_reach_model": bool(forwarded) and all(gw(n) for n in forwarded),
            "non_gateway_tools_in_goose": [n for n in offered if not gw(n)],
            "num_ctx": sorted({(r.get("options") or {}).get("num_ctx") for r in rows if r.get("options")}),
            "endpoints": sorted({r.get("path") for r in rows})}


def goose_final_answer(out: pathlib.Path) -> str:
    """Text of the LAST assistant message in goose's session store (complete, untruncated)."""
    import glob
    import sqlite3
    text = ""
    for db in glob.glob(str(out / "goose_state" / "**" / "sessions.db"), recursive=True):
        con = sqlite3.connect(db)
        rows = con.execute("select content_json from messages where role='assistant' order by id").fetchall()
        con.close()
        for (content,) in rows:
            parts = [p.get("text", "") for p in json.loads(content or "[]") if p.get("type") == "text"]
            if parts:
                text = "\n".join(parts)
    return text


def goose_tool_calls(out: pathlib.Path) -> dict:
    """Tool calls goose actually executed, from its own session store (names only)."""
    import glob
    import sqlite3
    dbs = glob.glob(str(out / "goose_state" / "**" / "sessions.db"), recursive=True)
    names = []
    for db in dbs:
        con = sqlite3.connect(db)
        rows = con.execute("select content_json from messages where role='assistant' order by id").fetchall()
        con.close()
        for (content,) in rows:
            for part in json.loads(content or "[]"):
                if part.get("type") == "toolRequest":
                    call = (part.get("toolCall") or {}).get("value") or {}
                    names.append(call.get("name"))
    gw = lambda n: isinstance(n, str) and n.startswith("gateway_8790_mcp__") and n.split("__")[-1] in GATEWAY_TOOL_NAMES
    return {"executed_tool_calls": len(names), "names": names, "non_gateway_calls": [n for n in names if not gw(n)]}


def receipts_from(out: pathlib.Path):
    from rightware.agent.receipts import ExecutionReceipt
    path = out / "receipts.jsonl"
    rows = [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []
    return [ExecutionReceipt(**{**r, "file_evidence": tuple(map(tuple, r["file_evidence"])) if r.get("file_evidence")
                                else None}) for r in rows]


def finish(out, extra) -> dict:
    from labs.te_p2a_gateway.verify import verify
    receipts = receipts_from(out)
    events = [json.loads(s) for s in (out / "http.jsonl").read_text().splitlines() if s.strip()] \
        if (out / "http.jsonl").exists() else []
    report, source = None, "none"
    for f in sorted((out / "agent_workdir").glob("*.json"), key=lambda f: (f.name != "report.json", -f.stat().st_size)):
        try:
            report, source = json.loads(f.read_text(encoding="utf-8")), f"file:/work/{f.name}"
            break
        except ValueError:
            continue
    if report is None:                         # goose's own session store: the full final answer
        final = goose_final_answer(out)            # (the CLI truncates long output on the terminal)
        report, source = last_json_object(final), "goose_session_final_answer_last_json"
    if report is None:
        report, source = last_json_object((out / "goose_stdout.txt").read_text(errors="replace")), "final_answer_last_json"
    calls = goose_tool_calls(out)
    subs_path = out / "submissions.jsonl"
    submissions = [json.loads(x) for x in subs_path.read_text().splitlines() if x.strip()] if subs_path.exists() else []
    rows = [json.loads(x) for x in (out / "model_requests.jsonl").read_text().splitlines() if x.strip()] \
        if (out / "model_requests.jsonl").exists() else []
    blocked = [n for r in rows for n in r.get("blocked_tool_calls_in_model_output", [])]
    rejections = [json.loads(x) for x in (out / "transport_rejections.jsonl").read_text().splitlines() if x.strip()] \
        if (out / "transport_rejections.jsonl").exists() else []
    result = {**extra, "inventory": inventory(out), "goose_tool_calls": calls, "receipts": len(receipts),
              "blocked_tool_calls_in_model_output": blocked, "transport_rejections": rejections,
              "submissions": [{"sequence": x["sequence"], "sha256": x["sha256"], "chars": len(x["report"])}
                              for x in submissions],
              "gateway_exclusive": not calls["non_gateway_calls"] and len(receipts) == calls["executed_tool_calls"],
              "receipt_rows": [(r.sequence, r.tool, r.status, r.reason_code, r.http_status, r.final_url) for r in receipts],
              "fixture_events": [(e["path"], e["http_status"]) for e in events], "report_source": source,
              "verification": verify(receipts, events, None, submissions=submissions, report_channel="submit_report"),
              "comparison_final_answer_channel": verify(receipts, events, report, report_channel="final_answer")}
    chain_path = out / "submission_chain.jsonl"
    if chain_path.exists():                    # TE-P2B: contract mode — chain ↔ receipts ↔ audit, then verdict record
        from labs.te_p2a_gateway import frozen
        from labs.te_p2a_gateway import report_contract as RC
        chain = [json.loads(x) for x in chain_path.read_text().splitlines() if x.strip()]
        audit = [json.loads(x) for x in (out / "audit.jsonl").read_text().splitlines() if x.strip()] \
            if (out / "audit.jsonl").exists() else []
        before = RC.check_chain(chain, receipts, submissions, audit)
        final = list(chain)
        RC.chain_record(final, kind="verdict", run_id=chain[0]["run_id"] if chain else f"TE-P2B-T1:{extra.get('attempt')}",
                        verdict=result["verification"]["verdict"],
                        verifier_group_sha256=frozen.current()["groups"]["verifier"],
                        accepted_receipt_sequence=result["verification"]["report_delivery_receipt"])
        (out / "submission_chain_final.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in final))
        after = RC.check_chain(final, receipts, submissions, audit) if chain else {"valid": True, "problems": []}
        result["contract"] = {"contract_id": RC.CONTRACT_ID, "schema_sha256": RC.SCHEMA_SHA256,
                              "chain_check_gateway": before, "chain_check_with_verdict": after,
                              "submissions": [{k: r[k] for k in ("receipt_sequence", "report_sha256", "report_bytes",
                                                                 "decision", "schema_valid", "errors")}
                                              for r in chain]}
    (out / "run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return result


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("probe", "smoke", "t1"))
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--goose", type=pathlib.Path, required=True)
    p.add_argument("--models", type=pathlib.Path, required=True)
    p.add_argument("--ollama", type=pathlib.Path, required=True)
    p.add_argument("--attempt", default="A1")
    p.add_argument("--task", default="TE-P2A-T1")
    p.add_argument("--report-contract", default=None, help="TE-P2B contract id (default: legacy submit_report)")
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    infra(a.out, a, a.attempt)
    topo = probe(a.out)
    if a.mode == "probe":
        print(json.dumps(topo, indent=2))
        return
    text = "Responde apenas: ok" if a.mode == "smoke" else INSTRUCTION.format(base=BASE)
    extra = run_goose(a.out, a, text, max_turns=3 if a.mode == "smoke" else 40, timeout=900 if a.mode == "smoke" else 1800)
    extra["topology_probe"] = topo
    extra["mode"] = a.mode
    sh(["docker", "logs", "ollama"], )
    (a.out / "ollama_server.log").write_text(sh(["docker", "logs", "ollama"]).stderr, encoding="utf-8")
    result = finish(a.out, extra)
    print(json.dumps({k: result[k] for k in ("mode", "wall_seconds", "timed_out", "inventory", "goose_tool_calls",
                                             "gateway_exclusive", "receipts",
                                             "receipt_rows", "fixture_events", "verification")}, ensure_ascii=False,
                     indent=1, default=str))


if __name__ == "__main__":
    main()
