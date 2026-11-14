"""Deterministic completion gate for contracted tasks: WORK-07 Milestone A3 (opt-in, default OFF).

Judges, for ONE run, whether every mandatory objective of a trusted A1 contract has OPERATIONAL
evidence in the A2 execution receipts. A pure function: no model, no page text, no network.
The model's own claims are never input.

Evidence rules (per objective)
------------------------------
A receipt counts as observation of an objective only if ALL of these hold:
* ``binding == "BOUND"`` and ``call_id_status == "SUPPLIED"`` (no ORPHAN, DUPLICATE, MISSING);
* ``authorized`` and ``executed``, ``status == "OK"``, ``audit == "OK"`` and not ``late``;
* the tool is a page-load tool;
* ``final_url`` is exactly the objective URL;
* ``http_status == 200``, an html/plain content type, a raw-body SHA-256 with scope
  ``raw_response_bytes``, and ``truncated is False`` (a truncated body proves only a prefix);
* the receipt has not already been used for another objective.

A matching receipt that PROVES the page was not obtained (HTTP error, empty content, refused,
failed, not executed) leaves the objective MISSING. A matching receipt whose evidence is AMBIGUOUS
(orphan, duplicate or missing call id, late after timeout, truncated, no raw hash, wrong content
type, audit not confirmed) makes the objective UNKNOWN. No matching receipt at all means MISSING.

Identity
--------
A1 contracts have ``identity_rule = "NONE"``: a URL with HTTP 200 does not prove the page is the
authentic original. An observed objective is therefore ``PAGE_OBSERVED``, never verified, and a
task whose objectives are all observed is ``UNKNOWN_IDENTITY``. ``COMPLETE_VERIFIED`` requires a
trusted identity rule, which A1 cannot express, so it is unreachable today by construction.

Task states, in priority order: ERROR (audit failure) > HALTED (interrupted) > INCOMPLETE (a
mandatory objective missing) > UNKNOWN (ambiguous evidence) > UNKNOWN_IDENTITY > COMPLETE_VERIFIED.
Factual correctness of the answer is never assessed (``answer_factually_verified`` is always False).
"""
from __future__ import annotations

import dataclasses

from rightware.agent.receipts import HASH_SCOPE_RAW, ExecutionReceipt
from rightware.agent.task_contract import TaskContract

PAGE_TOOLS = frozenset({"web_open", "web_follow", "web_submit", "web_read"})
PAGE_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
NOT_OBTAINED = frozenset({"HTTP_ERROR", "EMPTY_CONTENT", "REFUSED", "FAILED", "NOT_EXECUTED", "DENIED",
                          "REFUSED_AT_BOUNDARY", "BLOCKED"})
STATES = ("COMPLETE_VERIFIED", "INCOMPLETE", "UNKNOWN", "UNKNOWN_IDENTITY", "HALTED", "ERROR")


@dataclasses.dataclass(frozen=True)
class ObjectiveResult:
    oid: str
    state: str                    # VERIFIED | PAGE_OBSERVED | UNKNOWN | MISSING
    reason: str
    evidence_sequence: int | None  # the receipt sequence used (runtime id), if any


@dataclasses.dataclass(frozen=True)
class CompletionResult:
    state: str                    # one of STATES
    contract_id: str
    objectives: tuple[ObjectiveResult, ...]
    reason: str
    answer_factually_verified: bool = False

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(o.oid for o in self.objectives if o.state == "MISSING")

    def as_dict(self) -> dict:
        return {"state": self.state, "contract_id": self.contract_id, "reason": self.reason,
                "answer_factually_verified": False,
                "objectives": [dataclasses.asdict(o) for o in self.objectives]}


