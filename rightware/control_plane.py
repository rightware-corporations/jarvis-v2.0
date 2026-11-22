"""JRV-P1: unified Control Plane — ONE product entry for conversation and supervised tasks.

    INPUT → SESSION → ROUTE → AUTHORIZATION → EXECUTOR → EVIDENCE → RESULT

It adds no executor, policy or verifier. It only composes what already exists:
* SESSION / ROUTE / text answers: ``TaskEntry.submit_text`` → ``TextFacade`` (tool-free, unchanged);
* EXECUTOR / EVIDENCE: ``TaskEntry.run_trusted_file_compare`` → ``AgentSession`` (allow={"files"}) →
  ``AgentPolicy`` + ``ReceiptLedger`` → ``evaluate_file_task`` (TE-06A, unchanged);
* RESULT: one state vocabulary derived ONLY from those results.

Authorization (host-defined, never text-defined)
------------------------------------------------
* A capability exists only if the HOST process enabled it at start (``enable_trial_compare=True``; the
  console exposes it only with the launch flag ``--tarefa-ensaio``). Nothing a user or model writes adds one.
* Requesting a capability returns ``AUTORIZACAO_NECESSARIA`` with a single-use, short-lived code minted by the
  host. The task runs only when the operator types the exact host command ``/autorizar <code>`` for that
  pending request. Free text, JSON with "authorized": true, quoted commands or model output never authorise.
* The only capability is the TE-06A comparison of two SYNTHETIC files that the host itself writes into a
  fresh temporary directory with host-chosen names; the model names logical ids A/B only. No user paths, no
  OS reads, no shell, no writes by the agent, no personal documents. It is NOT real-document access.
"""
from __future__ import annotations

import dataclasses
import re
import secrets
import shutil
import tempfile
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from rightware.task_entry import FileTaskEntryResult, TaskEntry
from rightware.text_facade import Route, Status, TextFacade, TextResult

TRIAL_COMPARE = "comparar-versoes-ensaio"
CAPABILITY_TEXT = {
    TRIAL_COMPARE: ("Comparar duas versões SINTÉTICAS de um documento de ensaio (A e B), criadas pelo anfitrião "
                    "numa pasta temporária. Só leitura; o resultado vem dos recibos e do verificador RIGHTWARE."),
}
# Synthetic fixtures written by the HOST (never user/model supplied). Known ground truth for the verifier.
TRIAL_FILES = {"A": ("versao_a.txt", "Relatório trimestral\nreceitas: 100\ncustos: 80\nnotas: nenhuma\nfim\n"),
               "B": ("versao_b.txt", "Relatório trimestral\nreceitas: 120\nnotas: nenhuma\nanexo: tabela 2\nfim\n")}
TRIAL_INSTRUCTION = ("Compara as duas versões autorizadas deste documento de ensaio, identifica as alterações e "
                     "apresenta um relatório curto.")
CODE_TTL_SECONDS = 120.0


class State(str, Enum):
    RESPOSTA_SEM_EXECUCAO = "RESPOSTA_SEM_EXECUCAO"
    TAREFA_NAO_AUTORIZADA = "TAREFA_NAO_AUTORIZADA"
    AUTORIZACAO_NECESSARIA = "AUTORIZACAO_NECESSARIA"
    TAREFA_EM_EXECUCAO = "TAREFA_EM_EXECUCAO"
    EXECUCAO_PARCIAL = "EXECUCAO_PARCIAL"
    TAREFA_CANCELADA = "TAREFA_CANCELADA"
    EXECUCAO_FALHADA = "EXECUCAO_FALHADA"
    RESULTADO_VERIFICADO = "RESULTADO_VERIFICADO"
    RESULTADO_DESCONHECIDO = "RESULTADO_DESCONHECIDO"


LABELS = {
    State.RESPOSTA_SEM_EXECUCAO: "Resposta sem execução",
    State.TAREFA_NAO_AUTORIZADA: "Tarefa não autorizada — nada foi executado",
    State.AUTORIZACAO_NECESSARIA: "Autorização necessária — nada foi executado ainda",
    State.TAREFA_EM_EXECUCAO: "Tarefa em execução",
    State.EXECUCAO_PARCIAL: "Execução parcialmente concluída — resultado não verificado",
    State.TAREFA_CANCELADA: "Tarefa cancelada",
    State.EXECUCAO_FALHADA: "Execução falhada",
    State.RESULTADO_VERIFICADO: "Resultado verificado por evidência (recibos + verificador RIGHTWARE)",
    State.RESULTADO_DESCONHECIDO: "Resultado desconhecido — sem provas suficientes",
}


@dataclasses.dataclass(frozen=True)
class TaskOutcome:
    """What the Control Plane shows for a supervised task. ``verified`` is True ONLY for the executor's own
    COMPARISON_VERIFIED state; changes are present only then (they come from code, not from the model)."""
    state: State
    capability: str
    operational_state: str | None
    verified: bool
    changes: tuple | None
    objectives: tuple
    receipts_count: int
    receipt_events: tuple
    halt_reason_code: str
    error_code: str
    model_commentary_unverified: str
    seconds: float

    def __post_init__(self):
        if self.verified != (self.state == State.RESULTADO_VERIFICADO):
            raise ValueError("only an executor-verified result may be shown as verified")
        if not self.verified and self.changes is not None:
            raise ValueError("unverified results carry no changes")


