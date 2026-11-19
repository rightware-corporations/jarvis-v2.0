"""JRV-TE-P2D independent research verifier (RIGHTWARE authority; the model's text is never evidence).

Checks, in order, from RIGHTWARE records only (receipts, egress log, observations, receipted submission):
1. delivery: the report is the receipted, hash-bound ``submit_report`` submission (frozen
   ``verify.submitted_report``); answers in the final message / "thinking" never count;
2. egress ↔ receipts: every final (non-redirect) response the egress service delivered corresponds, in order,
   to one executed page-read receipt with the same URL, HTTP status and raw SHA-256, and vice versa; every
   request the egress service ANSWERED passed the egress policy (no unauthorised destination);
3. observations: each cited observation is an executed, bound, audited, HTTP 200 page read whose raw hash
   equals the receipt's and whose stored text hash matches;
4. claims: a claim gets credit only if its ``source_url`` is the cited observation's URL and its ``quote``
   (normalised whitespace/case, ≥ ``min_quote_chars``) occurs in the text RIGHTWARE showed for that
   observation. Every source must be an observed URL. One uncredited claim or unobserved source → not verified;
5. semantics (pre-registered, protected reference): for each reference fact, the answer AND at least one
   CREDITED claim (text and quote) must match the fact pattern; the required source must be observed and cited.
Verdicts: RESEARCH_VERIFIED_LIMITED | ABSTAINED | NOT_VERIFIED. Source verification is not proof that every
sentence of the answer is true; the semantic rubric covers only the pre-registered facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from labs.te_p2a_gateway.verify import submitted_report
from labs.te_p2d_public.egress import EgressPolicy

REFERENCE_DIR = Path(__file__).resolve().parent
PAGE_TOOLS = ("web_open", "web_follow")


def load_reference(question_id: str) -> dict:
    path = REFERENCE_DIR / f"reference_{question_id.lower().replace('-', '_')}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def _strip_fragment(url) -> str:
    return str(url).split("#", 1)[0] if isinstance(url, str) else ""


def egress_correspondence(receipts, egress_rows: list[dict], policy: EgressPolicy) -> dict:
    final = [(r.get("url"), r.get("status"), r.get("sha256")) for r in egress_rows
             if r.get("decision") == "OK" and r.get("status") not in (301, 302, 303, 307, 308)]
    reads = [(r.final_url, r.http_status, r.raw_sha256) for r in sorted(receipts, key=lambda r: r.sequence)
             if r.tool in PAGE_TOOLS and r.executed and r.binding == "BOUND" and r.http_status is not None]
    unauthorised = [r.get("seq") for r in egress_rows if r.get("decision") == "OK" and policy.check(r.get("url"))]
    first = next((i for i, (a, b) in enumerate(zip(reads, final)) if a != b), None)
    if first is None and len(reads) != len(final):
        first = min(len(reads), len(final))
    return {"match": first is None and not unauthorised, "first_mismatch_index": first,
            "receipt_reads": len(reads), "egress_final_responses": len(final),
            "unauthorised_egress": unauthorised}


def verify_research(receipts, egress_rows, observations, submissions, reference: dict,
                    policy: EgressPolicy | None = None) -> dict:
    policy = policy or EgressPolicy()
    result = {"verdict": "NOT_VERIFIED", "reasons": [], "limits": [
        "source/observation/quote checks prove what was READ and CITED, not that every sentence is true",
        "semantic rubric covers only the pre-registered facts of one question"]}
    reasons = result["reasons"]
    corr = egress_correspondence(receipts, egress_rows, policy)
    result["egress_receipt_correspondence"] = corr
    if not corr["match"]:
        reasons.append("egress/receipt correspondence failed")
    defects = [r.sequence for r in receipts if r.binding != "BOUND" or r.call_id_status != "SUPPLIED"
               or (r.executed and r.audit != "OK")]
    result["receipt_defects"] = defects
    if defects:
        reasons.append("receipt defects")
    report, seq = submitted_report(receipts, submissions or [])
    result["report_delivery_receipt"] = seq
    if not isinstance(report, dict):
        reasons.append("no receipted conformant report")
        return result
    if report.get("question_id") != reference["question_id"]:
        reasons.append("question_id mismatch")
    by_seq = {r.sequence: r for r in receipts}
    obs = {int(k): v for k, v in (observations.items() if isinstance(observations, dict) else
                                  ((o["observation"], o) for o in observations))}
    observed_urls = set()
    valid_obs = {}
    for oid, o in obs.items():
        r = by_seq.get(oid)
        ok = (r is not None and r.tool in PAGE_TOOLS and r.executed and r.status == "OK" and r.binding == "BOUND"
              and r.audit == "OK" and r.http_status == 200 and r.raw_sha256 and r.raw_sha256 == o.get("raw_sha256")
              and _strip_fragment(r.final_url) == _strip_fragment(o.get("final_url"))
              and hashlib.sha256(str(o.get("text", "")).encode("utf-8")).hexdigest() == o.get("text_sha256"))
        if ok:
            valid_obs[oid] = o
            observed_urls.add(_strip_fragment(r.final_url))
    result["valid_observations"] = sorted(valid_obs)
    min_quote = int(reference.get("min_quote_chars", 12))
    credited, uncredited = [], []
    for c in report.get("claims") or []:
        o = valid_obs.get(c.get("observation"))
        quote = _norm(c.get("quote", ""))
        why = None
        if o is None:
            why = "observation not found or invalid"
        elif _strip_fragment(c.get("source_url")) != _strip_fragment(o["final_url"]):
            why = "source_url is not the cited observation's URL"
        elif len(quote) < min_quote:
            why = "quote too short"
        elif quote not in _norm(o["text"]):
            why = "quote not found in the observed text"
        (uncredited if why else credited).append({"claim_id": c.get("claim_id"), **({"why": why} if why else {})})
    result["claims_credited"], result["claims_uncredited"] = credited, uncredited
    unobserved = [s for s in report.get("sources") or [] if _strip_fragment(s) not in observed_urls]
    result["unobserved_sources"] = unobserved
    if report.get("abstained") is True:
        result["verdict"] = "ABSTAINED" if not reasons else "NOT_VERIFIED"
        return result
    if uncredited:
        reasons.append("claims without verifiable support")
    if unobserved:
        reasons.append("sources not consulted through the Gateway")
    credited_ids = {c["claim_id"] for c in credited}
    claims = {c.get("claim_id"): c for c in report.get("claims") or []}
    facts = []
    for f in reference["facts"]:
        pat = re.compile(f["pattern"], re.I)
        in_answer = bool(pat.search(str(report.get("answer", ""))))
        supported = [cid for cid in credited_ids if pat.search(str(claims[cid].get("text", "")))
                     and pat.search(str(claims[cid].get("quote", "")))]
        facts.append({"fact_id": f["fact_id"], "in_answer": in_answer, "supported_by": sorted(supported)})
    req = _strip_fragment(reference["required_source"])
    cites_required = any(_strip_fragment(claims[cid].get("source_url")) == req for cid in credited_ids)
    semantic = all(x["in_answer"] and x["supported_by"] for x in facts) and cites_required
    result["semantic"] = {"facts": facts, "required_source_cited_by_credited_claim": cites_required,
                          "gate": "PASS" if semantic else "FAIL"}
    if not semantic:
        reasons.append("semantic rubric failed")
    if not reasons:
        result["verdict"] = "RESEARCH_VERIFIED_LIMITED"
    return result
