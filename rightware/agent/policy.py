"""Product tool policy for the JARVIS agent (contract C1-C4, C9, C10).

Stdlib only, independent of the WORK-04 lab: no scenarios, truth, oracles or
report-format rules. Every model tool call passes two checks:

1. ``before_tool_call`` (hook, before execution): closed registry, exact
   schema, session authorisation, budgets, deadline, cancel, fail-closed
   batches. An approval is bound to the exact canonical arguments.
2. ``authorize_execution`` (tool boundary): the same call must have been
   approved and is consumed once.

Consequential tools additionally need a HUMAN confirmation obtained by the
caller (never text produced by the model); WindowsActions already enforces
this. The audit records tool names, decisions and outcomes, never
conversation text; URL arguments are reduced to host + SHA-256.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable
from urllib.parse import urlsplit


@dataclasses.dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    params: dict[str, dict]            # JSON-schema properties (type string; optional enum/maxLength)
    required: tuple[str, ...]
    session_flag: str                  # "web" | "actions": the session must allow it
    consequential: bool                # needs human confirmation at execution
    max_calls: int

    def schema(self) -> dict:
        return {"type": "object", "properties": self.params, "required": list(self.required),
                "additionalProperties": False}


@dataclasses.dataclass
class Budgets:
    max_calls: int = 6
    deadline_seconds: float = 180.0


def canonical(name: str, args: dict) -> str:
    return hashlib.sha256(json.dumps({"t": name, "a": args}, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _safe_args(args: Any) -> dict:
    if not isinstance(args, dict):
        return {"_raw": "<invalid>"}
    out = {}
    for k, v in args.items():
        if k == "url" and isinstance(v, str):
            out[k] = {"host": (urlsplit(v).hostname or "")[:80],
                      "sha256": hashlib.sha256(v.encode("utf-8")).hexdigest()[:16]}
        elif k == "text" and isinstance(v, str):         # typed queries: length + hash only
            out[k] = {"chars": len(v), "sha256": hashlib.sha256(v.encode("utf-8")).hexdigest()[:16]}
        elif isinstance(v, str) and len(v) > 60:
            out[k] = f"<{len(v)} chars sha256={hashlib.sha256(v.encode()).hexdigest()[:16]}>"
        else:
            out[k] = v
    return out


class AgentPolicy:
    def __init__(self, tools: dict[str, ToolDef], *, allow: set[str], budgets: Budgets | None = None,
                 clock: Callable[[], float] = time.monotonic, audit_path: Path | None = None):
        self.tools = dict(tools)
        self.allow = set(allow)
        self.budgets = budgets or Budgets()
        self._clock, self._start = clock, clock()
        self._lock = threading.Lock()
        self.calls = 0
        self.per_tool: dict[str, int] = {}
        self._approved: list[str] = []
        self._deny_next = 0
        self.cancelled = False
        self.log: list[dict] = []
        self.audit_path = audit_path
        self.audit_failures = 0

    # -- static validation --------------------------------------------------
    def validate(self, name: Any, args: Any) -> str | None:
        tool = self.tools.get(name) if isinstance(name, str) else None
        if tool is None:
            return "ferramenta fora do registo"
        if not isinstance(args, dict):
            return "argumentos não são um objecto"
        if set(args) - set(tool.params) or set(tool.required) - set(args):
            return "argumentos em falta ou não previstos"
        for key, value in args.items():
            spec = tool.params[key]
            if spec.get("type") == "string":
                if not isinstance(value, str):
                    return f"tipo inválido em '{key}'"
                if len(value) > spec.get("maxLength", 2048):
                    return f"'{key}' demasiado longo"
            if "enum" in spec and value not in spec["enum"]:
                return f"valor não permitido em '{key}'"
        return None

    def _batch_problem(self, raw_calls: list[dict]) -> str | None:
        """Full pre-validation of a model response (R1 F2): names, schemas, session
        capabilities, cancellation, deadline, and per-tool and global quotas
        counting the WHOLE batch. Caller holds the lock."""
        if self.cancelled:
            return "tarefa cancelada"
        if self._clock() - self._start > self.budgets.deadline_seconds:
            return "tempo esgotado"
        if self.calls + len(raw_calls) > self.budgets.max_calls:
            return "o lote excede o limite de passos"
        planned: dict[str, int] = {}
        for tc in raw_calls:
            try:
                args = json.loads(tc.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                return "argumentos inválidos no lote"
            name = tc.get("name")
            reason = self.validate(name, args)
            if reason:
                return reason
            tool = self.tools[name]
            if tool.session_flag not in self.allow:
                return f"capacidade '{tool.session_flag}' não autorizada nesta sessão"
            planned[name] = planned.get(name, 0) + 1
            if self.per_tool.get(name, 0) + planned[name] > tool.max_calls:
                return "o lote excede o limite de chamadas de uma ferramenta"
        return None

    def batch_guard(self, raw_calls: list[dict]) -> None:
        """Any problem in a model response with several calls denies ALL of them."""
        if len(raw_calls) < 2:
            return
        with self._lock:
            problem = self._batch_problem(raw_calls)
            if problem:
                self._deny_next = len(raw_calls)
        if problem:
            self._record("<batch>", {}, False, "lote recusado por inteiro: " + problem)

    # -- hook ------------------------------------------------------------------
    def before_tool_call(self, name: str, args: dict) -> bool:
        with self._lock:
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
                tool = self.tools[name]
                if tool.session_flag not in self.allow:
                    reason = f"capacidade '{tool.session_flag}' não autorizada nesta sessão"
                elif self.per_tool.get(name, 0) >= tool.max_calls:
                    reason = "limite de chamadas desta ferramenta atingido"
            # Mandatory audit (R1 F4): persist the decision BEFORE any state change;
            # if it cannot be persisted, deny and change nothing else.
            if not self._persist(self._entry(name, args, reason is None, reason)):
                self._memory(self._entry(name, args, False, "auditoria indisponível: negado"))
                return False
            self.calls += 1
            if reason is None:
                self.per_tool[name] = self.per_tool.get(name, 0) + 1
                self._approved.append(canonical(name, args))
            return reason is None

    # -- boundary --------------------------------------------------------------
    def authorize_execution(self, name: str, args: dict) -> None:
        with self._lock:
            if self.cancelled:
                reason = "tarefa cancelada"
            elif self._clock() - self._start > self.budgets.deadline_seconds:
                reason = "tempo esgotado"                       # R1 F3: deadline rechecked here
            else:
                reason = self.validate(name, args)
            key = canonical(name, args)
            if reason is None and key not in self._approved:
                reason = "chamada não aprovada ou argumentos alterados após aprovação"
            if reason is None:
                self._approved.remove(key)
            else:
                self._record(name, args, False, "fronteira: " + reason)
                raise PermissionError(reason)

    def note_outcome(self, name: str, args: dict, outcome: str) -> bool:
        """Record an executed tool's outcome. False if the audit could not be persisted."""
        return self._record(name, args, True, None, outcome=outcome)

    @property
    def halt_reason(self) -> str | None:
        with self._lock:
            if self.cancelled:
                return "tarefa cancelada"
            if self.calls >= self.budgets.max_calls:
                return "limite de passos atingido"
            if self._clock() - self._start > self.budgets.deadline_seconds:
                return "tempo esgotado"
            return None

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True

    @staticmethod
    def _entry(name, args, allowed, reason, outcome=None) -> dict:
        entry = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(), "tool": str(name)[:60],
                 "args": _safe_args(args), "allowed": allowed, "reason": reason}
        if outcome is not None:
            entry["outcome"] = outcome
        return entry

    def _memory(self, entry: dict) -> None:
        self.log.append(entry)

    def _persist(self, entry: dict) -> bool:
        """In-memory log always; file audit when configured. False if the file write failed."""
        self._memory(entry)
        if self.audit_path is None:
            return True
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return True
        except OSError:
            self.audit_failures += 1
            self.log.pop()
            return False

    def _record(self, name, args, allowed, reason, outcome=None) -> bool:
        ok = self._persist(self._entry(name, args, allowed, reason, outcome))
        if not ok:
            self._memory(self._entry(name, args, allowed, (reason or "") + " [auditoria falhou]", outcome))
        return ok
