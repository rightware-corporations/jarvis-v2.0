"""Execution receipts for the JARVIS agent: WORK-07 Milestone A2 (opt-in, default OFF).

A receipt states, for ONE tool proposal in ONE ``AgentSession.run``, what the RIGHTWARE runtime
actually did:
* the decision (authorised or denied, with the policy reason);
* whether execution started;
* the code-checked tool status;
* whether the audit was persisted;
* safe source metadata.

It proves OPERATIONAL facts only. It never proves document authenticity or factual correctness.

Binding (why it is unambiguous)
-------------------------------
The pinned ``OrchestratorAgent`` runs, per call ``tc``:
1. ``_check_tool_allowed(tc)`` (the policy hook);
2. ``ToolExecutor.execute(tc)``, which may return early WITHOUT calling the tool, or submit
   ``tool.execute`` to a worker thread with a timeout. On timeout the orchestrator moves on
   while the worker may still run.

So neither «the current call» nor call order is a safe link. The ledger uses:
* ``decide``: one record per proposal, with a runtime ``sequence``, created in
  ``_check_tool_allowed``;
* ``dispatch``: the orchestrator wraps ``executor.execute(tc)`` and publishes a dispatch token
  for exactly that record before calling it;
* ``claim``: the tool (worker thread) claims a record only if the dispatch token is current AND
  the canonical identity of its arguments equals the record's. Otherwise the execution is
  recorded as ``ORPHAN``, with no call id;
* ``end_dispatch``: when ``executor.execute`` returns, an unclaimed record becomes
  ``NOT_EXECUTED`` and a claimed but unfinished one becomes ``TIMED_OUT``. A later finish is
  kept but marked ``late``;
* ``close``: at the end of the run every open record is closed ``NOT_EXECUTED``.

The model's ``call_id`` is kept only as an identifier it supplied, never as authentication.
Duplicated call ids are flagged. Receipts contain no page text, typed text, prompts or secrets:
arguments are reduced to a SHA-256 of their canonical form, and URLs are redacted.
"""
from __future__ import annotations

import dataclasses
import json
import secrets
import threading

from rightware.agent.policy import canonical
from rightware.agent.web import redact_url

HASH_SCOPE_RAW = "raw_response_bytes"      # SHA-256 of the downloaded body bytes (not the model view)


@dataclasses.dataclass(frozen=True)
class ExecutionReceipt:
    run_id: str                  # runtime-generated, one per AgentSession.run
    sequence: int                # monotonic per run, in decision order (0 = orphan execution)
    call_id: str | None          # supplied by the model; NOT authentication
    call_id_status: str          # SUPPLIED | MISSING | DUPLICATE | NONE (orphan)
    tool: str
    args_sha256: str | None      # canonical(tool, args); None if arguments were unparseable
    authorized: bool             # the policy hook approved the call
    executed: bool               # the tool body actually started (after the boundary check)
    status: str                  # DENIED | NOT_EXECUTED | REFUSED_AT_BOUNDARY | TIMED_OUT | <ToolOutcome.status>
    binding: str                 # BOUND | ORPHAN
    policy_reason: str | None
    audit: str                   # OK | FAILED | NOT_APPLICABLE
    late: bool                   # finished after the orchestrator had already returned for it
    final_url: str | None
    http_status: int | None
    content_type: str | None
    raw_sha256: str | None
    hash_scope: str | None
    truncated: bool | None


class _Record:
    __slots__ = ("sequence", "call_id", "call_id_status", "tool", "key", "authorized", "executed",
                 "status", "binding", "policy_reason", "audit", "late", "evidence", "state")

    def __init__(self, **kw):
        self.executed, self.late, self.evidence, self.audit = False, False, {}, "NOT_APPLICABLE"
        for k, v in kw.items():
            setattr(self, k, v)


