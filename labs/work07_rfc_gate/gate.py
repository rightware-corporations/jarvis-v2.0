"""WORK-07 RFC Editor gate runner (prepared; every external run needs operator authorisation).

Two separately authorised, request-triggered operations (same protocol as WORK-06:
approved code commit + separate request commit changing only the request file,
single-use request_id, no re-runs):

1. ``site-preflight`` (Phase 4, NO model): checks with the REAL PublicBrowser and the
   pinned network path that https://www.rfc-editor.org/search/ works without JavaScript
   and yields traversable results for RFC 9110 / 9112. The driver here is deterministic
   evaluator-side code; it is not product behaviour.
2. ``qwen`` (Phase 5): ONE real Qwen3.5:4b run of the product AgentSession with only
   the browse capability. The model gets the user's instruction plus the site scope and
   start page; never the reference answers (``evaluator.GOLD``).

    python -m labs.work07_rfc_gate.gate --plan-only {site-preflight|qwen}
    python -m labs.work07_rfc_gate.gate --check-request {site-preflight|qwen} --run-attempt N
    python -m labs.work07_rfc_gate.gate --run site-preflight --approved-code-sha X --evidence-dir D
    python -m labs.work07_rfc_gate.gate --run qwen --approved-code-sha X --evidence-dir D

Exit: 0 = completed (verdict in evidence, may be FAIL/NOT_READY), 2 = blocked.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

from rightware import agent_smoke as A
from rightware.agent.web import redact_url, redact_text_urls

SITE = "www.rfc-editor.org"
START_URL = "https://www.rfc-editor.org/search/"
INSTRUCTION = ("Jarvis, entra no site RFC Editor, pesquisa os documentos RFC 9110 e RFC 9112, abre os dois e "
               "explica qual define a semântica do HTTP e qual define o HTTP/1.1. Apresenta os títulos oficiais "
               "e os links das fontes.")
QWEN_LIMITS = {"max_turns": 14, "max_tokens": 768, "tool_calls": 14, "deadline_seconds": 900.0,
               "per_tool": {"web_open": 3, "web_type": 4, "web_submit": 4, "web_follow": 6, "web_find": 6}}
PREFLIGHT_LIMITS = {"max_loads": 12, "queries": ["9110", "9112"]}
OPS = {
    "site-preflight": {"experiment": "WORK07_RFC_SITE_PREFLIGHT", "request": "ops/work07_site_preflight_request.json"},
    "qwen": {"experiment": "WORK07_RFC_QWEN_GATE", "request": "ops/work07_qwen_request.json"},
}


def plan_static_qwen() -> dict:
    """The fixed qwen plan (plain data: usable by GATE 0 on plain Python)."""
    return {"experiment": OPS["qwen"]["experiment"], "sites": [SITE], "start_url": START_URL,
            "openjarvis_pin": A.PIN, "capabilities": ["browse"], "windows_actions": False,
            "instruction": INSTRUCTION, "limits": QWEN_LIMITS, "model": A.MODEL,
            "model_digest": A.EXPECTED_DIGEST, "ollama": A.OLLAMA_VERSION}


def plan(op: str) -> dict:
    if op == "qwen":
        return plan_static_qwen()
    return {"experiment": OPS[op]["experiment"], "sites": [SITE], "start_url": START_URL,
            "openjarvis_pin": A.PIN, "capabilities": ["browse"], "windows_actions": False,
            "model": None, "limits": PREFLIGHT_LIMITS}


def plan_sha256(op: str) -> str:
    """Any change to the plan changes this digest and voids an authorisation."""
    return hashlib.sha256(json.dumps(plan(op), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def check_request(op: str, run_attempt: int, root: Path | None = None) -> dict:
    return A.check_request(run_attempt, root, request_path=OPS[op]["request"],
                           experiment=OPS[op]["experiment"], expected_plan_sha256=plan_sha256(op))


def code_check(approved: str, request_path: str, root: Path | None = None) -> dict:
    """Running code = approved code (apart from the request file), clean tree, pinned OpenJarvis."""
    if not A._hex(approved, 40):
        raise RuntimeError("a full approved code SHA is required")
    head = A._git("rev-parse", "HEAD", root=root)
    if A._git("status", "--porcelain", root=root):
        raise RuntimeError("working tree modified locally")
    if sorted(A._git("diff", "--name-only", approved, head, root=root).split()) not in ([], [request_path]):
        raise RuntimeError("running code differs from the approved code revision")
    gitlink = A._git("ls-tree", "HEAD", "vendor/openjarvis", root=root).split()
    if len(gitlink) < 3 or gitlink[2] != A.PIN:
        raise RuntimeError("OpenJarvis pin mismatch")
    return {"approved_code_sha": approved, "trigger_sha": head}


class RecordingEngine:
    """Records exactly what the MODEL emitted at the engine boundary (tool names, public
    arguments, final text). Scripted/FAKE engines are visible through engine_id."""

    def __init__(self, engine):
        self._engine = engine
        self.engine_id = getattr(engine, "engine_id", "")
        self.responses: list[dict] = []

    def generate(self, messages, **kwargs):
        result = self._engine.generate(messages, **kwargs)
        calls = []
        for tc in result.get("tool_calls") or []:
            raw = tc.get("arguments") or ""
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except (TypeError, ValueError):
                args = {"_unparsed_sha256": hashlib.sha256(str(raw).encode()).hexdigest()}
            if isinstance(args, dict) and isinstance(args.get("url"), str):
                args = {**args, "url": redact_url(args["url"])}
            calls.append({"name": tc.get("name"), "arguments": args if isinstance(args, dict) else {}})
        self.responses.append({"engine_id": self.engine_id, "tool_calls": calls,
                               "content": redact_text_urls((result.get("content") or "")[:4000])})
        return result

    def final_text(self) -> str:
        for r in reversed(self.responses):
            if not r["tool_calls"]:
                return r["content"]
        return ""


# -- Phase 4: site preflight (no model) -------------------------------------------------
READY = {"site-preflight": "READY", "qwen": "PASS"}          # the ONLY accepted verdicts


def site_preflight(browser) -> dict:
    """Deterministic evaluator-side driver over the REAL PublicBrowser. No model.

    READY only if BOTH documents were opened and each one passes ``check_document``
    (HTTP 200, canonical final URL of the same RFC after redirects, official title)."""
    from labs.work07_rfc_gate.evaluator import check_document, doc_number
    loads = 0
    steps: list[dict] = []

    def record(name, step):
        nonlocal loads
        if name in ("open", "submit", "follow"):
            loads += 1
        steps.append({"step": name, "status": step.status, "evidence": step.evidence,
                      "view_excerpt": step.content[:1500]})
        return step

    def result_link(number):
        return next((lid for lid, (u, _) in browser.links.items() if doc_number(u) == number), None)

    start = record("open", browser.open(START_URL))
    result = {"start_status": start.status, "start_final_url": start.evidence.get("final_url"),
              "search_fields": [], "documents": {}, "steps": steps}
    if start.status != "OK":
        return {**result, "events": browser.events, "verdict": "NOT_READY", "reasons": [f"start page {start.status}"]}
    fields = list(browser.fields)
    result["search_fields"] = [{"id": f, "label": browser.fields[f].control.label,
                                "name": browser.fields[f].control.name, "action": redact_url(browser.fields[f].form.action)}
                               for f in fields]
    reasons = []
    if not fields:
        reasons.append("no search field without JavaScript on the start page")
    for number in PREFLIGHT_LIMITS["queries"]:
        found = None
        for fid in fields:
            for text in (number, f"RFC {number}"):
                if loads >= PREFLIGHT_LIMITS["max_loads"] or found:
                    break
                record("type", browser.type(fid, text))
                if record("submit", browser.submit(fid)).status != "OK":
                    continue
                found = result_link(number)
                if not found:
                    info = next((lid for lid, (u, _) in browser.links.items()        # real site: /info/rfcN/ (run 43152996478)
                                 if u.rstrip("/").endswith(f"/info/rfc{number}")), None)
                    if info and loads < PREFLIGHT_LIMITS["max_loads"] \
                            and record("follow", browser.follow(info)).status == "OK":
                        found = result_link(number)
        if not found:
            reasons.append(f"no traversable result link to RFC {number}")
            result["documents"][number] = {"validated": False, "candidate_links": sorted(
                {redact_url(u) for u, _ in browser.links.values() if f"rfc{number}" in u.lower()})[:20]}
            continue
        if loads >= PREFLIGHT_LIMITS["max_loads"]:
            reasons.append(f"load budget exhausted before opening RFC {number}")
            continue
        link_url = redact_url(browser.links[found][0])
        doc = record("follow", browser.follow(found))
        ev = doc.evidence
        problems = [f"RFC {number}: document {doc.status}"] if doc.status != "OK" else \
            check_document(number, ev.get("status"), ev.get("final_url"), ev.get("title"))
        result["documents"][number] = {"link_url": link_url, "outcome": doc.status, "status": ev.get("status"),
                                       "final_url": ev.get("final_url"), "redirected": ev.get("final_url") != link_url,
                                       "title": ev.get("title"), "truncated": ev.get("truncated"),
                                       "validated": not problems, "problems": problems}
        reasons += problems
    validated = [n for n, d in result["documents"].items() if d.get("validated")]
    if sorted(validated) != sorted(PREFLIGHT_LIMITS["queries"]) and not reasons:
        reasons.append("not every document was validated")                    # defence in depth
    result["events"] = browser.events
    return {**result, "verdict": "NOT_READY" if reasons else "READY", "reasons": reasons}


def acceptance(op: str, evidence_dir: Path, technical_exit: int) -> dict:
    """Separate the TECHNICAL execution (did the runner complete?) from the ACCEPTANCE verdict.
    Accepted only when the runner completed (exit 0) AND the recorded verdict is READY (site
    preflight) / PASS (qwen). NOT_READY, FAIL, INCOMPLETE, a missing or unreadable verdict, or
    a blocked runner are never accepted."""
    name = {"site-preflight": "site_preflight.json", "qwen": "qwen_gate.json"}[op]
    verdict, reasons = None, []
    try:
        data = json.loads((evidence_dir / name).read_text(encoding="utf-8"))
        v = data.get("verdict")
        verdict = v.get("verdict") if isinstance(v, dict) else v
        reasons = (v.get("reasons") if isinstance(v, dict) else data.get("reasons")) or []
    except (OSError, ValueError, AttributeError):
        reasons = ["no readable verdict evidence"]
    technical = "COMPLETED" if technical_exit == 0 else ("BLOCKED" if technical_exit == 2 else "ERROR")
    if technical != "COMPLETED":
        verdict = verdict or "NO_VERDICT"
    accepted = technical == "COMPLETED" and verdict == READY[op]
    return {"operation": op, "technical_execution": technical, "technical_exit": technical_exit,
            "verdict": verdict or "NO_VERDICT", "accepted": accepted, "required_verdict": READY[op],
            "reasons": [str(r)[:200] for r in reasons][:20]}


def run(op: str, approved: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=False)
    fixed = plan(op)
    try:
        info = code_check(approved, OPS[op]["request"])
        if op == "qwen":
            info = A.preflight(approved, root=None, request_path=OPS[op]["request"], plan_sha=plan_sha256(op))
    except Exception as exc:
        (out / "preflight.json").write_text(json.dumps({"status": "BLOCKED", "reason": str(exc)[:200]}),
                                            encoding="utf-8")
        print("PREFLIGHT BLOCKED:", str(exc)[:200], file=sys.stderr)
        return 2
    from rightware.agent.browser import PublicBrowser
    from rightware.agent.web import HttpxFetcher
    started = dt.datetime.now(dt.timezone.utc)
    if op == "site-preflight":
        result = site_preflight(PublicBrowser([SITE], HttpxFetcher()))
        evidence = {**fixed, **info, "plan_sha256": plan_sha256(op), "models_called": False,
                    "utc_start": started.isoformat(), "utc_end": dt.datetime.now(dt.timezone.utc).isoformat(),
                    **result}
        (out / "site_preflight.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print("SITE PREFLIGHT:", result["verdict"], json.dumps(result["reasons"], ensure_ascii=False))
        return 0
    from openjarvis.engine.ollama import OllamaEngine
    from rightware.agent.policy import Budgets
    from rightware.agent import session as S
    from labs.work07_rfc_gate.evaluator import evaluate
    lim = QWEN_LIMITS
    if {n: S.TOOLS[n].max_calls for n in lim["per_tool"]} != lim["per_tool"]:
        raise RuntimeError("product per-tool limits differ from the approved plan")
    engine = RecordingEngine(OllamaEngine(host=A.HOST, timeout=lim["deadline_seconds"]))
    session = S.AgentSession(engine, A.MODEL, allow={"browse"}, confirm=lambda q: None, actions=None,
                             sites=(SITE,), start_url=START_URL, audit_path=out / "audit.jsonl",
                             budgets=Budgets(max_calls=lim["tool_calls"], deadline_seconds=lim["deadline_seconds"]),
                             max_turns=lim["max_turns"], max_tokens=lim["max_tokens"])
    reply = session.run(INSTRUCTION)
    outcome = json.loads(S.reply_json(reply))
    events = session.browser.events if session.browser else []
    verdict = evaluate(engine_id=engine.engine_id, model_digest=info["model_digest"],
                       expected_digest=A.EXPECTED_DIGEST, responses=engine.responses, events=events,
                       reply=outcome, answer=engine.final_text(), max_tool_calls=lim["tool_calls"])
    evidence = {**fixed, "models_called": True, **info, "utc_start": started.isoformat(),
                "utc_end": dt.datetime.now(dt.timezone.utc).isoformat(), "model_responses": engine.responses,
                "browser_events": events, "reply": outcome, "model_answer": engine.final_text(),
                "product_reply": reply.text, "verdict": verdict}
    (out / "qwen_gate.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("VERDICT:", json.dumps({k: verdict[k] for k in ("verdict", "reasons")}, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan-only", choices=sorted(OPS))
    g.add_argument("--check-request", choices=sorted(OPS))
    g.add_argument("--run", choices=sorted(OPS))
    g.add_argument("--acceptance", choices=sorted(OPS))
    ap.add_argument("--technical-exit", type=int, default=-1)
    ap.add_argument("--run-attempt", type=int, default=0)
    ap.add_argument("--approved-code-sha", default="")
    ap.add_argument("--evidence-dir", default="")
    args = ap.parse_args(argv)
    if args.plan_only:
        p = plan(args.plan_only)
        print(json.dumps({**p, "plan_sha256": plan_sha256(args.plan_only)}, ensure_ascii=False))
        return 0
    if args.check_request:
        result = check_request(args.check_request, args.run_attempt)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 2
    if not args.evidence_dir:
        print("--evidence-dir is required", file=sys.stderr)
        return 2
    if args.acceptance:
        result = acceptance(args.acceptance, Path(args.evidence_dir), args.technical_exit)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["accepted"] else 1
    return run(args.run, args.approved_code_sha, Path(args.evidence_dir))


if __name__ == "__main__":
    sys.exit(main())