def _defect(r: ExecutionReceipt) -> str | None:
    """Why a receipt whose URL matches still cannot count (None = it counts)."""
    if r.binding != "BOUND":
        return "recibo órfão (sem vínculo à chamada)"
    if r.call_id_status != "SUPPLIED":
        return f"identificador de chamada {r.call_id_status.lower()}"
    if not (r.authorized and r.executed):
        return "não autorizado ou não executado"
    if r.late or r.status == "TIMED_OUT":
        return "execução após timeout"
    if r.status != "OK":
        return f"estado {r.status}"
    if r.audit != "OK":
        return "auditoria não confirmada"
    if r.tool not in PAGE_TOOLS:
        return "ferramenta não carrega páginas"
    if r.http_status != 200 or r.content_type not in PAGE_TYPES:
        return "resposta HTTP sem conteúdo de página válido"
    if not r.raw_sha256 or r.hash_scope != HASH_SCOPE_RAW:
        return "sem hash do corpo bruto"
    if r.truncated is not False:
        return "conteúdo truncado (só prova um prefixo)"
    return None


def evaluate(contract: TaskContract, receipts: tuple[ExecutionReceipt, ...], *, halted: str | None = None,
             audit_failed: bool = False) -> CompletionResult:
    if type(contract) is not TaskContract or not contract.objectives:
        return CompletionResult("ERROR", getattr(contract, "preset_id", "?"), (), "contrato ausente ou inválido")
    run_ids = {r.run_id for r in receipts}
    if len(run_ids) > 1:
        return CompletionResult("ERROR", contract.preset_id, (), "recibos de execuções diferentes misturados")
    used: set[int] = set()
    pending = any(r.status == "TIMED_OUT" for r in receipts)    # a tool still running after its timeout
    results = []
    for o in contract.objectives:
        matching = [r for r in receipts if r.final_url == o.url]
        good = [r for r in matching if _defect(r) is None and r.sequence not in used]
        if good:
            r = good[0]
            used.add(r.sequence)
            if o.identity_rule == "NONE":
                results.append(ObjectiveResult(o.oid, "PAGE_OBSERVED",
                                               "página carregada; identidade do original não verificada", r.sequence))
            else:                                          # unreachable with A1 contracts (validator rejects)
                results.append(ObjectiveResult(o.oid, "UNKNOWN", "regra de identidade não suportada", r.sequence))
        elif matching and all(r.binding == "BOUND" and r.status in NOT_OBTAINED for r in matching):
            results.append(ObjectiveResult(o.oid, "MISSING", f"tentativa falhada ({matching[-1].status})", None))
        elif matching:
            bad = next((r for r in matching if r.status not in NOT_OBTAINED), matching[0])
            results.append(ObjectiveResult(o.oid, "UNKNOWN", _defect(bad) or "evidência já usada", None))
        elif pending:
            results.append(ObjectiveResult(o.oid, "UNKNOWN", "execução pendente após timeout", None))
        else:
            results.append(ObjectiveResult(o.oid, "MISSING", "sem execução verificada do objectivo", None))
    objectives = tuple(results)
    states = {r.state for r in objectives}
    any_audit_failed = audit_failed or any(r.audit == "FAILED" for r in receipts)
    if any_audit_failed:
        return CompletionResult("ERROR", contract.preset_id, objectives, "falha de auditoria: estado não confirmável")
    if halted:
        return CompletionResult("HALTED", contract.preset_id, objectives, f"tarefa interrompida ({halted})")
    if "MISSING" in states:
        return CompletionResult("INCOMPLETE", contract.preset_id, objectives, "objectivos obrigatórios sem evidência")
    if "UNKNOWN" in states:
        return CompletionResult("UNKNOWN", contract.preset_id, objectives, "evidência ambígua ou inválida")
    if "PAGE_OBSERVED" in states:
        return CompletionResult("UNKNOWN_IDENTITY", contract.preset_id, objectives,
                                "páginas observadas, mas a identidade dos originais não é verificável")
    return CompletionResult("COMPLETE_VERIFIED", contract.preset_id, objectives, "todos os objectivos verificados")


def recovery_feedback(contract: TaskContract, result: CompletionResult) -> str:
    """Code-generated continuation feedback: objective ids and code-owned labels only (no page
    text, no URLs, no model text)."""
    labels = {o.oid: o.label for o in contract.objectives}
    items = "; ".join(f"{oid}: {labels[oid]}" for oid in result.missing)
    return ("[RIGHTWARE-VERIFICAÇÃO] A tarefa ainda não pode ser dada como concluída. Objectivos obrigatórios sem "
            f"evidência de execução: {items}. Usa apenas as ferramentas autorizadas para os cumprir, ou explica "
            "porque não é possível.")
