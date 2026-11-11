"""WORK-04 R2: overwrite pre-validation that does not burn a write slot.

Problem (QWEN REAL, run 42821805533): an overwrite attempt was approved by the
frozen WORK-02 Policy, consumed one of the two `write_report` slots, and was
then refused by the sandbox. The corrected `_v2` version became impossible.

R2-only fix, WORK-02 policy file untouched (this is a subclass):
* A `write_report` whose target ALREADY exists in output/ (same
  case-insensitive rule as the sandbox) is pre-validated BEFORE authorization.
* It still consumes one GLOBAL call (`calls += 1`) and is logged.
* It does NOT consume a `write_report` slot.
* It is approved only as a REFUSAL: the call is flagged and `WriteReportR2`
  refuses it without touching the file system, whatever happens meanwhile.
* All earlier denials keep precedence: fail-closed batch, cancel, deadline,
  global step limit, invalid names/schema (handled by the parent, which also
  keeps counting slots for every non-overwrite write).
* Repeated overwrite attempts: at most `MAX_FREE_OVERWRITE_REFUSALS` are free
  of a write slot; further ones are denied outright (still one global call
  each), so the global budget always bounds the loop.
* The definitive sandbox check (`write_new`: no-overwrite listing + atomic
  `os.link`) stays mandatory for every write that is actually executed, so a
  file created between pre-check and execution is still refused.
"""
from __future__ import annotations

import os

from w02lab.policy import Policy, canonical
from w02lab.sandbox import SandboxError
from w02lab.tools import WriteReport
from w04lab.recovery_r2 import v2_name  # noqa: F401  (re-exported)

OVERWRITE_BASE = "já existe um relatório com esse nome; não é permitido sobrescrever"


def overwrite_message(name: str) -> str:
    v2 = v2_name(name)
    if v2 is None:
        return OVERWRITE_BASE + ". Não são permitidas mais versões"
    return OVERWRITE_BASE + f". Escreve UMA versão corrigida NOVA com o nome {v2} e verifica-a"


class OverwritePrecheckPolicy(Policy):
    MAX_FREE_OVERWRITE_REFUSALS = 2

    NO_PATH = "sem caminho autorizado para concluir: escritas ou verificações esgotadas e a última verificação falhou"

    def __init__(self, *, sandbox, **kwargs):
        super().__init__(**kwargs)
        self._sandbox = sandbox
        self.overwrite_refusals = 0
        self._overwrite_keys: list[str] = []
        self._last_written: str | None = None
        self._verify_results: dict[str, bool] = {}   # report name -> last verification passed

    # -- R2-B: fail-closed stop when completion is no longer reachable ------
    def note_success(self, name: str, args: dict) -> None:
        super().note_success(name, args)
        if name == "write_report":
            with self._lock:
                self._last_written = args["name"]

    def note_verification(self, report_name: str, passed: bool) -> None:
        with self._lock:
            self._verify_results[report_name] = bool(passed)

    def _left(self, tool: str) -> int:
        return self.budgets.per_tool.get(tool, 0) - self.per_tool.get(tool, 0)

    @property
    def halt_reason(self) -> str | None:
        base = super().halt_reason
        if base:
            return base
        with self._lock:
            last = self._last_written
            if last is None or self._verify_results.get(last) is True:
                return None
            failed = self._verify_results.get(last) is False
            if (failed and self._left("write_report") <= 0) or self._left("verify_report") <= 0:
                return self.NO_PATH
            return None

    def _target_exists(self, name: str) -> bool:
        return name.lower() in {n.lower() for n in os.listdir(self._sandbox.output_dir)}

    def before_tool_call(self, name: str, args: dict) -> bool:
        if (name != "write_report" or not isinstance(args, dict)
                or self.validate(name, args) is not None or not self._target_exists(args["name"])):
            return super().before_tool_call(name, args)
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
            elif not self.write_authorized:
                reason = "escrita não autorizada nesta tarefa"
            elif self.overwrite_refusals >= self.MAX_FREE_OVERWRITE_REFUSALS:
                reason = "tentativas repetidas de sobrescrever um relatório existente"
            self.calls += 1                      # global budget always consumed
            if reason is not None:
                self._record(name, args, False, reason)
                return False
            self.overwrite_refusals += 1         # NO per_tool['write_report'] increment
            key = canonical(name, args)
            self._approved.append(key)           # approved ONLY to deliver an explicit refusal
            self._overwrite_keys.append(key)
            self._record(name, args, True, "pré-validação R2: alvo existente; recusa sem consumir quota de escrita")
            return True

    def take_overwrite_flag(self, name: str, args: dict) -> bool:
        with self._lock:
            key = canonical(name, args)
            if key in self._overwrite_keys:
                self._overwrite_keys.remove(key)
                return True
            return False


class WriteReportR2(WriteReport):
    """Refuses flagged overwrites before any file access; otherwise the frozen
    WORK-02 write path (sandbox.write_new) runs unchanged."""

    def run(self, name: str, content: str) -> str:
        flagged = isinstance(self.policy, OverwritePrecheckPolicy) and \
            self.policy.take_overwrite_flag(self.tool_name, {"name": name, "content": content})
        if flagged:
            raise SandboxError(overwrite_message(name))
        try:
            return super().run(name, content)
        except SandboxError as exc:
            if "sobrescrever" in str(exc):     # race fallback: definitive sandbox refusal
                raise SandboxError(overwrite_message(name)) from None
            raise