class ReceiptLedger:
    """Per-run ledger. Thread-safe: tools run in the upstream worker threads."""

    def __init__(self, run_id: str | None = None):
        self.run_id = run_id or secrets.token_hex(8)
        self._lock = threading.Lock()
        self._records: list[_Record] = []
        self._seen_call_ids: set[str] = set()
        self._dispatch: _Record | None = None

    # -- decision (orchestrator thread, inside _check_tool_allowed) ------------------
    def decide(self, call_id, tool: str, arguments, allowed: bool, reason: str | None) -> _Record:
        try:
            args = json.loads(arguments) if isinstance(arguments, str) and arguments else (arguments or {})
            key = canonical(tool, args) if isinstance(args, dict) else None
        except (TypeError, ValueError):
            key = None
        with self._lock:
            cid = call_id if isinstance(call_id, str) and call_id else None
            if cid is None:
                cid_status = "MISSING"
            elif cid in self._seen_call_ids:
                cid_status = "DUPLICATE"
            else:
                cid_status = "SUPPLIED"
            if cid is not None:
                self._seen_call_ids.add(cid)
            rec = _Record(sequence=len(self._records) + 1, call_id=cid, call_id_status=cid_status,
                          tool=str(tool)[:60], key=key, authorized=bool(allowed),
                          status=None if allowed else "DENIED", binding="BOUND",
                          policy_reason=None if allowed else (reason or "recusada"),
                          state="OPEN" if allowed else "CLOSED")
            self._records.append(rec)
            return rec

    # -- dispatch (orchestrator thread, around ToolExecutor.execute) ------------------
    def dispatch(self, rec: _Record | None) -> None:
        with self._lock:
            self._dispatch = rec if rec is not None and rec.state == "OPEN" else None

    def end_dispatch(self, rec: _Record | None) -> None:
        with self._lock:
            self._dispatch = None
            if rec is None:
                return
            if rec.state == "OPEN":                     # executor returned early: tool never called
                rec.status, rec.state = "NOT_EXECUTED", "CLOSED"
            elif rec.state == "RUNNING":                # executor gave up (timeout): still running
                rec.status, rec.state = "TIMED_OUT", "ABANDONED"

    # -- execution (worker thread, inside _PolicyTool.execute) -------------------------
    def claim(self, tool: str, params: dict) -> _Record:
        key = canonical(tool, params)
        with self._lock:
            rec = self._dispatch
            if rec is not None and rec.state == "OPEN" and rec.tool == tool and rec.key == key:
                rec.state = "CLAIMED"
                self._dispatch = None                   # one claim per dispatch
                return rec
            orphan = _Record(sequence=0, call_id=None, call_id_status="NONE", tool=str(tool)[:60], key=key,
                             authorized=False, status=None, binding="ORPHAN", policy_reason=None, state="CLAIMED")
            self._records.append(orphan)
            return orphan

    def started(self, rec: _Record) -> None:
        with self._lock:
            rec.executed = True
            if rec.state == "CLAIMED":
                rec.state = "RUNNING"

    def finish(self, rec: _Record, status: str, evidence: dict, audit_ok: bool | None) -> None:
        with self._lock:
            rec.late = rec.state == "ABANDONED"
            rec.status = status
            rec.evidence = dict(evidence or {})
            rec.audit = "NOT_APPLICABLE" if audit_ok is None else ("OK" if audit_ok else "FAILED")
            rec.state = "CLOSED"

    # -- end of run ------------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._dispatch = None
            for rec in self._records:
                if rec.state in ("OPEN", "CLAIMED"):
                    rec.status, rec.state = "NOT_EXECUTED", "CLOSED"

    def receipts(self) -> tuple[ExecutionReceipt, ...]:
        with self._lock:
            out = []
            for r in self._records:
                ev = r.evidence
                raw = ev.get("sha256") if isinstance(ev.get("sha256"), str) and len(ev.get("sha256")) == 64 else None
                out.append(ExecutionReceipt(
                    run_id=self.run_id, sequence=r.sequence, call_id=r.call_id, call_id_status=r.call_id_status,
                    tool=r.tool, args_sha256=r.key, authorized=r.authorized, executed=r.executed,
                    status=r.status or "UNKNOWN", binding=r.binding, policy_reason=r.policy_reason,
                    audit=r.audit, late=r.late,
                    final_url=redact_url(ev["final_url"]) if isinstance(ev.get("final_url"), str) else None,
                    http_status=ev.get("status") if isinstance(ev.get("status"), int) else None,
                    content_type=ev.get("content_type") if isinstance(ev.get("content_type"), str) else None,
                    raw_sha256=raw, hash_scope=HASH_SCOPE_RAW if raw else None,
                    truncated=ev.get("truncated") if isinstance(ev.get("truncated"), bool) else None))
            return tuple(out)
