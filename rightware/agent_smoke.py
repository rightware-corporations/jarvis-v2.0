"""WORK-05 real-Qwen smoke for the PRODUCT agent (prepared; runs only when authorised).

One fixed instruction, one fixed public page, read-only web, no Windows
effects, no shell, no filesystem tool. It proves something only if the tool
call was PROPOSED BY THE REAL MODEL: every engine response is recorded at the
engine boundary (``RecordingEngine``), and PASS requires engine_id 'ollama',
the pinned model digest and a model-proposed ``web_read`` for the fixed URL.

    python -m rightware.agent_smoke --plan-only            # prints the plan and its SHA-256
    python -m rightware.agent_smoke --check-request --run-attempt N   # authorisation gate (no model)
    python -m rightware.agent_smoke --approved-code-sha <40-hex> --evidence-dir DIR

Authorisation (WORK-06, branch ``develop``): the operator approves an exact CODE
commit and the fixed plan; a separate REQUEST commit adds the request file
``ops/work05_smoke_request.json`` = {experiment, request_id, approved_code_sha,
plan_sha256, authorized_by}. The request commit may differ from the approved
code ONLY in that file; request_id must increase by exactly one per request
commit (single use, no replay); a GitHub re-run (run attempt > 1) is refused.

Exit: 0 = run completed (verdict in evidence, may be FAIL), 2 = preflight or
environment blocked. A PASS is diagnostic evidence for this single case,
never a claim of general agent quality.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

PIN = "f21d902f4d3bd7f0f3f138f1a4613019a394b549"
MODEL = "qwen3.5:4b"
EXPECTED_DIGEST = "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04"
REQUEST_PATH = "ops/work05_smoke_request.json"
EXPERIMENT = "WORK05_PRODUCT_AGENT_REAL_SMOKE"
REQUEST_KEYS = {"experiment", "request_id", "approved_code_sha", "plan_sha256", "authorized_by"}
OLLAMA_VERSION = "0.40.15"
HOST = "http://127.0.0.1:11434"
URL = "https://example.com/"
INSTRUCTION = ("Lê a página " + URL + " com a ferramenta web_read e diz-me, numa frase em português, "
               "para que serve este domínio segundo a própria página. Cita o endereço.")
# Words present in the fixed page text; overlap is reported, NOT treated as factual proof.
PAGE_TERMS = ("exempl", "example", "document", "ilustra", "illustrat")
LIMITS = {"max_turns": 4, "max_tokens": 512, "tool_calls": 3, "deadline_seconds": 300.0}
ROOT = Path(__file__).resolve().parents[1]
# Kept outside rightware/agent/ on purpose: it needs subprocess (git) for preflight,
# which the product agent package must never import.


class RecordingEngine:
    """Wraps the real engine; records what the MODEL emitted (not what a script injected)."""

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
                args = None
            calls.append({"name": tc.get("name"), "url": (args or {}).get("url") if isinstance(args, dict) else None,
                          "arguments_sha256": hashlib.sha256(str(raw).encode()).hexdigest()})
        self.responses.append({"engine_id": self.engine_id, "tool_calls": calls,
                               "content_chars": len(result.get("content") or "")})
        return result


def classify(*, engine_id: str, model_digest: str | None, expected_digest: str,
             responses: list[dict], completion: str, outcomes: list[dict], flags: list[str],
             sources: list[dict], answer: str) -> dict:
    """PASS / FAIL / INCOMPLETE with reasons. Pure function (unit-tested)."""
    proposed = [c for r in responses for c in r["tool_calls"]]
    proposed_web = [c for c in proposed if c["name"] == "web_read"]
    reasons: list[str] = []
    if engine_id != "ollama" or model_digest != expected_digest:
        return {"verdict": "INCOMPLETE", "reasons": ["not a real pinned-model run (engine or digest)"],
                "model_proposed_web_read": bool(proposed_web)}
    if completion == "ERROR":
        return {"verdict": "INCOMPLETE", "reasons": ["engine or audit error"], "model_proposed_web_read": bool(proposed_web)}
    web = [o for o in outcomes if o["tool"] == "web_read"]
    if web and all(o["status"] in ("FAILED", "HTTP_ERROR") for o in web):
        # The model did its part; the external page or network did not (not a model FAIL).
        return {"verdict": "INCOMPLETE", "reasons": ["fixed page unreachable or erroring from the runner"],
                "model_proposed_web_read": bool(proposed_web)}
    if not proposed_web:
        reasons.append("the model never proposed web_read")
    elif not any(c["url"] and c["url"].rstrip("/") == URL.rstrip("/") for c in proposed_web):
        reasons.append("web_read was proposed for a different URL")
    if any(c["name"] != "web_read" for c in proposed):
        reasons.append("the model proposed a tool other than web_read")
    if completion != "ANSWERED_WITH_SOURCES":
        reasons.append(f"completion {completion}")
    if not any(s.get("final_url", "").rstrip("/") == URL.rstrip("/") for s in sources):
        reasons.append("the fixed page is not a recorded source")
    for f in ("UNSUPPORTED_READ_CLAIM", "UNVERIFIED_EFFECT_CLAIM", "AUDIT_FAILED"):
        if f in flags:
            reasons.append(f"flag {f}")
    if len(proposed) > LIMITS["tool_calls"]:
        reasons.append("more tool proposals than the budget")
    if not answer.strip():
        reasons.append("empty answer")
    overlap = any(t in answer.lower() for t in PAGE_TERMS)
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons,
            "model_proposed_web_read": bool(proposed_web), "answer_mentions_page_terms": overlap,
            "answer_factually_verified": False}


def plan() -> dict:
    """The fixed experiment. Any change to it changes plan_sha256 and voids an authorisation."""
    return {"experiment": EXPERIMENT, "url": URL, "instruction": INSTRUCTION, "capabilities": ["web"],
            "windows_actions": False, "limits": LIMITS, "model": MODEL, "model_digest": EXPECTED_DIGEST,
            "ollama": OLLAMA_VERSION, "openjarvis_pin": PIN}


def plan_sha256() -> str:
    return hashlib.sha256(json.dumps(plan(), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _hex(value, n) -> bool:
    return isinstance(value, str) and len(value) == n and all(c in "0123456789abcdef" for c in value)


def validate_request(req, *, trigger_sha: str, changed_files: list[str], previous_request_id: int,
                     request_commits: int, run_attempt: int, approved_is_ancestor: bool) -> list[str]:
    """Pure authorisation check. Returns the list of problems (empty = authorised)."""
    if not isinstance(req, dict) or set(req) != REQUEST_KEYS:
        return ["request keys must be exactly " + ", ".join(sorted(REQUEST_KEYS))]
    problems = []
    if req["experiment"] != EXPERIMENT:
        problems.append("wrong experiment")
    rid = req["request_id"]
    if not isinstance(rid, int) or isinstance(rid, bool) or rid < 1:
        problems.append("request_id must be a positive integer")
    else:
        if rid != previous_request_id + 1:
            problems.append("request_id must be exactly previous + 1 (replay or gap)")
        if rid != request_commits:
            problems.append("request_id must equal the number of request commits (single use)")
    if not _hex(req["approved_code_sha"], 40):
        problems.append("approved_code_sha must be a full lowercase 40-hex SHA")
    elif req["approved_code_sha"] == trigger_sha:
        problems.append("the request must be a separate commit after the approved code")
    if req["plan_sha256"] != plan_sha256():
        problems.append("plan_sha256 does not match the fixed plan")
    who = req["authorized_by"]
    if not isinstance(who, str) or not who.strip() or len(who) > 200 or "\n" in who:
        problems.append("authorized_by must be a short single-line text")
    if changed_files != [REQUEST_PATH]:
        problems.append("the request commit may change only " + REQUEST_PATH)
    if not approved_is_ancestor:
        problems.append("approved_code_sha is not an ancestor of the request commit")
    if run_attempt != 1:
        problems.append("re-runs are refused: push a new request instead")
    return problems


def _git(*args: str, root: Path | None = None) -> str:
    return subprocess.check_output(["git", *args], cwd=root or ROOT, text=True).strip()


def check_request(run_attempt: int, root: Path | None = None) -> dict:
    """Gather the git facts for the request at HEAD and validate them (no model, no network)."""
    head = _git("rev-parse", "HEAD", root=root)
    try:
        req = json.loads(_git("show", f"HEAD:{REQUEST_PATH}", root=root))
    except (subprocess.CalledProcessError, ValueError):
        return {"ok": False, "problems": ["request file missing or not JSON at HEAD"], "trigger_sha": head}
    try:
        prev = json.loads(_git("show", f"HEAD^:{REQUEST_PATH}", root=root)).get("request_id", 0)
    except (subprocess.CalledProcessError, ValueError):
        prev = 0
    prev = prev if isinstance(prev, int) and not isinstance(prev, bool) else -1
    approved = req.get("approved_code_sha") if isinstance(req, dict) else None
    changed, ancestor = [], False
    if _hex(approved, 40):
        try:
            changed = sorted(_git("diff", "--name-only", approved, head, root=root).split())
            subprocess.check_call(["git", "merge-base", "--is-ancestor", approved, head], cwd=root or ROOT)
            ancestor = True
        except subprocess.CalledProcessError:
            ancestor = False
    commits = int(_git("rev-list", "--count", "HEAD", "--", REQUEST_PATH, root=root) or 0)
    problems = validate_request(req, trigger_sha=head, changed_files=changed, previous_request_id=prev,
                                request_commits=commits, run_attempt=run_attempt, approved_is_ancestor=ancestor)
    return {"ok": not problems, "problems": problems, "trigger_sha": head,
            "approved_code_sha": approved if _hex(approved, 40) else None,
            "request_id": req.get("request_id") if isinstance(req, dict) else None}


def _local(path: str) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(HOST + path, timeout=15) as r:
        return json.load(r)


def preflight(approved_code_sha: str, expected_digest: str = EXPECTED_DIGEST, root: Path | None = None) -> dict:
    if not _hex(approved_code_sha, 40) or expected_digest != EXPECTED_DIGEST:
        raise RuntimeError("a full approved code SHA and the fixed model digest are required")
    head = _git("rev-parse", "HEAD", root=root)
    if _git("status", "--porcelain", root=root):
        raise RuntimeError("working tree modified locally")
    if sorted(_git("diff", "--name-only", approved_code_sha, head, root=root).split()) not in ([], [REQUEST_PATH]):
        raise RuntimeError("running code differs from the approved code revision")
    gitlink = _git("ls-tree", "HEAD", "vendor/openjarvis", root=root).split()
    if len(gitlink) < 3 or gitlink[2] != PIN or \
            _git("-C", "vendor/openjarvis", "rev-parse", "HEAD", root=root) != PIN:
        raise RuntimeError("OpenJarvis pin mismatch")
    if _local("/api/version").get("version") != OLLAMA_VERSION:
        raise RuntimeError("Ollama version mismatch")
    digest = {m.get("name"): m.get("digest") for m in _local("/api/tags").get("models", [])}.get(MODEL)
    if digest != expected_digest:
        raise RuntimeError("model digest mismatch")
    return {"approved_code_sha": approved_code_sha, "trigger_sha": head, "openjarvis_pin": PIN,
            "ollama": OLLAMA_VERSION, "model": MODEL, "model_digest": digest, "plan_sha256": plan_sha256()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--check-request", action="store_true")
    ap.add_argument("--run-attempt", type=int, default=0)
    ap.add_argument("--approved-code-sha", default="")
    ap.add_argument("--evidence-dir", default="")
    args = ap.parse_args(argv)
    fixed = plan()
    if args.plan_only:
        print(json.dumps({**fixed, "plan_sha256": plan_sha256(), "models_called": False}, ensure_ascii=False))
        return 0
    if args.check_request:
        result = check_request(args.run_attempt)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 2
    if not args.evidence_dir:
        print("--evidence-dir is required", file=sys.stderr)
        return 2
    out = Path(args.evidence_dir)
    out.mkdir(parents=True, exist_ok=False)
    try:
        info = preflight(args.approved_code_sha)
    except Exception as exc:
        (out / "preflight.json").write_text(json.dumps({"status": "BLOCKED", "reason": str(exc)[:200]}), encoding="utf-8")
        print("PREFLIGHT BLOCKED:", str(exc)[:200], file=sys.stderr)
        return 2
    from openjarvis.engine.ollama import OllamaEngine
    from rightware.agent.policy import Budgets
    from rightware.agent.session import AgentSession, reply_json

    engine = RecordingEngine(OllamaEngine(host=HOST, timeout=LIMITS["deadline_seconds"]))
    session = AgentSession(engine, MODEL, allow={"web"}, confirm=lambda q: None, actions=None,
                           audit_path=out / "audit.jsonl",
                           budgets=Budgets(max_calls=LIMITS["tool_calls"], deadline_seconds=LIMITS["deadline_seconds"]),
                           max_turns=LIMITS["max_turns"], max_tokens=LIMITS["max_tokens"])
    started = dt.datetime.now(dt.timezone.utc)
    reply = session.run(INSTRUCTION)
    outcome = json.loads(reply_json(reply))
    verdict = classify(engine_id=engine.engine_id, model_digest=info["model_digest"],
                       expected_digest=EXPECTED_DIGEST, responses=engine.responses,
                       completion=reply.completion, outcomes=outcome["outcomes"], flags=reply.flags,
                       sources=reply.sources, answer=reply.text)
    evidence = {**fixed, "models_called": True, **info, "utc_start": started.isoformat(),
                "utc_end": dt.datetime.now(dt.timezone.utc).isoformat(),
                "model_responses": engine.responses, "reply": outcome, "answer": reply.text,
                "verdict": verdict}
    (out / "smoke.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("VERDICT:", json.dumps(verdict, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
