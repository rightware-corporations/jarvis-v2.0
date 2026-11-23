# RIGHTWARE runtime component (JRV-P3A): moved from labs/te_p2a_gateway/gateway.py @ a1b88ef; changes declared in rightware/gateway/PARITY.json.
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

import dataclasses
import hashlib
import json
import threading
from pathlib import Path

from rightware.agent.browser import PublicBrowser, Step
from rightware.agent.policy import AgentPolicy, Budgets, ToolDef, canonical
from rightware.agent.receipts import ReceiptLedger
from rightware.agent.session import TOOLS

from rightware.gateway import report_contract as RC


def _contract_module(contract_id):
    """Only pre-registered contracts exist (fail closed on anything else)."""
    if contract_id == RC.CONTRACT_ID:
        return RC
    raise ValueError("unknown report contract")


def _submit_tool(module) -> ToolDef:
    return ToolDef("submit_report", module.TOOL_DESCRIPTION,
                   {"report": {"type": "string", "maxLength": 2 * module.MAX_REPORT_BYTES,
                               "description": f"texto de um objecto JSON conforme ao contrato {module.CONTRACT_ID}"}},
                   ("report",), session_flag="report", consequential=False, max_calls=module.MAX_SUBMISSIONS)

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
# JRV-TE-P2B: the same receipted operation under the pre-registered contract te-p2b.report.v1. The policy
# length bound is only the OUTER bound (2x); the contract's UTF-8 size rule gives structured feedback.
SUBMIT_REPORT_V1 = ToolDef(
    "submit_report", RC.TOOL_DESCRIPTION,
    {"report": {"type": "string", "maxLength": 2 * RC.MAX_REPORT_BYTES,
                "description": "texto de um objecto JSON conforme ao contrato te-p2b.report.v1"}},
    ("report",), session_flag="report", consequential=False, max_calls=RC.MAX_SUBMISSIONS)


# JRV-TE-P2C: replay classes (host-defined, never model-defined). An operation EXECUTED in an earlier transport
# generation that is requested again with the same effective signature is NOT executed again.
READ_REPLAY = ("web_open", "web_follow")        # network reads: replay a completed OK read once, then policy decides
EFFECT_REPLAY = ("submit_report",)              # effects: any executed operation is never re-executed
EFFECT_REPLAY_LIMIT = 3


