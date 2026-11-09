"""Authorization layer: validated at the hook (before execution) AND again at the
tool boundary (at execution), independent of the prompt.

* Allowlist by exact, case-sensitive name; schema with no extra keys.
* Names validated by the sandbox rules; content size limits.
* Budgets: total calls, per-tool calls, wall-clock deadline.
* Plausible order: write only after a successful read; verify only a report
  written in this run.
* Writes need an explicit (synthetic) authorization bound to output/, new
  files only.
* Approval is bound to (tool, canonical arguments) and consumed once at
  execution, so arguments changed after approval are refused.
* A batch of tool calls is fail-closed: if any call in one model response is
  invalid, none of them executes.
* Cancellation flag: once set, every further call is denied.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import time

from w02lab.sandbox import SandboxError, check_name

SCHEMAS = {
    "list_workspace": {},
    "read_document": {"name": str},
    "write_report": {"name": str, "content": str},
    "verify_report": {"name": str},
}
MAX_CONTENT_CHARS = 20_000


@dataclasses.dataclass
class Budgets:
    max_calls: int = 12
    per_tool: dict = dataclasses.field(default_factory=lambda: {
        "list_workspace": 3, "read_document": 6, "write_report": 2, "verify_report": 3})
    deadline_seconds: float = 300.0


def canonical(name: str, args: dict) -> str:
    blob = json.dumps({"tool": name, "args": args}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Policy:
    def __init__(self, *, write_authorized: bool, budgets: Budgets | None = None,
                 clock=time.monotonic):
        self.write_authorized = write_authorized
        self.budgets = budgets or Budgets()
        self._clock = clock
        self._start = clock()
        self._lock = threading.Lock()
        self.calls = 0
        self.per_tool: dict[str, int] = {}
        self.read_ok: set[str] = set()
        self.written: set[str] = set()
        self._approved: list[str] = []
        self._deny_next = 0
        self.cancelled = False
        self.log: list[dict] = []

    # -- static validation (no state change) ------------------------------
    def validate(self, name, args) -> str | None:
        """Return a denial reason, or None if (name, args) is well formed."""
        if not isinstance(name, str) or name not in SCHEMAS:
            return "ferramenta fora da allowlist"
        if not isinstance(args, dict):
            return "argumentos não são um objecto"
        schema = SCHEMAS[name]
        if set(args) != set(schema):
            return "argumentos em falta ou não previstos"
        for key, typ in schema.items():
            if not isinstance(args[key], typ) or isinstance(args[key], bool):
                return f"tipo inválido em '{key}'"
        try:
            if name == "read_document":
                check_name(args["name"])
            elif name in ("write_report", "verify_report"):
                check_name(args["name"], report=True)
        except SandboxError as exc:
            return str(exc)
        if name == "write_report" and len(args["content"]) > MAX_CONTENT_CHARS:
            return "conteúdo acima do limite"
        return None

    def batch_guard(self, raw_calls: list[dict]) -> None:
        """Called by the engine wrapper for each model response with tool calls."""
        if len(raw_calls) < 2:
            return
        for tc in raw_calls:
            try:
                args = json.loads(tc.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                args = None
            if self.validate(tc.get("name"), args) is not None:
                with self._lock:
                    self._deny_next = len(raw_calls)
                self._record("<batch>", {}, False, "lote com chamada inválida: nenhuma executada")
                return

    # -- hook used by OrchestratorAgent(before_tool_call=...) -------------
    def before_tool_call(self, name: str, args: dict) -> bool:
        with self._lock:
            reason = None
            if self._deny_next > 0:
                self._deny_next -= 1
                reason = "lote fail-closed"
            elif self.cancelled:
                reason = "tarefa cancelada"
            elif self._clock() - self._start > self.budgets.deadline_seconds:
                reason = "tempo esgotado"
            elif self.calls >= self.budgets.max_calls:
                reason = "limite de passos atingido"
            else:
                reason = self.validate(name, args)
            if reason is None:
                used = self.per_tool.get(name, 0)
                if used >= self.budgets.per_tool.get(name, 0):
                    reason = "limite de chamadas desta ferramenta atingido"
                elif name == "write_report" and not self.write_authorized:
                    reason = "escrita não autorizada nesta tarefa"
                elif name == "write_report" and not self.read_ok:
                    reason = "ordem inválida: ler documentos antes de escrever"
                elif name == "verify_report" and args["name"] not in self.written:
                    reason = "só é possível verificar um relatório criado nesta tarefa"
            self.calls += 1
            if reason is None:
                self.per_tool[name] = self.per_tool.get(name, 0) + 1
                self._approved.append(canonical(name, args))
            self._record(name, args, reason is None, reason)
            return reason is None

    # -- boundary re-validation at execution ------------------------------
    def authorize_execution(self, name: str, args: dict) -> None:
        """Raise PermissionError unless this exact call was approved and is still valid."""
        with self._lock:
            reason = None
            if self.cancelled:
                reason = "tarefa cancelada"
            else:
                reason = self.validate(name, args)
            key = canonical(name, args)
            if reason is None and key not in self._approved:
                reason = "chamada não aprovada ou argumentos alterados após aprovação"
            if reason is None:
                self._approved.remove(key)     # single use
            if reason is not None:
                self._record(name, args, False, "fronteira: " + reason)
                raise PermissionError(reason)

    def note_success(self, name: str, args: dict) -> None:
        with self._lock:
            if name == "read_document":
                self.read_ok.add(args["name"])
            elif name == "write_report":
                self.written.add(args["name"])

    @property
    def halt_reason(self) -> str | None:
        """Why the harness must stop asking the model for more steps, if at all."""
        with self._lock:
            if self.cancelled:
                return "tarefa cancelada"
            if self.calls >= self.budgets.max_calls:
                return "orçamento de passos esgotado"
            if self._clock() - self._start > self.budgets.deadline_seconds:
                return "tempo esgotado"
            return None

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True

    def _record(self, name, args, allowed, reason):
        safe = {k: (v if not isinstance(v, str) or len(v) <= 120 else
                    f"<{len(v)} chars sha256={hashlib.sha256(v.encode()).hexdigest()[:16]}>")
                for k, v in (args or {}).items()} if isinstance(args, dict) else {"_raw": "<invalid>"}
        self.log.append({"t": round(self._clock() - self._start, 4), "tool": str(name)[:60],
                         "args": safe, "allowed": allowed, "reason": reason})

    @property
    def denials(self) -> list[dict]:
        return [e for e in self.log if not e["allowed"]]
