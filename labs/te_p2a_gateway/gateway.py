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

import hashlib
import json
import threading
from pathlib import Path

from rightware.agent.browser import PublicBrowser, Step
from rightware.agent.policy import AgentPolicy, Budgets, ToolDef, canonical
from rightware.agent.receipts import ReceiptLedger
from rightware.agent.session import TOOLS

GATEWAY_TOOLS = ("web_open", "web_follow", "web_find")
TOOL_TIMEOUT_SECONDS = 30.0
MAX_REPORT_CHARS = 8000
# JRV-BP-043: the report becomes a receipted operation instead of free model text. It grants nothing:
# it only stores the submitted JSON object (hash bound to the receipt) for the RIGHTWARE verifier.
SUBMIT_REPORT = ToolDef(
    "submit_report", "Entrega à RIGHTWARE o relatório final: o texto de UM objecto JSON com as propriedades e as "
    "fontes consultadas. A conclusão é verificada pela RIGHTWARE a partir das execuções, não deste texto.",
    {"report": {"type": "string", "maxLength": MAX_REPORT_CHARS, "description": "objecto JSON do relatório"}},
    ("report",), session_flag="report", consequential=False, max_calls=2)


class Gateway:
    def __init__(self, *, task_id: str, attempt_id: str, sites: tuple[str, ...], fetcher, budgets: Budgets,
                 audit_path: Path | None = None, clock=None, tool_timeout: float = TOOL_TIMEOUT_SECONDS,
                 submit_report: bool = False):
        if not task_id or not attempt_id:
            raise ValueError("task and attempt identity are required")
        self.task_id, self.attempt_id = task_id, attempt_id
        self.registry = {n: TOOLS[n] for n in GATEWAY_TOOLS}
        allow = {"browse"}
        if submit_report:                     # host decision (code), never the model's
            self.registry["submit_report"] = SUBMIT_REPORT
            allow.add("report")
        self.browser = PublicBrowser(sites, fetcher)
        kwargs = {"clock": clock} if clock else {}
        self.policy = AgentPolicy(self.registry, allow=allow, budgets=budgets, audit_path=audit_path,
                                  signature=self._signature, **kwargs)
        self.submissions: list[dict] = []     # {"sequence", "sha256", "report"} — bound to receipts
        self.cancelled_requests: set = set()  # MCP notifications/cancelled (request ids)
        self._stuck: threading.Thread | None = None   # a tool still running after its timeout
        self.ledger = ReceiptLedger(run_id=f"{task_id}:{attempt_id}")
        self.tool_timeout = tool_timeout
        self._lock = threading.Lock()
        self._runners = {"web_open": self.browser.open, "web_follow": self.browser.follow,
                         "web_find": self.browser.find, "submit_report": self._submit_report}
        self._current_sequence = None

    def _submit_report(self, report: str) -> Step:
        """Deterministic validation only: one JSON object, bounded size. Stored with its SHA-256 under the
        receipt's sequence; no judgement of its content here (that is the verifier's job)."""
        try:
            obj = json.loads(report)
        except (TypeError, ValueError):
            return Step("REFUSED", "Relatório recusado: não é JSON válido.", {}, "INVALID_REPORT")
        if not isinstance(obj, dict) or not obj:
            return Step("REFUSED", "Relatório recusado: tem de ser um objecto JSON não vazio.", {}, "INVALID_REPORT")
        digest = hashlib.sha256(report.encode("utf-8")).hexdigest()
        self.submissions.append({"sequence": self._current_sequence, "sha256": digest, "report": report})
        return Step("OK", f"Relatório recebido pela RIGHTWARE (SHA-256 {digest[:16]}…); será verificado a partir "
                          "das execuções registadas.", {}, None)

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
            # JRV-BP-043: a request cancelled by the client before it ran, or any call while an earlier tool
            # is still running after its timeout, is refused WITHOUT executing (receipted, budget untouched).
            if request_id in self.cancelled_requests or (self._stuck is not None and self._stuck.is_alive()):
                reason = ("pedido cancelado pelo cliente antes da execução" if request_id in self.cancelled_requests
                          else "uma ferramenta anterior ainda está em execução após timeout")
                self.ledger.decide(call_id, tool, json.dumps(arguments) if isinstance(arguments, dict) else None,
                                   False, reason)
                return f"[RIGHTWARE] A ferramenta '{tool}' NÃO foi executada: {reason}.", True
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
            self._current_sequence = rec.sequence
            box: dict = {}
            worker = threading.Thread(target=self._execute, args=(tool, dict(arguments), box), daemon=True)
            worker.start()
            worker.join(self.tool_timeout)
            self.ledger.end_dispatch(rec)
            if worker.is_alive():
                self._stuck = worker
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