def text_state(result: TextResult) -> State:
    """Text path: never an execution state."""
    if result.route == Route.TASK:
        return State.TAREFA_NAO_AUTORIZADA
    return State.RESPOSTA_SEM_EXECUCAO


def task_state(result: FileTaskEntryResult, cancelled: bool) -> State:
    """Executor path: derived ONLY from the TE-06A executor/verifier result."""
    op = result.operational_state
    if op == "COMPARISON_VERIFIED" and result.comparison_verified:
        return State.RESULTADO_VERIFICADO
    if cancelled or result.halt_reason_code == "CANCELLED":
        return State.TAREFA_CANCELADA
    if op == "ERROR":
        return State.EXECUCAO_FALHADA
    if any(st == "VERIFIED" for _, st, _ in result.objective_states):
        return State.EXECUCAO_PARCIAL
    return State.RESULTADO_DESCONHECIDO


class TrialWorkspace:
    """Host-created temporary directory with the two synthetic files; removed on close."""

    def __init__(self):
        from rightware.agent.file_task import FixtureWorkspace
        self.root = Path(tempfile.mkdtemp(prefix="jarvis-ensaio-"))
        try:
            for _, (name, text) in TRIAL_FILES.items():
                (self.root / name).write_text(text, encoding="utf-8")
            self.workspace = FixtureWorkspace(self.root, {k: v[0] for k, v in TRIAL_FILES.items()}, max_bytes=16384)
        except BaseException:                       # JRV-P2 fix 2: never leave a half-prepared directory
            shutil.rmtree(self.root, ignore_errors=True)
            raise

    def close(self):
        try:
            self.workspace.close()
        finally:
            shutil.rmtree(self.root, ignore_errors=True)


def real_session_factory(model: str, workspace_box: dict, agent_box: dict) -> Callable:
    """Host factory for the REAL executor: local Ollama engine, AgentSession limited to the TE-06A envelope."""
    def make():
        from openjarvis.engine.ollama import OllamaEngine
        from rightware.agent.session import AgentSession, Budgets
        engine = OllamaEngine(host="http://127.0.0.1:11434", timeout=120)
        agent = AgentSession(engine, model, allow={"files"}, confirm=lambda _: None, actions=None, receipts=True,
                             file_task="fixture-two-versions-compare",
                             file_workspace=workspace_box["ws"].workspace,
                             budgets=Budgets(max_calls=6, deadline_seconds=120), max_turns=6,
                             max_tokens=768, temperature=0.2)
        agent_box["agent"] = agent
        return agent
    return make


@dataclasses.dataclass(frozen=True)
class Refusal:
    """A task that did NOT run. ``reason``: CODE_INVALID (wrong/expired/used code), BUSY (another task is
    running), ENVELOPE_REFUSED (the executor was outside the approved envelope). Never used for failures."""
    state: State
    reason: str


_HOST_STATUS_LINE = re.compile(r"^\s*Estado(?: da tarefa \([^)]*\))?:", re.M)


def model_text_only(text: str) -> str:
    """JRV-P2 fix 1: the executor appends its own generic status lines ("Estado: …", "Estado da tarefa (…): …")
    to the model's text; they can contradict the code-verified state. The Control Plane shows the verified state
    itself, so those host-appended lines are removed from the (unverified) model commentary."""
    return "\n".join(l for l in str(text or "").splitlines() if not _HOST_STATUS_LINE.match(l)).strip()


def failure_outcome(capability: str, error_code: str, seconds: float) -> TaskOutcome:
    return TaskOutcome(State.EXECUCAO_FALHADA, capability, "ERROR", False, None, (), 0, (), "NONE", error_code, "",
                       seconds)


