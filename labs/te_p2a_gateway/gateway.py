"""JRV-TE-P2A: RIGHTWARE Tool Gateway core (transport-agnostic, experimental, labs only).

An external executor (goose) gets NO tool of its own. Every operation it wants goes through
``Gateway.call``, which REUSES the RIGHTWARE authority stack unchanged:

* ``AgentPolicy`` (schema/enum/length validation, capability, global proposal budget, per-tool quota,
  deadline, cancel, argument-aware loop guard, mandatory audit) — the only authority;
* the existing ``ToolDef`` registry (``web_open``, ``web_follow``, ``web_find`` from the session);
* ``ReceiptLedger`` / ``ExecutionReceipt`` (A2) and the A3 completion verifier;
* ``PublicBrowser`` with its host allowlist and the experimental fixture transport.

Binding (why each receipt belongs to exactly one authorised execution)
--------------------------------------------------------------------
The OpenJarvis executor binds receipts through its orchestrator hook. Here the gateway owns the whole
sequence for every call, SERIALISED by one lock (one call at a time per task attempt):

1. ``policy.before_tool_call`` decides (authority comes only from code: registry + budgets);
2. ``ledger.decide`` records the decision with call id ``<task>:<attempt>:<jsonrpc id>``;
3. if allowed: ``ledger.dispatch`` publishes the token for that record only;
4. a worker thread runs the tool: ``ledger.claim`` (token + canonical args must match) →
   ``policy.authorize_execution`` (boundary re-check) → ``ledger.started`` → tool → ``note_outcome``
   (audit) → ``ledger.finish``;
5. ``ledger.end_dispatch`` after a bounded wait: unclaimed → NOT_EXECUTED, still running → TIMED_OUT
   (a later finish is kept but marked ``late``).

Nothing in the model's text can create a permission: the model only chooses which registered tool to
propose and with which arguments; the policy decides.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from rightware.agent.browser import PublicBrowser
from rightware.agent.policy import AgentPolicy, Budgets, canonical
from rightware.agent.receipts import ReceiptLedger
from rightware.agent.session import TOOLS

GATEWAY_TOOLS = ("web_open", "web_follow", "web_find")
TOOL_TIMEOUT_SECONDS = 30.0


class Gateway:
    def __init__(self, *, task_id: str, attempt_id: str, sites: tuple[str, ...], fetcher, budgets: Budgets,
                 audit_path: Path | None = None, clock=None, tool_timeout: float = TOOL_TIMEOUT_SECONDS):
        if not task_id or not attempt_id:
            raise ValueError("task and attempt identity are required")
        self.task_id, self.attempt_id = task_id, attempt_id
        self.registry = {n: TOOLS[n] for n in GATEWAY_TOOLS}
        self.browser = PublicBrowser(sites, fetcher)
        kwargs = {"clock": clock} if clock else {}
        self.policy = AgentPolicy(self.registry, allow={"browse"}, budgets=budgets, audit_path=audit_path,
                                  signature=self._signature, **kwargs)
        self.ledger = ReceiptLedger(run_id=f"{task_id}:{attempt_id}")
        self.tool_timeout = tool_timeout
        self._lock = threading.Lock()
        self._runners = {"web_open": self.browser.open, "web_follow": self.browser.follow,
                         "web_find": self.browser.find}

    # -- what the executor may see ------------------------------------------------------------
    def tool_specs(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "inputSchema": t.schema()}
                for t in self.registry.values()]

    # -- loop-guard identity (same rule as AgentSession._action_signature) --------------------
    def _signature(self, name: str, args: dict) -> str:
        b = self.browser
        if name in ("web_open", "web_follow"):
            url = args.get("url") if name == "web_open" else \
                (b.links.get(str(args.get("link", "")).strip().upper()) or (f"<unknown {args.get('link')}>",))[0]
            return canonical("load", {"url": url})
        return canonical(name, args)

    def _denial_reason(self, name, before: int) -> str:
        for entry in reversed(self.policy.log[before:]):
            if not entry.get("allowed") and "outcome" not in entry:
                return entry.get("reason") or "recusada pela política"
        return "recusada pela política"

    # -- the only way to act --------------------------------------------------------------------
    def call(self, name: object, arguments: object, request_id: object) -> tuple[str, bool]:
        """Returns (text for the model, is_error). Every proposal yields exactly one decision receipt."""
        call_id = f"{self.task_id}:{self.attempt_id}:{request_id}" if request_id is not None else None
        tool = str(name) if isinstance(name, str) else "<invalid>"
        with self._lock:
            before = len(self.policy.log)
            if not isinstance(arguments, dict):
                self.policy.before_tool_call(tool, {"__invalid__": True})   # recorded + counted, always denied
                reason = "os argumentos não são um objecto JSON"
                allowed = False
            else:
                allowed = self.policy.before_tool_call(tool, arguments)
                reason = None if allowed else self._denial_reason(tool, before)
            rec = self.ledger.decide(call_id, tool, json.dumps(arguments) if isinstance(arguments, dict) else None,
                                     allowed, reason)
            if not allowed:
                return (f"[RIGHTWARE] A ferramenta '{tool}' NÃO foi executada: {reason}. Não repitas a mesma "
                        "chamada; ajusta o plano ou conclui com o que já foi verificado.", True)
            self.ledger.dispatch(rec)
            box: dict = {}
            worker = threading.Thread(target=self._execute, args=(tool, dict(arguments), box), daemon=True)
            worker.start()
            worker.join(self.tool_timeout)
            self.ledger.end_dispatch(rec)
            if worker.is_alive():
                return (f"[RIGHTWARE] '{tool}' excedeu {self.tool_timeout:.0f} s; o resultado não é utilizável.", True)
            status, content = box.get("status", "FAILED"), box.get("content", "Erro da ferramenta.")
            return content, status not in ("OK",)

    def _execute(self, tool: str, args: dict, box: dict) -> None:
        rec = self.ledger.claim(tool, args)
        try:
            self.policy.authorize_execution(tool, args)
        except PermissionError as exc:
            self.policy.note_outcome(tool, args, "REFUSED")
            self.ledger.finish(rec, "REFUSED_AT_BOUNDARY", {}, None)
            box.update(status="REFUSED", content=f"Recusado pela política: {exc}.")
            return
        self.ledger.started(rec)
        try:
            step = self._runners[tool](**args)
            status, content, evidence, code = step.status, step.content, step.evidence, step.code
        except Exception as exc:                     # fail closed, no internals
            status, content, evidence, code = "FAILED", f"Erro da ferramenta ({type(exc).__name__}).", {}, \
                "TOOL_EXCEPTION"
        audit_ok = self.policy.note_outcome(tool, args, status)
        self.ledger.finish(rec, status, evidence, audit_ok, reason_code=code)
        box.update(status=status, content=content)

    def cancel(self) -> None:
        self.policy.cancel()

    def close(self) -> None:
        with self._lock:
            self.policy.close_pending()
            self.ledger.close()

    def receipts(self):
        return self.ledger.receipts()
