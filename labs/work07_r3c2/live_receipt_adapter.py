"""WORK-07 R3-C2-019 — real-run evidence correlation, LAB ONLY.

Consumes real AgentSession traces, browser events and ToolOutcome objects; never
writes to production or creates a fictional task/run/outcome ID. Conservative:
unique trace/outcome/browser matching is necessary, NEVER sufficient to prove
the identity/authenticity of a document or factual correctness of an answer.

One result may be correlated by content hash, tool, status and browser metadata.
On a collision/absence, return UNKNOWN. Hashes from TaskTrace are truncated
observational digests, not cryptographic proof. This is an exploratory adapter,
not a durable, transactional execution receipt or a production G3 verifier.
"""
from __future__ import annotations
import dataclasses
import hashlib

LOAD_TOOLS = frozenset(("web_open", "web_follow", "web_submit"))


@dataclasses.dataclass(frozen=True)
class ObservedReceipt:
    tool: str
    status: str
    url: str | None
    content_digest: str | None
    call_id: str | None
    grade: str       # G1 | G2_OBSERVATIONAL | UNKNOWN
    reason: str


def correlate(session, reply) -> tuple[ObservedReceipt, ...]:
    """Fail closed: correlate only unique exact observations, never infer IDs."""
    trace = getattr(session, "trace", None)
    browser = getattr(session, "browser", None)
    proposals = [p for turn in (trace.turns if trace is not None else [])
                 for p in turn.get("proposals", [])]
    outcomes = list(getattr(reply, "outcomes", []))
    events = list(browser.events if browser is not None else [])
    rows = []
    for o in outcomes:
        ev = getattr(o, "evidence", {}) or {}
        url = ev.get("final_url")
        digest = hashlib.sha256(o.content.encode("utf-8")).hexdigest()[:16]
        # G2 requires a unique *approved* traced proposal with matching observed
        # outcome content. This can prove correlation in this particular run,
        # not immutable identity nor authorized replay beyond it.
        matching_proposals = [
            p for p in proposals
            if p.get("name") == o.tool and p.get("status") == o.status
            and p.get("result_sha256") == digest
            and p.get("decision") == "APPROVED"
            and p.get("call_id")
        ]
        matching_outcomes = [
            other for other in outcomes
            if other.tool == o.tool and other.status == o.status
            and hashlib.sha256(other.content.encode("utf-8")).hexdigest()[:16] == digest
        ]
        # Browser events do not emit tool call ids. Their metadata must uniquely
        # match this ToolOutcome, otherwise retain only G1.
        matching_events = [
            e for e in events
            if e.get("final_url") == url and e.get("outcome") == o.status
            and e.get("sha256") == ev.get("sha256") and url
        ]
        trace_ok = len(matching_proposals) == 1 and len(matching_outcomes) == 1
        browser_ok = (o.tool not in LOAD_TOOLS or len(matching_events) == 1)
        if o.status not in ("OK", "VERIFIED"):
            grade, reason, cid = "UNKNOWN", "unsuccessful_or_nonexecuted", None
        elif not trace_ok:
            grade, reason, cid = "G1", "missing_or_ambiguous_traced_call", None
        elif not browser_ok:
            grade, reason, cid = "G1", "missing_or_ambiguous_browser_event", None
        else:
            grade, reason = "G2_OBSERVATIONAL", "unique_in_memory_link_not_durable_receipt"
            cid = matching_proposals[0]["call_id"]
        rows.append(ObservedReceipt(o.tool, o.status, url, digest, cid, grade, reason))
    return tuple(rows)


def observed_originals(session, reply, expected: dict[str, str]) -> dict[str, str]:
    """G1-only proof of observation: NOT semantic original validation (G3).

    expected: objective_id -> preapproved exact original URL; a trusted preset
    must supply these and validate original identity elsewhere.
    """
    rows = correlate(session, reply)
    result = {}
    for oid, url in expected.items():
        matching = [r for r in rows if r.url == url and r.status == "OK"
                    and r.tool in LOAD_TOOLS]
        if len(matching) == 1:
            result[oid] = matching[0].grade
        elif matching:
            result[oid] = "UNKNOWN_AMBIGUOUS"
        else:
            result[oid] = "INCOMPLETE"
    return result
