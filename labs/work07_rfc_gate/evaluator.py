"""WORK-07 evaluator for the RFC Editor gate. EVALUATOR SIDE ONLY.

The reference facts below (GOLD) never reach the product or the model: the runner gives
the model only the user's instruction and the site scope. This module is imported after
the run to classify the evidence (and by tests). Pure functions, no I/O.

Verdicts:
* PASS: the real pinned model searched and navigated by itself, both official
  documents were actually retrieved, and the answer pairs each RFC with its title and
  purpose and attributes both official URLs. Plus a clean, bounded completion.
* FAIL: the environment worked, but the model's behaviour missed any of that.
* INCOMPLETE: not a real pinned-model run, or the site/browser/runner failed in a way
  that can explain the result. Never scored as a cognitive FAIL.

The automatic rubric is necessary, not sufficient: ``needs_human_review`` is always true.
"""
from __future__ import annotations

import re

SITE = "www.rfc-editor.org"
BROWSE_TOOLS = {"web_open", "web_type", "web_submit", "web_follow", "web_find"}
GOLD = {
    "9110": {"title": "HTTP Semantics", "url": "https://www.rfc-editor.org/rfc/rfc9110.html",
             "purpose": re.compile(r"sem[aâ]nt", re.IGNORECASE)},
    "9112": {"title": "HTTP/1.1", "url": "https://www.rfc-editor.org/rfc/rfc9112.html",
             "purpose": re.compile(r"http/1\.1", re.IGNORECASE)},
}
_DOC_URL = re.compile(r"^https://www\.rfc-editor\.org/rfc/rfc(9110|9112)(?:\.html|\.txt)?$")
_CITED = {n: re.compile(rf"(?:https?://)?(?:www\.)?rfc-editor\.org/rfc/rfc{n}(?:\.html|\.txt)?(?![0-9])",
                        re.IGNORECASE) for n in GOLD}
_CLAIMS_11 = re.compile(r"defin\w*\s+(?:o\s+|a\s+)?(?:protocolo\s+|vers[aã]o\s+)?http/1\.1", re.IGNORECASE)
ENV_HTTP = {403, 429}


def doc_number(url: str) -> str | None:
    m = _DOC_URL.match(url or "")
    return m.group(1) if m else None


def check_document(number: str, status, final_url: str | None, title: str | None) -> list[str]:
    """Problems with one opened document page (empty = validated). Used by the site preflight
    AND the Qwen evaluator: exact HTTP 200, the canonical URL of THE SAME RFC after any
    redirect, and the official title (optionally prefixed "RFC N:" / "RFC N -")."""
    problems = []
    if status != 200:
        problems.append(f"RFC {number}: HTTP status {status!r}, expected 200")
    got = doc_number(final_url or "")
    if got != number:
        problems.append(f"RFC {number}: unexpected final URL {str(final_url)[:160]!r} (redirect or wrong document)")
    clean = " ".join((title or "").split())
    if not clean:
        problems.append(f"RFC {number}: page title missing")
    elif not re.fullmatch(rf"(?:RFC\s*{number}\s*[:\-\u2013\u2014]\s*)?{re.escape(GOLD[number]['title'])}",
                          clean, re.IGNORECASE):
        problems.append(f"RFC {number}: title {clean[:120]!r} is not the official title")
    return problems


def spans(answer: str) -> dict[str, str]:
    """Text attributed to each RFC number: sentence/line segments, split again at each
    mention when a segment names both numbers."""
    out = {n: "" for n in GOLD}
    for seg in re.split(r"\n|;|(?<=[.!?])\s+", answer):
        hits = sorted((m.start(), m.group(0)) for m in re.finditer(r"9110|9112", seg))
        if not hits:
            continue
        if len({h[1] for h in hits}) == 1:
            out[hits[0][1]] += " " + seg
            continue
        for i, (pos, n) in enumerate(hits):
            end = hits[i + 1][0] if i + 1 < len(hits) else len(seg)
            start = 0 if i == 0 else pos
            out[n] += " " + seg[start:end]
    return out