class Gateway:
    def __init__(self, *, task_id: str, attempt_id: str, sites: tuple[str, ...], fetcher, budgets: Budgets,
                 audit_path: Path | None = None, clock=None, tool_timeout: float = TOOL_TIMEOUT_SECONDS,
                 submit_report: bool = False, report_contract: str | None = None):
        if not task_id or not attempt_id:
            raise ValueError("task and attempt identity are required")
        self.task_id, self.attempt_id = task_id, attempt_id
        self.registry = {n: TOOLS[n] for n in GATEWAY_TOOLS}
        allow = {"browse"}
        self._rc = _contract_module(report_contract) if report_contract is not None else None
        self.report_contract = report_contract
        # TE-P2D: in research mode every successful page read is announced to the model as a numbered RIGHTWARE
        # observation (receipt sequence + raw SHA-256) that a report can cite; the text the model saw is kept.
        self.observe = report_contract is not None and self._rc is not RC
        self.observations: dict[int, dict] = {}
        if submit_report or report_contract:  # host decision (code), never the model's
            self.registry["submit_report"] = (SUBMIT_REPORT_V1 if self._rc is RC else _submit_tool(self._rc)) \
                if report_contract else SUBMIT_REPORT
            allow.add("report")
        self.browser = PublicBrowser(sites, fetcher)
        kwargs = {"clock": clock} if clock else {}
        self.policy = AgentPolicy(self.registry, allow=allow, budgets=budgets, audit_path=audit_path,
                                  signature=self._signature, **kwargs)
        self.submissions: list[dict] = []     # {"sequence", "sha256", "report"} — bound to receipts
        self.submission_chain: list[dict] = []   # TE-P2B: hash-chained record of EVERY submission
        self.submitted_texts: list[dict] = []    # TE-P2B: {"sequence", "sha256", "report"} incl. rejected ones
        self._accepted_sequence = None
        self.cancelled_requests: set = set()  # MCP notifications/cancelled (request ids)
        self._stuck: threading.Thread | None = None   # a tool still running after its timeout
        self.ledger = ReceiptLedger(run_id=f"{task_id}:{attempt_id}")
        self.tool_timeout = tool_timeout
        self._lock = threading.Lock()
        self._runners = {"web_open": self.browser.open, "web_follow": self.browser.follow,
                         "web_find": self.browser.find,
                         "submit_report": self._submit_report_v1 if report_contract else self._submit_report}
        self._current_sequence = None
        self._current_call_id = None
        self.generation = 0                    # TE-P2C: transport generation (+1 per host-authorised resume)
        self._ops: list[dict] = []             # executed/decided operations with signature and result box
        self.replays: list[dict] = []          # TE-P2C: replay-served requests (evidence)

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

    def _submit_report_v1(self, report: str) -> Step:
        """TE-P2B: pure contract validation (pre-filter) + decision + hash-chained record. Only the FIRST
        conformant report is stored for the verifier; nothing here judges content."""
        digest = hashlib.sha256(report.encode("utf-8", "surrogatepass")).hexdigest()
        result = self._rc.validate_report(report)
        seen = {t["sha256"] for t in self.submitted_texts}
        if self._accepted_sequence is not None:
            decision = "ALREADY_ACCEPTED"
        elif digest in seen:
            decision = "DUPLICATE_SUBMISSION"
        elif not result.schema_valid:
            decision = "REJECTED_SCHEMA"
        else:
            decision = "ACCEPTED_FOR_VERIFICATION"
        seq = self._current_sequence
        self.submitted_texts.append({"sequence": seq, "sha256": digest, "report": report})
        if decision == "ACCEPTED_FOR_VERIFICATION":
            self._accepted_sequence = seq
            self.submissions.append({"sequence": seq, "sha256": digest, "report": report})
        self._rc.chain_record(self.submission_chain, kind="submission", run_id=self.ledger.run_id,
                        receipt_sequence=seq, call_id=self._current_call_id, report_sha256=digest,
                        report_bytes=len(report.encode("utf-8", "surrogatepass")), decision=decision,
                        schema_valid=result.schema_valid,
                        errors=[[e["path"], e["code"]] for e in result.errors])
        remaining = self.registry["submit_report"].max_calls - self.policy.per_tool.get("submit_report", 0)
        text = self._rc.feedback(result, decision, remaining)
        if decision == "ACCEPTED_FOR_VERIFICATION":
            return Step("OK", text, {}, None)
        return Step("REFUSED", text, {}, decision)

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
        tool = str(name) if isinstance(name, str) else "<invalid>"
        with self._lock:
            gen = f"g{self.generation}:" if self.generation else ""      # TE-P2C: ids restart in a new process
            call_id = f"{self.task_id}:{self.attempt_id}:{gen}{request_id}" if request_id is not None else None
            # JRV-BP-043: a request cancelled by the client before it ran, or any call while an earlier tool
            # is still running after its timeout, is refused WITHOUT executing (receipted, budget untouched).
            if request_id in self.cancelled_requests or (self._stuck is not None and self._stuck.is_alive()):
                reason = ("pedido cancelado pelo cliente antes da execução" if request_id in self.cancelled_requests
                          else "uma ferramenta anterior ainda está em execução após timeout")
                self.ledger.decide(call_id, tool, json.dumps(arguments) if isinstance(arguments, dict) else None,
                                   False, reason)
                return f"[RIGHTWARE] A ferramenta '{tool}' NÃO foi executada: {reason}.", True
            replay = self._replay(tool, arguments, call_id)
            if replay is not None:
                return replay
            sig = self._safe_signature(tool, arguments)
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
            self._current_sequence, self._current_call_id = rec.sequence, call_id
            box: dict = {}
            worker = threading.Thread(target=self._execute, args=(tool, dict(arguments), box), daemon=True)
            worker.start()
            worker.join(self.tool_timeout)
            self.ledger.end_dispatch(rec)
            self._ops.append({"sequence": rec.sequence, "tool": tool, "sig": sig, "generation": self.generation,
                              "rec": rec, "box": box, "worker": worker, "replays": 0})
            if worker.is_alive():
                self._stuck = worker
                return (f"[RIGHTWARE] '{tool}' excedeu {self.tool_timeout:.0f} s; o resultado não é utilizável.", True)
            status, content = box.get("status", "FAILED"), box.get("content", "Erro da ferramenta.")
            if self.observe and status == "OK" and tool in ("web_open", "web_follow"):
                content = self._observation(rec, content)
            return content, status not in ("OK",)

    # -- TE-P2C: resume support (host-owned state only) ----------------------------------------
    def _safe_signature(self, tool, arguments):
        if not isinstance(arguments, dict):
            return None
        try:
            return self._signature(tool, arguments)
        except Exception:
            return None

    def _replay(self, tool, arguments, call_id):
        """Caller holds the lock. Serve a request that repeats an operation executed in an EARLIER generation
        from its receipt, without executing it again. Returns (text, is_error) or None (normal path)."""
        if self.generation == 0 or tool not in READ_REPLAY + EFFECT_REPLAY:
            return None
        sig = self._safe_signature(tool, arguments)
        if sig is None:
            return None
        for op in self._ops:
            if op["generation"] >= self.generation or op["sig"] != sig or op["worker"].is_alive():
                continue
            rec, box = op["rec"], op["box"]
            if not rec.executed:
                continue
            effect = tool in EFFECT_REPLAY
            if not effect and (rec.status != "OK" or op["replays"] >= 1):
                continue                                   # a failed read may be retried; one replay per read
            args_json = json.dumps(arguments)
            if effect and op["replays"] >= EFFECT_REPLAY_LIMIT:
                reason = f"operação com efeito já executada no recibo #{op['sequence']}; não é repetida"
                r = self.ledger.decide(call_id, tool, args_json, False, reason)
                r.reason_code = "EFFECT_ALREADY_EXECUTED"
                self.replays.append({"sequence": r.sequence, "original_sequence": op["sequence"], "tool": tool,
                                     "generation": self.generation, "served": False})
                return f"[RIGHTWARE] {reason}.", True
            op["replays"] += 1
            reason = (f"reenvio: operação já executada no recibo #{op['sequence']} (geração {op['generation']}); "
                      "resultado registado devolvido sem nova execução")
            r = self.ledger.decide(call_id, tool, args_json, False, reason)
            r.reason_code = "REPLAYED_FROM_RECEIPT"
            self.replays.append({"sequence": r.sequence, "original_sequence": op["sequence"], "tool": tool,
                                 "generation": self.generation, "served": True})
            content = box.get("content", "")
            return (f"[RIGHTWARE] Resultado registado do recibo #{op['sequence']} (não re-executado):\n{content}",
                    box.get("status") != "OK")
        return None

    def _observation(self, rec, content: str) -> str:
        """Caller holds the lock. Register the page the model is about to see as a citable observation."""
        receipt = next(r for r in self.ledger.receipts() if r.sequence == rec.sequence)
        self.observations[rec.sequence] = {
            "observation": rec.sequence, "final_url": receipt.final_url, "http_status": receipt.http_status,
            "raw_sha256": receipt.raw_sha256, "text": content,
            "text_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
        return (f"[RIGHTWARE observação {rec.sequence} | sha256 {(receipt.raw_sha256 or '')[:16]} | "
                f"{receipt.final_url}]\n{content}")

    def begin_generation(self, generation: int) -> None:
        """Called by the transport only after a host-authorised resume consumed its grant."""
        with self._lock:
            if generation != self.generation + 1:
                raise ValueError("generation must advance by one")
            self.generation = generation
            self.cancelled_requests.clear()               # ids of the previous process never carry over

    def snapshot(self) -> dict:
        """Host summary of the authorised state (waits for any in-flight call: same lock as ``call``)."""
        with self._lock:
            receipts = self.ledger.receipts()
            digest = hashlib.sha256(json.dumps([dataclasses.asdict(r) for r in receipts], sort_keys=True,
                                               default=str).encode()).hexdigest()
            return {"task_id": self.task_id, "attempt_id": self.attempt_id, "generation": self.generation,
                    "receipts": len(receipts), "last_sequence": receipts[-1].sequence if receipts else 0,
                    "receipts_sha256": digest,
                    "chain_head": self.submission_chain[-1]["record_sha256"] if self.submission_chain else None,
                    "in_flight": bool(self._stuck is not None and self._stuck.is_alive()),
                    "per_tool": dict(self.policy.per_tool), "calls": self.policy.calls}

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
