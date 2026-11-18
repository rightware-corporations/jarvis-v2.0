"""TE-02: opt-in trusted task entry using existing AgentSession, not a new agent.

Only an application host may call run_trusted_browser_fixture() with a factory
that creates a constrained AgentSession. Plain TextFacade.submit() is unchanged.
This deliberately narrow experiment is NOT a general NL task classifier,
Goose adapter, user-facing CLI, durable task ledger or real-model acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import secrets
from threading import Lock
from typing import Callable

from rightware.text_facade import TextFacade, TextResult

_FIXTURE_ID = "synthetic-archive-two-originals"
_IANA_ID = "iana-reserved-example-public-readonly"
_ALLOWED_SCOPE = frozenset({"browse"})
_TERMINAL = frozenset({
    "COMPLETE_VERIFIED", "INCOMPLETE", "UNKNOWN", "UNKNOWN_IDENTITY", "HALTED", "ERROR",
})
# The model's text and the tool arguments are NEVER diagnostic evidence.
_HALT_CODES = {
    None: "NONE",
    "limite de passos atingido": "TOOL_BUDGET",
    "tempo esgotado": "DEADLINE",
    "limite de turnos atingido": "TURN_BUDGET",
    "tarefa cancelada": "CANCELLED",
}
# TE-05E: mirrors rightware.agent.diagnostics.ERROR_CODES (kept here so text-only paths need no vendor).
_ERROR_CODES = frozenset(("NONE", "ENGINE_TIMEOUT", "ENGINE_CONNECTION", "ENGINE_FAILURE", "AGENT_FAILURE",
                          "AUDIT_FAILURE", "EVIDENCE_INCOMPLETE", "OTHER"))
_SAFE_TOOLS = frozenset(("web_open", "web_follow", "web_submit", "web_type", "web_find",
                         "fixture_read", "fixture_compare"))
# TE-05: DENIED (policy refused before execution) is a real receipt status; it was masked as UNKNOWN.
_SAFE_STATUSES = frozenset((
    "OK", "DENIED", "FAILED", "REFUSED", "REFUSED_AT_BOUNDARY", "TIMED_OUT", "NOT_EXECUTED",
    "BLOCKED", "HTTP_ERROR", "EMPTY_CONTENT", "CANCELLED", "UNKNOWN",
))


def _receipt_events(receipts):
    """Only ordinal, fixed-vocabulary tool and outcome; no args, URLs, body or model text."""
    return tuple((r.sequence if type(r.sequence) is int and r.sequence >= 1 else 0,
                  r.tool if r.tool in _SAFE_TOOLS else "OTHER",
                  r.status if r.status in _SAFE_STATUSES else "UNKNOWN") for r in receipts)


def _receipt_reason_codes(receipts):
    """TE-05: (sequence, finite reason code) for receipts that carry one. Codes come from a fixed
    vocabulary (policy denials, browser refusals); anything else becomes OTHER."""
    from rightware.agent.diagnostics import REASON_CODES
    return tuple((r.sequence if type(r.sequence) is int and r.sequence >= 1 else 0,
                  r.reason_code if r.reason_code in REASON_CODES else "OTHER")
                 for r in receipts if getattr(r, "reason_code", None) is not None)


@dataclass(frozen=True)
class TaskEntryResult:
    request_id: str
    session_id: str
    route: str
    operational_state: str
    objective_states: tuple[tuple[str, str, int | None], ...]
    receipts_count: int
    factual_verified: bool
    completion_verified: bool
    model_commentary_unverified: str
    limitations: tuple[str, ...]
    halt_reason_code: str = "NONE"
    receipt_events: tuple[tuple[int, str, str], ...] = ()
    receipt_reason_codes: tuple[tuple[int, str], ...] = ()
    generation_metrics: tuple = ()          # rightware.agent.diagnostics.GenerationMetric, numbers only
    continuations: int = 0
    error_code: str = "NONE"                # TE-05E: finite execution-error category (diagnostic only)

    def __post_init__(self):
        if self.route != "TASK" or self.operational_state not in _TERMINAL:
            raise ValueError("invalid task result")
        if self.factual_verified or (self.completion_verified and self.operational_state != "COMPLETE_VERIFIED"):
            raise ValueError("unverified claims must not become verified")
        if self.halt_reason_code not in frozenset((*_HALT_CODES.values(), "OTHER")):
            raise ValueError("untrusted halt diagnostics")
        if any(type(seq) is not int or seq < 0 or tool not in (*_SAFE_TOOLS, "OTHER")
               or status not in _SAFE_STATUSES for seq, tool, status in self.receipt_events):
            raise ValueError("untrusted receipt diagnostics")
        if self.receipt_reason_codes or self.generation_metrics:
            from rightware.agent.diagnostics import GenerationMetric, REASON_CODES
            if any(type(seq) is not int or seq < 0 or code not in REASON_CODES
                   for seq, code in self.receipt_reason_codes):
                raise ValueError("untrusted reason diagnostics")
            if any(type(m) is not GenerationMetric for m in self.generation_metrics):
                raise ValueError("untrusted generation metrics")
        if type(self.continuations) is not int or not 0 <= self.continuations <= 1:
            raise ValueError("untrusted continuation count")
        if self.error_code not in _ERROR_CODES:
            raise ValueError("untrusted error diagnostics")
        if (self.error_code != "NONE") != (self.operational_state == "ERROR"):
            raise ValueError("an execution error and the ERROR state must go together")


class TaskEntry:
    """Host-controlled opt-in bridge for ONE existing synthetic browser preset.

    Host code supplies the factory. Neither the natural-language instruction,
    nor model output, nor a user-supplied JSON object selects a capability.
    The factory must produce an actual protected AgentSession with receipt and
    completion gates already enabled. All execution stays in AgentSession.
    """

    def __init__(self, text_facade: TextFacade, *, fixture_session_factory: Callable | None = None,
                 public_session_factory: Callable | None = None, file_session_factory: Callable | None = None):
        if not isinstance(text_facade, TextFacade):
            raise TypeError("expected a RIGHTWARE text facade")
        if fixture_session_factory is not None and not callable(fixture_session_factory):
            raise TypeError("fixture_session_factory must be callable")
        if public_session_factory is not None and not callable(public_session_factory):
            raise TypeError("public_session_factory must be callable")
        self.text_facade = text_facade
        self._fixture_session_factory = fixture_session_factory
        self._public_session_factory = public_session_factory
        if file_session_factory is not None and not callable(file_session_factory):
            raise TypeError("file_session_factory must be callable")
        self._file_session_factory = file_session_factory
        self._lock = Lock()
        self._active: set[str] = set()

    def submit_text(self, session_id: str, text: str) -> TextResult:
        """The existing, tool-free D01/D02 path remains the default."""
        return self.text_facade.submit(session_id, text)

    def run_trusted_browser_fixture(self, session_id: str, instruction: str) -> TaskEntryResult:
        """Preserve TE-02 synthetic test-only mode (no real network)."""
        return self._run_trusted(session_id, instruction, self._fixture_session_factory, _FIXTURE_ID, True)

    def run_trusted_public_iana_task(self, session_id: str, instruction: str) -> TaskEntryResult:
        """Explicit host-authorized IANA-9110/9112 read-only task (real network permitted).

        This does not parse intents, enable tools on the default text path,
        or permit shell/filesystem/Windows effects. Document authenticity and
        factual correctness remain UNVERIFIED even if both pages are fetched.
        """
        return self._run_trusted(session_id, instruction, self._public_session_factory, _IANA_ID, False)

    def _run_trusted(self, session_id: str, instruction: str, factory: Callable | None,
                     preset_id: str, synthetic: bool) -> TaskEntryResult:
        """Only trusted host methods choose preset/grants; user text is never authority."""
        if (not isinstance(instruction, str) or not instruction.strip()
                or len(instruction) > self.text_facade.max_input_chars
                or any(ord(c) < 32 and c not in "\n\t\r" for c in instruction)):
            raise ValueError("invalid task instruction")
        self.text_facade.history_snapshot(session_id)  # checks host-minted session ownership
        if factory is None:
            raise PermissionError("No task execution has been enabled by the host")
        with self._lock:
            if session_id in self._active:
                raise RuntimeError("Task already running in this session")
            self._active.add(session_id)
        try:
            # Do not import the pinned vendor or start Ollama on text-only calls.
            from rightware.agent.session import AgentSession
            from rightware.agent.task_contract import TRUSTED_PRESETS

            agent = factory()
            if type(agent) is not AgentSession:
                raise PermissionError("Untrusted task executor")
            preset = TRUSTED_PRESETS[preset_id]
            budgets = agent.budgets
            if (agent.allow != _ALLOWED_SCOPE or agent.actions is not None
                    or agent.task_contract is not preset
                    or preset.synthetic is not synthetic
                    or agent.sites != preset.hosts
                    or not agent.receipts_enabled or not agent.completion_gate
                    or budgets is None or not 1 <= budgets.max_calls <= 12
                    or not 0 < budgets.deadline_seconds <= 120
                    or not 1 <= agent.max_turns <= 12):
                raise PermissionError("Task session is outside the approved task envelope")

            try:
                reply = agent.run(instruction)
            except Exception:                    # TE-05E: an unexpected failure still yields a safe record
                reply = None
            # Safe diagnostics are collected FIRST, so that no error path can discard them (TE-05E).
            receipts = agent.receipts
            diag = dict(
                receipts_count=len(receipts),
                receipt_events=_receipt_events(receipts),
                receipt_reason_codes=_receipt_reason_codes(receipts),
                generation_metrics=tuple(agent.generation_metrics),
                halt_reason_code=_HALT_CODES.get(reply.halted, "OTHER") if reply is not None else "NONE",
            )
            unknown_rows = tuple((o.oid, "UNKNOWN", None) for o in preset.objectives)

            def failed(code: str, limitation: str) -> TaskEntryResult:
                # Evidence could not be trusted: every objective stays UNKNOWN (never observed).
                return TaskEntryResult(
                    secrets.token_hex(16), session_id, "TASK", "ERROR", unknown_rows,
                    factual_verified=False, completion_verified=False, model_commentary_unverified="",
                    limitations=(limitation,), error_code=code, **diag)

            if reply is None:
                return failed("AGENT_FAILURE", "EXECUTION_FAILED")
            error_code = agent.error_code if agent.error_code in _ERROR_CODES else "OTHER"
            detail = reply.task_completion
            if (not isinstance(detail, dict)
                    or reply.completion not in _TERMINAL
                    or detail.get("state") != reply.completion
                    or detail.get("contract_id") != preset_id
                    or detail.get("answer_factually_verified") is not False):
                # Do not trust an unchecked model answer or an absent gate.
                return failed(error_code if error_code != "NONE" else "EVIDENCE_INCOMPLETE",
                              "INVALID_COMPLETION_EVIDENCE")
            objectives = detail.get("objectives")
            if not isinstance(objectives, list) or len(objectives) != len(preset.objectives):
                return failed(error_code if error_code != "NONE" else "EVIDENCE_INCOMPLETE",
                              "INCOMPLETE_OBJECTIVE_EVIDENCE")
            result_rows = []
            for index, o in enumerate(objectives):
                if (not isinstance(o, dict) or o.get("oid") != preset.objectives[index].oid
                        or o.get("state") not in ("VERIFIED", "PAGE_OBSERVED", "UNKNOWN", "MISSING")
                        or (o.get("evidence_sequence") is not None
                            and (type(o["evidence_sequence"]) is not int or o["evidence_sequence"] < 1))):
                    return failed(error_code if error_code != "NONE" else "EVIDENCE_INCOMPLETE",
                                  "MALFORMED_OBJECTIVE_EVIDENCE")
                result_rows.append((o["oid"], o["state"], o.get("evidence_sequence")))
            if reply.completion != "ERROR":
                error_code = "NONE"
            elif error_code == "NONE":
                error_code = "OTHER"
            return TaskEntryResult(
                request_id=secrets.token_hex(16), session_id=session_id, route="TASK",
                operational_state=reply.completion,
                objective_states=tuple(result_rows),
                factual_verified=False, completion_verified=reply.completion == "COMPLETE_VERIFIED",
                model_commentary_unverified=reply.text,
                limitations=(("SYNTHETIC_READ_ONLY" if synthetic else "PUBLIC_IANA_READ_ONLY"),
                             "NO_FACTUAL_VERIFICATION", "NO_INDEPENDENT_MODEL_VERIFICATION")
                + (("EXECUTION_ERROR",) if reply.completion == "ERROR" else ()),
                continuations=detail.get("continuations") if type(detail.get("continuations")) is int
                and 0 <= detail.get("continuations") <= 1 else 0,
                error_code=error_code, **diag,
            )
        finally:
            with self._lock:
                self._active.discard(session_id)


# -- TE-06A: trusted file comparison -----------------------------------------------------------------
_FILE_TASK_ID = "fixture-two-versions-compare"
_FILE_STATES = frozenset(("COMPARISON_VERIFIED", "INCOMPLETE", "UNKNOWN", "HALTED", "ERROR"))
_NARRATIVE = frozenset(("NOT_CHECKABLE", "NO_COUNTS_STATED", "COUNTS_CONSISTENT", "COUNTS_DISCREPANCY"))
_HEX64 = frozenset("0123456789abcdef")


def _sha(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX64


@dataclass(frozen=True)
class FileTaskEntryResult:
    """Structured result of the trusted file comparison. ``changes`` come from CODE (only when the
    agent's comparison was verified); the model text is carried separately as unverified."""
    request_id: str
    session_id: str
    route: str
    task_id: str
    operational_state: str
    file_a_sha256: str | None
    file_b_sha256: str | None
    read_receipts: tuple[int, ...]          # receipt sequences that verified READ_A, READ_B
    comparison_receipt: int | None          # receipt sequence that verified COMPARE
    changes: tuple | None
    comparison_verified: bool
    narrative: str                          # never "verified"; at most counts consistent with code
    error_code: str
    limitations: tuple[str, ...]
    objective_states: tuple[tuple[str, str, int | None], ...]
    model_commentary_unverified: str = ""
    receipts_count: int = 0
    receipt_events: tuple[tuple[int, str, str], ...] = ()
    receipt_reason_codes: tuple[tuple[int, str], ...] = ()
    generation_metrics: tuple = ()
    halt_reason_code: str = "NONE"
    continuations: int = 0

    def __post_init__(self):
        if self.route != "TASK" or self.operational_state not in _FILE_STATES or self.narrative not in _NARRATIVE:
            raise ValueError("invalid file task result")
        if self.comparison_verified != (self.operational_state == "COMPARISON_VERIFIED"):
            raise ValueError("comparison verification must match the verified state")
        if self.comparison_verified and (self.comparison_receipt is None or len(self.read_receipts) != 2
                                         or not _sha(self.file_a_sha256) or not _sha(self.file_b_sha256)
                                         or self.changes is None):
            raise ValueError("a verified comparison needs both reads, the comparison receipt and hashes")
        if not self.comparison_verified and self.changes is not None:
            raise ValueError("unverified comparisons must not report changes")
        if self.error_code not in _ERROR_CODES or (self.error_code != "NONE") != (self.operational_state == "ERROR"):
            raise ValueError("an execution error and the ERROR state must go together")
        if self.halt_reason_code not in frozenset((*_HALT_CODES.values(), "OTHER")):
            raise ValueError("untrusted halt diagnostics")
        if any(type(seq) is not int or seq < 0 or tool not in (*_SAFE_TOOLS, "OTHER")
               or status not in _SAFE_STATUSES for seq, tool, status in self.receipt_events):
            raise ValueError("untrusted receipt diagnostics")


def _file_record_rows(detail, contract):
    objectives = detail.get("objectives") if isinstance(detail, dict) else None
    if not isinstance(objectives, list) or [o.get("oid") if isinstance(o, dict) else None
                                            for o in objectives] != list(contract.objective_ids):
        return None
    rows = []
    for o in objectives:
        seq = o.get("evidence_sequence")
        if o.get("state") not in ("VERIFIED", "UNKNOWN", "MISSING") or (seq is not None and (type(seq) is not int
                                                                                           or seq < 1)):
            return None
        rows.append((o["oid"], o["state"], seq))
    return tuple(rows)


def _run_trusted_file_compare(self, session_id: str, instruction: str) -> FileTaskEntryResult:
    """Host-authorised comparison of the two host-bound versions A/B. The instruction is never
    authority: capability, contract, workspace and budgets all come from the host factory."""
    if (not isinstance(instruction, str) or not instruction.strip()
            or len(instruction) > self.text_facade.max_input_chars
            or any(ord(c) < 32 and c not in "\n\t\r" for c in instruction)):
        raise ValueError("invalid task instruction")
    self.text_facade.history_snapshot(session_id)
    if self._file_session_factory is None:
        raise PermissionError("No file task has been enabled by the host")
    with self._lock:
        if session_id in self._active:
            raise RuntimeError("Task already running in this session")
        self._active.add(session_id)
    try:
        from rightware.agent.file_task import TRUSTED_FILE_PRESETS, FixtureWorkspace
        from rightware.agent.session import AgentSession

        agent = self._file_session_factory()
        contract = TRUSTED_FILE_PRESETS[_FILE_TASK_ID]
        budgets = agent.budgets if type(agent) is AgentSession else None
        if (type(agent) is not AgentSession or agent.allow != frozenset({"files"})
                or agent.actions is not None or agent.file_contract is not contract
                or type(agent.file_workspace) is not FixtureWorkspace or not agent.receipts_enabled
                or agent.completion_gate or agent.task_contract is not None
                or budgets is None or not 1 <= budgets.max_calls <= 8
                or not 0 < budgets.deadline_seconds <= 120 or not 1 <= agent.max_turns <= 8):
            raise PermissionError("Task session is outside the approved file task envelope")
        try:
            reply = agent.run(instruction)
        except Exception:
            reply = None
        receipts = agent.receipts
        diag = dict(receipts_count=len(receipts), receipt_events=_receipt_events(receipts),
                    receipt_reason_codes=_receipt_reason_codes(receipts),
                    generation_metrics=tuple(agent.generation_metrics),
                    halt_reason_code=_HALT_CODES.get(reply.halted, "OTHER") if reply is not None else "NONE")
        unknown = tuple((oid, "UNKNOWN", None) for oid in contract.objective_ids)

        def failed(code, limitation):
            return FileTaskEntryResult(secrets.token_hex(16), session_id, "TASK", contract.task_id, "ERROR",
                                       None, None, (), None, None, False, "NOT_CHECKABLE", code, (limitation,),
                                       unknown, **diag)
        if reply is None:
            return failed("AGENT_FAILURE", "EXECUTION_FAILED")
        detail = reply.task_completion
        error_code = agent.error_code if agent.error_code in _ERROR_CODES else "OTHER"
        rows = _file_record_rows(detail, contract)
        if (rows is None or reply.completion not in _FILE_STATES or detail.get("state") != reply.completion
                or detail.get("task_id") != contract.task_id or detail.get("narrative_verified") is not False):
            return failed(error_code if error_code != "NONE" else "EVIDENCE_INCOMPLETE", "INVALID_COMPLETION_EVIDENCE")
        verified = reply.completion == "COMPARISON_VERIFIED"
        if reply.completion != "ERROR":
            error_code = "NONE"
        elif error_code == "NONE":
            error_code = "OTHER"
        seqs = {oid: seq for oid, state, seq in rows if state == "VERIFIED"}
        changes = detail.get("changes") if verified else None
        return FileTaskEntryResult(
            request_id=secrets.token_hex(16), session_id=session_id, route="TASK", task_id=contract.task_id,
            operational_state=reply.completion,
            file_a_sha256=detail.get("file_a_sha256") if _sha(detail.get("file_a_sha256")) else None,
            file_b_sha256=detail.get("file_b_sha256") if _sha(detail.get("file_b_sha256")) else None,
            read_receipts=tuple(seqs[k] for k in ("READ_A", "READ_B") if k in seqs),
            comparison_receipt=seqs.get("COMPARE"),
            changes=tuple(changes) if isinstance(changes, list) else None,
            comparison_verified=verified,
            narrative=detail.get("narrative") if detail.get("narrative") in _NARRATIVE else "NOT_CHECKABLE",
            error_code=error_code,
            limitations=("SYNTHETIC_FIXTURE_FILES", "READ_ONLY", "NARRATIVE_NOT_VERIFIED", "LINUX_SECURE_OPEN_ONLY")
            + (("EXECUTION_ERROR",) if reply.completion == "ERROR" else ()),
            objective_states=rows, model_commentary_unverified=reply.text,
            continuations=detail.get("continuations") if detail.get("continuations") in (0, 1) else 0, **diag)
    finally:
        with self._lock:
            self._active.discard(session_id)


TaskEntry.run_trusted_file_compare = _run_trusted_file_compare


def file_task_record(result: FileTaskEntryResult) -> dict:
    """JSON-ready report (no model transcript; model text is excluded, unverified anyway)."""
    import dataclasses as _dc
    return {
        "task_id": result.task_id, "request_id": result.request_id, "operational_state": result.operational_state,
        "file_a_sha256": result.file_a_sha256, "file_b_sha256": result.file_b_sha256,
        "read_receipts": list(result.read_receipts), "comparison_receipt": result.comparison_receipt,
        "changes": list(result.changes) if result.changes is not None else None,
        "comparison_verified": result.comparison_verified, "narrative": result.narrative,
        "narrative_verified": False, "error_code": result.error_code, "limitations": list(result.limitations),
        "objectives": [{"id": o, "state": st, "receipt_sequence": q} for o, st, q in result.objective_states],
        "receipts_count": result.receipts_count, "halt_reason_code": result.halt_reason_code,
        "continuations": result.continuations,
        "receipt_events": [{"sequence": q, "tool": t, "status": st} for q, t, st in result.receipt_events],
        "receipt_reason_codes": [{"sequence": q, "code": c} for q, c in result.receipt_reason_codes],
        "generations": [_dc.asdict(m) for m in result.generation_metrics],
    }
