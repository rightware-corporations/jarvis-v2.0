"""WORK-07 R3-C2-014: experimental objective/receipt contracts (TEST-ONLY).

Not wired to AgentSession; no claims about Qwen, model extraction or production.
Trusted objective contracts are INPUTS, not guessed from natural language.
Synthetic receipt IDs test verifier logic, NOT current runtime emission.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Iterable


@dataclass(frozen=True)
class Objective:
    oid: str
    verb: str
    target: str
    mandatory: bool = True
    condition: str | None = None
    after: str | None = None


@dataclass(frozen=True)
class Contract:
    objectives: tuple[Objective, ...]
    forbidden: frozenset[str] = frozenset()
    ambiguity: tuple[str, ...] = ()
    trusted: bool = True


@dataclass(frozen=True)
class Receipt:
    oid: str
    task_id: str
    run_id: str
    call_id: str
    outcome_id: str
    status: str
    kind: str
    target: str
    identity: str | None = None
    content_hash: str | None = None
    hash_scope: str = "page"
    rule_version: str = "v1"
    execution_authorized: bool = True
    executed: bool = True
    content_signal: str | None = None


@dataclass(frozen=True)
class Assessment:
    verdict: str
    missing: tuple[str, ...]
    reasons: tuple[str, ...]


def protect_trusted(contract: Contract, proposals: Iterable[Objective]) -> Contract:
    """Untrusted T3 proposals may only ADD new optional candidates; they cannot alter T1."""
    known = {o.oid for o in contract.objectives}
    extra = []
    for proposed in proposals:
        if proposed.oid in known:
            continue
        known.add(proposed.oid)
        extra.append(replace(proposed, mandatory=False))
    return replace(contract, objectives=contract.objectives + tuple(extra))


def assess(
    contract: Contract,
    receipts: Iterable[Receipt],
    *,
    task_id: str = "task-1",
    run_id: str = "run-1",
    rule_version: str = "v1",
    known_hashes: dict[str, tuple[str, str]] | None = None,
) -> Assessment:
    """Fail-closed fixture-level checker. G2 metadata are fixture inputs, not product receipts."""
    if not contract.trusted or not contract.objectives or contract.ambiguity:
        return Assessment("UNKNOWN", tuple(o.oid for o in contract.objectives if o.mandatory),
                          ("missing_trusted_contract_or_unresolved_ambiguity",))
    all_receipts = list(receipts)
    missing = []
    reasons = []
    for objective in contract.objectives:
        if not objective.mandatory:
            continue
        candidates = [r for r in all_receipts if r.oid == objective.oid]
        accepted = False
        for r in candidates:
            if r.task_id != task_id or r.run_id != run_id:
                reasons.append(f"{objective.oid}:cross_run")
                continue
            if not r.call_id or not r.outcome_id or not r.execution_authorized or not r.executed:
                reasons.append(f"{objective.oid}:no_executed_receipt")
                continue
            if r.status != "OK":
                reasons.append(f"{objective.oid}:outcome_{r.status}")
                continue
            if r.rule_version != rule_version:
                reasons.append(f"{objective.oid}:stale_verifier")
                continue
            if r.target != objective.target or r.kind != objective.verb:
                reasons.append(f"{objective.oid}:wrong_target_or_kind")
                continue
            if r.content_signal in ("challenge", "catalogue", "error"):
                reasons.append(f"{objective.oid}:non_document_content")
                continue
            if objective.verb in ("open_original", "read"):
                if r.identity != objective.target or not r.content_hash:
                    reasons.append(f"{objective.oid}:identity_unverified")
                    continue
            if known_hashes is not None and r.target in known_hashes:
                expected_hash, scope = known_hashes[r.target]
                if (r.content_hash, r.hash_scope) != (expected_hash, scope):
                    reasons.append(f"{objective.oid}:stale_or_incompatible_digest")
                    continue
            accepted = True
            break
        if not accepted:
            missing.append(objective.oid)
            if not candidates:
                reasons.append(f"{objective.oid}:no_receipt")
    if missing:
        return Assessment("INCOMPLETE", tuple(missing), tuple(reasons))
    return Assessment("PASS_OPERATIONAL_ONLY", (), ())


def receipt(oid: str, verb: str, target: str, **overrides) -> Receipt:
    """Synthetic fixture receipt, not a claim of a real tool execution."""
    base = dict(oid=oid, task_id="task-1", run_id="run-1", call_id="call-1",
                outcome_id="outcome-1", status="OK", kind=verb, target=target,
                identity=target, content_hash="hash-1")
    base.update(overrides)
    return Receipt(**base)
