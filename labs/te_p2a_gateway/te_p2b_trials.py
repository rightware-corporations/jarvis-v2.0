"""JRV-TE-P2B real T1 trials under the FROZEN pre-registration (single versioned entry point).

Fail-early preconditions (any failure → exit before the first trial, nothing is run):
* git: tracked tree clean, HEAD == remote branch head, the pre-registration file unchanged since its
  publishing commit (which must be an ancestor of HEAD);
* frozen set (verifier, policy, scenario, historical A1–A4, permissions) identical to the G0 manifest,
  OpenJarvis gitlink == pin;
* goose binary SHA-256 + ``--version`` == 1.60.1; Ollama binary SHA-256; model digest via ``/api/tags``;
* every pre-registered value in ``PROTOCOL`` equals the value written in the pre-registration document.

Per trial (attempt ids B1..Bn, never A*): fresh networks/containers (live_goose.infra), topology probe
(isolation), goose run, receipts + chain + verdict (live_goose.finish), num_ctx observed, classification,
cleanup. A critical isolation violation stops the series immediately (NO-GO). Invalidation only by the
pre-registered rules; at most 2 replacements; every attempt (valid or not) is kept.

No transcripts are copied into the repository: the summary keeps names, counts, hashes, codes and the
submitted report texts (synthetic model output), never goose's conversation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import subprocess
import sys
import time

from labs.te_p1_bakeoff.live_harness import INSTRUCTION, ROOT, sh
from labs.te_p2a_gateway import frozen, live_goose as LG
from labs.te_p2a_gateway import report_contract as RC

PREREG = ROOT / "docs/research/TE_P2B_PREREGISTRATION.md"
BRANCH = "exp/te-p1-kaggle-goose"
PROTOCOL = {
    "n_trials": 5,
    "max_replacements": 2,
    "attempt_prefix": "B",
    "task_id": "TE-P2B-T1",
    "goose_version": "1.60.1",
    "goose_sha256": "4db5cf70f20d200ab6971725b2f93808a9245606c8c126d926a89c70271361b8",
    "ollama_version": "0.40.15",
    "ollama_sha256": "5b8be7213d4ba3ba587bceaeed897ef39a09fc44c51e490c098aa31ba7b9d3cf",
    "model": "qwen3.5:4b",
    "model_digest": "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04",
    "num_ctx": 65536,
    "temperature": "0.2",
    "max_turns": 40,
    "trial_timeout_seconds": 1800,
    "contract_id": RC.CONTRACT_ID,
    "schema_sha256": RC.SCHEMA_SHA256,
    "max_submissions": RC.MAX_SUBMISSIONS,
    "max_report_bytes": RC.MAX_REPORT_BYTES,
    "global_step_budget": 15,
    "deadline_seconds": 1700,
    "instruction_sha256": hashlib.sha256(INSTRUCTION.format(base=LG.BASE).encode("utf-8")).hexdigest(),
}
HARNESS_FILES = ("labs/te_p2a_gateway/te_p2b_trials.py", "labs/te_p2a_gateway/live_goose.py",
                 "labs/te_p2a_gateway/gateway.py", "labs/te_p2a_gateway/mcp_http.py",
                 "labs/te_p2a_gateway/report_contract.py", "labs/te_p2a_gateway/frozen.py",
                 "labs/te_p2a_gateway/fake_model.py")


def file_sha(rel: str) -> str:
    return frozen.sha256_file(rel)


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """95% Wilson score interval — DESCRIPTIVE only (no inference is drawn from N=5)."""
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(max(0.0, mid - half), 4), round(min(1.0, mid + half), 4)


def preconditions(a) -> dict:
    problems, facts = [], {}
    if git("status", "--porcelain", "--untracked-files=no"):
        problems.append("tracked working tree not clean")
    head = git("rev-parse", "HEAD")
    remote = git("ls-remote", "origin", f"refs/heads/{BRANCH}").split()[0:1]
    facts.update(head=head, remote_head=remote[0] if remote else None)
    if not remote or remote[0] != head:
        problems.append("HEAD is not the published remote head")
    try:
        git("merge-base", "--is-ancestor", a.prereg_commit, head)
    except subprocess.CalledProcessError:
        problems.append("pre-registration commit is not an ancestor of HEAD")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", a.prereg_commit, "HEAD", "--",
                       str(PREREG.relative_to(ROOT))]).returncode != 0:
        problems.append("pre-registration changed after its publishing commit (frozen)")
    facts["prereg_sha256"] = file_sha(str(PREREG.relative_to(ROOT)))
    facts["prereg_commit"] = a.prereg_commit
    prereg_text = PREREG.read_text(encoding="utf-8")
    for key, value in PROTOCOL.items():               # the document and the code must state the same protocol
        if f"`{key}` = `{value}`" not in prereg_text:
            problems.append(f"protocol value not in pre-registration: {key}")
    for rel in HARNESS_FILES:
        if f"`{rel}` `{file_sha(rel)}`" not in prereg_text:
            problems.append(f"harness file hash not in pre-registration: {rel}")
    diffs = frozen.differences()
    if diffs:
        problems.append(f"frozen files changed: {diffs}")
    if frozen.openjarvis_gitlink() != frozen.OPENJARVIS_PIN:
        problems.append("OpenJarvis gitlink differs from pin")
    goose_sha = hashlib.sha256(a.goose.read_bytes()).hexdigest()
    version = sh([str(a.goose), "--version"]).stdout.strip()
    ollama_sha = hashlib.sha256((a.ollama / "bin" / "ollama").read_bytes()).hexdigest()
    facts.update(goose_sha256=goose_sha, goose_version=version, ollama_sha256=ollama_sha,
                 frozen_groups=frozen.current()["groups"])
    if goose_sha != PROTOCOL["goose_sha256"] or version != PROTOCOL["goose_version"]:
        problems.append("goose binary/version mismatch")
    if ollama_sha != PROTOCOL["ollama_sha256"]:
        problems.append("ollama binary mismatch")
    return {"ok": not problems, "problems": problems, "facts": facts}


def model_digest() -> str | None:
    code = ("import urllib.request,json;d=json.load(urllib.request.urlopen('http://ollama:11434/api/tags',timeout=20));"
            "print(json.dumps({m['name']:m['digest'] for m in d['models']}))")
    for _ in range(10):
        r = sh(["docker", "run", "--rm", "--network", "jrv-agent", LG.PY, "python", "-c", code])
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip().splitlines()[-1]).get(PROTOCOL["model"])
        time.sleep(3)
    return None


def isolation_ok(probe: dict) -> bool:
    return (probe.get("fixture", "").startswith("BLOCKED") and probe.get("internet", "").startswith("BLOCKED")
            and probe.get("gateway", "").startswith("REACHED") and probe.get("gateway_initialize_from_non_goose_ip") == "403")


def running(name: str) -> bool:
    r = sh(["docker", "inspect", "-f", "{{.State.Running}}", name])
    return r.returncode == 0 and r.stdout.strip() == "true"


def classify(run: dict, infra_alive: dict) -> dict:
    """Pre-registered rules (section 5.3 of the pre-registration). Model failure NEVER invalidates."""
    v = run["verification"]
    contract = run.get("contract") or {}
    chain_ok = (contract.get("chain_check_with_verdict") or {}).get("valid", False)
    violation = bool(run["goose_tool_calls"]["non_gateway_calls"]) or not run["gateway_exclusive"] \
        or not run["inventory"]["only_gateway_tools_reach_model"]
    receipts_inconsistent = not chain_ok or not v["http_receipt_correspondence"]["match"] or bool(v["receipt_defects"])
    infra_failed = not all(infra_alive.values()) or run["inventory"]["model_requests"] == 0
    subs = contract.get("submissions") or []
    accepted = [s for s in subs if s["decision"] == "ACCEPTED_FOR_VERIFICATION"]
    tool_fail = [r for r in run["receipt_rows"] if r[2] in ("TIMED_OUT", "FAILED")]
    if violation:
        category, sub = "POLÍTICA", "non-gateway execution or tool outside allowlist reached the model"
    elif infra_failed:
        category, sub = "AMBIENTE", f"infrastructure not alive at end: {infra_alive}"
    elif receipts_inconsistent:
        category, sub = "HARNESS", "receipts/chain/HTTP correspondence inconsistent"
    elif v["verdict"] == "TASK_VERIFIED_LIMITED":
        category, sub = None, None
    elif tool_fail:
        category, sub = "FERRAMENTA", "gateway tool failed or timed out"
    elif not subs:
        category, sub = "MODELO_FORMATO", "NO_SUBMISSION: no submit_report call"
    elif not accepted:
        category, sub = "MODELO_FORMATO", "NO_CONFORMANT_SUBMISSION"
    else:
        category, sub = "MODELO_CONTEÚDO", "conformant report not verified (values/recommendation/trajectory)"
    invalid = infra_failed or receipts_inconsistent      # S3 or proven infrastructure failure only
    return {"category": category, "detail": sub, "invalid": invalid and not violation,
            "isolation_violation": violation, "receipts_inconsistent": receipts_inconsistent}


def trial(a, attempt: str, root: pathlib.Path) -> dict:
    out = root / f"t1-{attempt.lower()}"
    out.mkdir(parents=True, exist_ok=False)
    ns = argparse.Namespace(goose=a.goose, models=a.models, ollama=a.ollama, task=PROTOCOL["task_id"],
                            report_contract=RC.CONTRACT_ID)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    LG.infra(out, ns, attempt)
    digest = model_digest()
    probe = LG.probe(out)
    if digest != PROTOCOL["model_digest"] or not isolation_ok(probe):
        return {"attempt": attempt, "started": started, "aborted_before_goose": True, "model_digest": digest,
                "topology_probe": probe, "isolation_ok": isolation_ok(probe)}
    extra = LG.run_goose(out, ns, INSTRUCTION.format(base=LG.BASE), max_turns=PROTOCOL["max_turns"],
                         timeout=PROTOCOL["trial_timeout_seconds"])
    alive = {n: running(n) for n in ("ollama", "ollama-tap", "gateway", "fixture")}
    (out / "ollama_server.log").write_text(sh(["docker", "logs", "ollama"]).stderr, encoding="utf-8")
    extra.update(topology_probe=probe, mode="t1", attempt=attempt, model_digest=digest)
    run = LG.finish(out, extra)
    ended = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cls = classify(run, alive)
    texts = [json.loads(x) for x in (out / "submitted_texts.jsonl").read_text().splitlines() if x.strip()] \
        if (out / "submitted_texts.jsonl").exists() else []
    v = run["verification"]
    subs = (run.get("contract") or {}).get("submissions") or []
    row = {
        "attempt": attempt, "started": started, "ended": ended, "wall_seconds": run["wall_seconds"],
        "timed_out": run["timed_out"], "infra_alive_at_end": alive, "model_digest": digest,
        "num_ctx_observed": run["inventory"]["num_ctx"], "isolation_ok": isolation_ok(probe),
        "paths": [p for p, _ in run["fixture_events"]], "fixture_events": run["fixture_events"],
        "recovery_503": {"outage_receipts": sum(1 for r in run["receipt_rows"] if r[4] == 503),
                         "recovered": v["recovered_from_503_by_receipts"]},
        "blocked_tool_calls_in_model_output": run["blocked_tool_calls_in_model_output"],
        "denied_or_refused": [(r[0], r[1], r[2], r[3]) for r in run["receipt_rows"] if r[2] not in ("OK",)],
        "receipts": run["receipts"], "chain_valid": (run.get("contract") or {}).get("chain_check_with_verdict", {}).get("valid"),
        "chain_problems": (run.get("contract") or {}).get("chain_check_with_verdict", {}).get("problems"),
        "submissions": subs, "submission_count": len(subs),
        "first_submission_schema_valid": subs[0]["schema_valid"] if subs else None,
        "http_receipt_correspondence": v["http_receipt_correspondence"]["match"],
        "verdict": v["verdict"], "report_semantic": v["report_semantic"],
        "objectives": v["objectives"], "decoy_requested": v["decoy_requested"],
        "gateway_exclusive": run["gateway_exclusive"], "non_gateway_calls": run["goose_tool_calls"]["non_gateway_calls"],
        "transport_rejections": run["transport_rejections"], **cls,
        "submitted_texts": [{"sequence": t["sequence"], "sha256": t["sha256"], "report": t["report"]} for t in texts],
    }
    (out / "trial.json").write_text(json.dumps(row, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return row


def cleanup():
    for n in ("ollama", "ollama-tap", "fixture", "gateway", "goose"):
        sh(["docker", "rm", "-f", n])
    for net in LG.NETS:
        sh(["docker", "network", "rm", net])


def summary(rows: list[dict]) -> dict:
    valid = [r for r in rows if not r.get("invalid") and not r.get("aborted_before_goose")][:PROTOCOL["n_trials"]]
    n = len(valid)
    k = sum(r["verdict"] == "TASK_VERIFIED_LIMITED" for r in valid)
    first = sum(bool(r["first_submission_schema_valid"]) for r in valid)
    accepted = sum(any(s["decision"] == "ACCEPTED_FOR_VERIFICATION" for s in r["submissions"]) for r in valid)
    walls = sorted(r["wall_seconds"] for r in valid)
    violations = sum(r["isolation_violation"] for r in rows if "isolation_violation" in r)
    inconsistent = sum(r["receipts_inconsistent"] for r in rows if "receipts_inconsistent" in r)
    format_only = all(r["category"] in ("MODELO_FORMATO", "CONTRATO") for r in valid if r["category"])
    if violations or inconsistent:
        decision = "NO-GO"
    elif n < PROTOCOL["n_trials"]:
        decision = "INCOMPLETE"
    elif k >= 4:
        decision = "GO"
    elif k in (2, 3) and format_only:
        decision = "GO_CONDICIONAL"
    else:
        decision = "NO-GO"
    return {"n_valid": n, "verified": k, "verified_wilson95_descriptive": wilson(k, n),
            "first_submission_schema_valid": first, "first_submission_wilson95_descriptive": wilson(first, n),
            "conformant_accepted_after_feedback": accepted, "accepted_wilson95_descriptive": wilson(accepted, n),
            "wall_seconds_min_max": (walls[0], walls[-1]) if walls else None,
            "wall_seconds_median": walls[len(walls) // 2] if walls else None,
            "isolation_violations": violations, "receipts_inconsistent": inconsistent,
            "invalid_attempts": [r["attempt"] for r in rows if r.get("invalid") or r.get("aborted_before_goose")],
            "categories": {r["attempt"]: r.get("category") for r in valid},
            "decision_by_preregistered_rule": decision}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--goose", type=pathlib.Path, required=True)
    p.add_argument("--models", type=pathlib.Path, required=True)
    p.add_argument("--ollama", type=pathlib.Path, required=True)
    p.add_argument("--prereg-commit", required=True)
    a = p.parse_args(argv)
    pre = preconditions(a)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "preconditions.json").write_text(json.dumps(pre, indent=2))
    if not pre["ok"]:
        print(json.dumps(pre, indent=2))
        sys.exit(2)
    rows, replacements, i = [], 0, 0
    while True:
        valid = [r for r in rows if not r.get("invalid") and not r.get("aborted_before_goose")]
        if len(valid) >= PROTOCOL["n_trials"]:
            break
        i += 1
        attempt = f"{PROTOCOL['attempt_prefix']}{i}"
        try:
            row = trial(a, attempt, a.out)
        finally:
            cleanup()
        rows.append(row)
        (a.out / "trials.jsonl").open("a", encoding="utf-8").write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        print(json.dumps({k: row.get(k) for k in ("attempt", "wall_seconds", "verdict", "category", "invalid",
                                                    "isolation_violation", "submission_count")}, ensure_ascii=False),
              flush=True)
        if row.get("isolation_violation") or (row.get("aborted_before_goose") and not row.get("isolation_ok")):
            break                                         # critical isolation failure: stop immediately (NO-GO)
        if row.get("invalid") or row.get("aborted_before_goose"):
            replacements += 1
            if replacements > PROTOCOL["max_replacements"]:
                break
    result = {"protocol": PROTOCOL, "preconditions": pre, "trials": rows, "summary": summary(rows),
              "frozen_after": {"differences": frozen.differences(), "groups": frozen.current()["groups"]}}
    (a.out / "te_p2b_trials.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