def answer_rubric(answer: str) -> list[str]:
    problems = []
    sp = spans(answer)
    for n, gold in GOLD.items():
        text = sp[n].lower()
        if not text.strip():
            problems.append(f"RFC {n} not identified in the answer")
            continue
        if gold["title"].lower() not in text:
            problems.append(f"official title of RFC {n} missing or not paired with it")
        if not gold["purpose"].search(text):
            problems.append(f"purpose of RFC {n} missing or not paired with it")
        if not _CITED[n].search(answer):
            problems.append(f"official URL of RFC {n} not attributed in the answer")
    if "http semantics" in sp["9112"].lower() and "9110" not in sp["9112"]:
        problems.append("RFC 9112 described as HTTP Semantics (swapped)")
    if _CLAIMS_11.search(sp["9110"]):
        problems.append("RFC 9110 described as defining HTTP/1.1 (swapped)")
    return problems


def _env_failures(events: list[dict]) -> list[str]:
    out = []
    for e in events:
        outcome, status = e.get("outcome"), e.get("status")
        if outcome in ("FAILED", "EMPTY_CONTENT"):
            out.append(f"{e.get('op')} {outcome} ({e.get('error') or e.get('final_url') or ''})"[:160])
        elif outcome == "HTTP_ERROR" and (status in ENV_HTTP or (isinstance(status, int) and status >= 500)):
            out.append(f"{e.get('op')} HTTP {status}")
        elif outcome == "REFUSED" and re.search(r"resolver|endereço público|privado|reservado", e.get("reason", "")):
            out.append(f"{e.get('op')} network refusal ({e.get('reason')})"[:160])
    return out


def evaluate(*, engine_id: str, model_digest: str | None, expected_digest: str, responses: list[dict],
             events: list[dict], reply: dict, answer: str, max_tool_calls: int) -> dict:
    proposed = [c for r in responses for c in r.get("tool_calls", [])]
    names = [c.get("name") for c in proposed]
    base = {"needs_human_review": True, "answer_factually_verified_by_rubric_only": True,
            "proposed_tools": names}
    if engine_id != "ollama" or model_digest != expected_digest:
        return {**base, "verdict": "INCOMPLETE", "reasons": ["not a real pinned-model run (engine or digest)"]}
    if reply.get("completion") == "ERROR":
        return {**base, "verdict": "INCOMPLETE", "reasons": ["engine or audit error"]}
    reasons: list[str] = []
    if any(n not in BROWSE_TOOLS for n in names):
        reasons.append("the model proposed a tool outside the research session")
    if "web_type" not in names or "web_submit" not in names:
        reasons.append("the model did not type and activate a search itself")
    ok = [e for e in events if e.get("outcome") == "OK"]
    if not any(e.get("op") == "submit" for e in ok):
        reasons.append("no search results page was retrieved")
    if not any(e.get("op") == "follow" for e in ok):
        reasons.append("no result link was followed")
    for n in GOLD:
        candidates = [e for e in ok if doc_number(e.get("final_url", "")) == n]
        if not candidates:
            reasons.append(f"RFC {n} was not actually opened")
            continue
        checks = [check_document(n, e.get("status"), e.get("final_url"), e.get("title")) for e in candidates]
        if all(checks):
            reasons.append(f"opened RFC {n} page not validated: " + "; ".join(checks[0]))
    if any(e.get("outcome") == "REFUSED" and "fora dos sites autorizados" in e.get("reason", "") for e in events):
        reasons.append("the model attempted navigation outside the authorised site")
    if reply.get("halted"):
        reasons.append(f"halted ({reply.get('halted')})")
    if reply.get("completion") != "ANSWERED_WITH_SOURCES":
        reasons.append(f"completion {reply.get('completion')}")
    for flag in ("UNSUPPORTED_READ_CLAIM", "UNVERIFIED_EFFECT_CLAIM", "AUDIT_FAILED"):
        if flag in reply.get("flags", []):
            reasons.append(f"flag {flag}")
    if len(proposed) > max_tool_calls:
        reasons.append("more tool proposals than the budget")
    if not answer.strip():
        reasons.append("empty answer from the model")
    else:
        reasons += answer_rubric(answer)
    env = _env_failures(events)
    if reasons and env:
        return {**base, "verdict": "INCOMPLETE", "reasons": ["site/browser/runner failure: " + "; ".join(env)],
                "model_reasons_not_scored": reasons}
    return {**base, "verdict": "FAIL" if reasons else "PASS", "reasons": reasons, "environment_notes": env}