class ControlPlane:
    """Authority for authorization (host-enabled capability + single-use operator code). Executors are
    registered by the HOST: the P1 trial comparison and, optionally, the JRV-P2 goose mission adapter."""

    def __init__(self, entry_text_facade: TextFacade, *, enable_trial_compare: bool = False,
                 session_factory_builder: Callable | None = None, model: str = "qwen3.5:2b", clock=time.monotonic,
                 goose=None):
        if not isinstance(entry_text_facade, TextFacade):
            raise TypeError("expected a RIGHTWARE text facade")
        self.facade, self.model, self._clock = entry_text_facade, model, clock
        self._ws: dict = {}
        self._agent: dict = {}
        builder = session_factory_builder or real_session_factory
        factory = builder(model, self._ws, self._agent) if enable_trial_compare else None
        self.entry = TaskEntry(entry_text_facade, file_session_factory=factory)
        self.session = entry_text_facade.open_session()
        self._executors: dict = {}
        self._descriptions: dict = {}
        if enable_trial_compare:
            self._executors[TRIAL_COMPARE] = self._run_trial_compare
            self._descriptions[TRIAL_COMPARE] = CAPABILITY_TEXT[TRIAL_COMPARE]
        self._goose = goose
        if goose is not None:
            self._executors[goose.capability] = goose.run
            self._descriptions[goose.capability] = goose.description
        self.capabilities = tuple(self._executors)
        self._pending: dict | None = None
        self._lock = threading.Lock()
        self._cancelled = threading.Event()
        self._active: str | None = None
        self.running = False
        self.audit: list[dict] = []          # host decisions (no content), for evidence

    def describe(self, capability: str) -> str:
        return self._descriptions[capability]

    # -- INPUT → SESSION → ROUTE (text) --------------------------------------------------------
    def submit_text(self, text: str) -> tuple[State, TextResult]:
        result = self.entry.submit_text(self.session, text)
        return text_state(result), result

    # -- AUTHORIZATION ------------------------------------------------------------------------------
    def request(self, capability: str) -> tuple[State, str]:
        """Host command: ask for an approved capability. Returns the one-time code to show the operator."""
        if capability not in self.capabilities:
            self.audit.append({"event": "request_refused", "capability": str(capability)[:40]})
            return State.TAREFA_NAO_AUTORIZADA, ""
        with self._lock:
            code = secrets.token_hex(3).upper()
            self._pending = {"capability": capability, "code": code, "expires": self._clock() + CODE_TTL_SECONDS}
        self.audit.append({"event": "authorization_requested", "capability": capability})
        return State.AUTORIZACAO_NECESSARIA, code

    def _consume(self, code: str) -> str | None:
        with self._lock:
            p, self._pending = self._pending, None          # single use: any attempt consumes it
        if p is None or not isinstance(code, str) or self._clock() > p["expires"] \
                or not secrets.compare_digest(code.strip().upper(), p["code"]):
            self.audit.append({"event": "authorization_refused"})
            return None
        self.audit.append({"event": "authorized", "capability": p["capability"]})
        return p["capability"]

    # -- EXECUTOR → EVIDENCE → RESULT ---------------------------------------------------------------
    def authorize_and_run(self, code: str, on_start: Callable[[], None] | None = None) -> TaskOutcome | Refusal:
        capability = self._consume(code)
        if capability is None:
            return Refusal(State.TAREFA_NAO_AUTORIZADA, "CODE_INVALID")
        with self._lock:                                    # JRV-P2 fix 5: one task at a time, atomically
            if self.running:
                self.audit.append({"event": "refused_busy"})
                return Refusal(State.TAREFA_NAO_AUTORIZADA, "BUSY")
            self.running, self._active = True, capability
        started = self._clock()
        self._cancelled.clear()
        try:
            outcome = self._executors[capability](self._cancelled, on_start)
        except PermissionError:
            self.audit.append({"event": "executor_refused_envelope"})
            return Refusal(State.TAREFA_NAO_AUTORIZADA, "ENVELOPE_REFUSED")
        except Exception as exc:                            # JRV-P2 fix 4: an internal error is a FAILURE
            self.audit.append({"event": "executor_internal_error", "type": type(exc).__name__})
            outcome = failure_outcome(capability, "INTERNAL_" + type(exc).__name__.upper()[:40],
                                      round(self._clock() - started, 2))
        finally:
            with self._lock:
                self.running, self._active = False, None
        self.audit.append({"event": "task_finished", "state": outcome.state.value, "receipts": outcome.receipts_count})
        return outcome

    def _run_trial_compare(self, cancelled: threading.Event, on_start) -> TaskOutcome:
        started = self._clock()
        ws = None
        try:
            ws = TrialWorkspace()                           # JRV-P2 fix 2: created inside the cleanup scope
            self._ws["ws"] = ws
            if on_start:
                on_start()
            result = self.entry.run_trusted_file_compare(self.session, TRIAL_INSTRUCTION)
        finally:
            self._agent.pop("agent", None)
            self._ws.pop("ws", None)
            if ws is not None:
                ws.close()
        state = task_state(result, cancelled.is_set())
        return TaskOutcome(state=state, capability=TRIAL_COMPARE, operational_state=result.operational_state,
                           verified=state == State.RESULTADO_VERIFICADO,
                           changes=result.changes if state == State.RESULTADO_VERIFICADO else None,
                           objectives=result.objective_states, receipts_count=result.receipts_count,
                           receipt_events=result.receipt_events, halt_reason_code=result.halt_reason_code,
                           error_code=result.error_code,
                           model_commentary_unverified=model_text_only(result.model_commentary_unverified),
                           seconds=round(self._clock() - started, 2))

    def cancel(self) -> bool:
        """Cancel the running task through its executor's own cancellation."""
        if not self.running:
            return False
        if self._active == TRIAL_COMPARE:
            agent = self._agent.get("agent")
            if agent is None:
                return False
            self._cancelled.set()
            agent.cancel()
            return True
        if self._goose is not None and self._active == self._goose.capability:
            self._cancelled.set()
            return self._goose.cancel()
        return False

    def close(self) -> None:
        ws = self._ws.pop("ws", None)
        if ws is not None:
            ws.close()
        self.facade.close()
