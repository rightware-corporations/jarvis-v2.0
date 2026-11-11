"""WORK-05 real-Qwen smoke for the PRODUCT agent (prepared; runs only when authorised).

One fixed instruction, one fixed public page, read-only web, no Windows
effects, no shell, no filesystem tool. It proves something only if the tool
call was PROPOSED BY THE REAL MODEL: every engine response is recorded at the
engine boundary (``RecordingEngine``), and PASS requires engine_id 'ollama',
the pinned model digest and a model-proposed ``web_read`` for the fixed URL.

    python -m rightware.agent_smoke --plan-only
    python -m rightware.agent_smoke --expect-sha <40-hex> --expected-digest <64-hex> --evidence-dir DIR

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


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _local(path: str) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(HOST + path, timeout=15) as r:
        return json.load(r)


def preflight(expect_sha: str, expected_digest: str) -> dict:
    if len(expect_sha) != 40 or len(expected_digest) != 64:
        raise RuntimeError("full 40-char SHA and 64-char digest are required")
    if _git("rev-parse", "HEAD") != expect_sha:
        raise RuntimeError("repository SHA differs from the authorised revision")
    if _git("status", "--porcelain", "--", "rightware"):
        raise RuntimeError("product code modified locally")
    if _git("ls-tree", "HEAD", "vendor/openjarvis").split()[2] != PIN or \
            _git("-C", "vendor/openjarvis", "rev-parse", "HEAD") != PIN:
        raise RuntimeError("OpenJarvis pin mismatch")
    if _local("/api/version").get("version") != OLLAMA_VERSION:
        raise RuntimeError("Ollama version mismatch")
    digest = {m.get("name"): m.get("digest") for m in _local("/api/tags").get("models", [])}.get(MODEL)
    if digest != expected_digest:
        raise RuntimeError("model digest mismatch")
    return {"repo_sha": expect_sha, "openjarvis_pin": PIN, "ollama": OLLAMA_VERSION,
            "model": MODEL, "model_digest": digest}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--expect-sha", default="")
    ap.add_argument("--expected-digest", default="")
    ap.add_argument("--evidence-dir", default="")
    args = ap.parse_args(argv)
    plan = {"experiment": "WORK05_PRODUCT_AGENT_REAL_SMOKE", "url": URL, "instruction": INSTRUCTION,
            "capabilities": ["web"], "windows_actions": False, "limits": LIMITS, "model": MODEL,
            "models_called": False}
    if args.plan_only:
        print(json.dumps(plan, ensure_ascii=False))
        return 0
    if not args.evidence_dir:
        print("--evidence-dir is required", file=sys.stderr)
        return 2
    out = Path(args.evidence_dir)
    out.mkdir(parents=True, exist_ok=False)
    try:
        info = preflight(args.expect_sha, args.expected_digest)
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
                       expected_digest=args.expected_digest, responses=engine.responses,
                       completion=reply.completion, outcomes=outcome["outcomes"], flags=reply.flags,
                       sources=reply.sources, answer=reply.text)
    evidence = {**plan, "models_called": True, **info, "utc_start": started.isoformat(),
                "utc_end": dt.datetime.now(dt.timezone.utc).isoformat(),
                "model_responses": engine.responses, "reply": outcome, "answer": reply.text,
                "verdict": verdict}
    (out / "smoke.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("VERDICT:", json.dumps(verdict, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
