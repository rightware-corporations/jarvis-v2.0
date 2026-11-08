"""The only two Windows effects Jarvis do Issa may perform.

Design rules (P0 safety):
- An action is chosen by deterministic Portuguese rules, never by the model.
- It runs only if the session was started with explicit authorization
  (``--allow-actions``) AND the user confirms this specific action.
- Fixed absolute executables, no shell, no user-supplied arguments.
- Success is reported only after a new process of the expected image is
  observed; otherwise the outcome is reported as not verified or failed.
- The audit log records action ids and outcomes, never conversation text.
"""
from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import unicodedata


@dataclasses.dataclass(frozen=True)
class Action:
    action_id: str
    label: str
    executable: str            # relative to %SystemRoot%\System32
    images: tuple[str, ...]    # process image names that prove it opened
    targets: tuple[str, ...]   # normalised phrases that name it


ACTIONS = {
    "notepad": Action("notepad", "o Bloco de Notas", "notepad.exe",
                      ("notepad.exe",), ("bloco de notas", "bloco-notas", "notepad")),
    # On Windows 10/11 calc.exe is a launcher that exits and starts the
    # packaged CalculatorApp.exe; older systems keep calc.exe/win32calc.exe.
    "calculator": Action("calculator", "a Calculadora", "calc.exe",
                         ("calculatorapp.exe", "calc.exe", "win32calc.exe"),
                         ("calculadora", "calculator")),
}

_REQUEST_VERBS = re.compile(
    r"\b(abre|abra|abrir|abram|abras|lanca|lancar|lance|inicia|iniciar|inicie|"
    r"executa|executar|execute|arranca|arrancar)\b")
_NEGATION = re.compile(r"\b(nao|nunca|jamais|nem)\b")
_YES = {"sim", "confirmo", "confirmar", "afirmativo", "claro"}


def normalise(text: str) -> str:
    """Lower-case, strip accents and punctuation (speech output varies)."""
    text = unicodedata.normalize("NFKD", text or "").lower()
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s-]", " ", text).split())


def detect_actions(text: str) -> list[str]:
    """Return action ids explicitly requested in ``text``.

    "Abre o Bloco de Notas" -> ["notepad"]; "Já abriste o Bloco de Notas?"
    or "Não abras a calculadora" -> [] (no request verb / negation).
    """
    norm = normalise(text)
    if not _REQUEST_VERBS.search(norm) or _NEGATION.search(norm):
        return []
    return [a.action_id for a in ACTIONS.values()
            if any(re.search(rf"\b{re.escape(t)}\b", norm) for t in a.targets)]


def is_confirmation(answer: str | None) -> bool:
    """Only an explicit, non-negated "sim"/"confirmo" confirms; all else cancels."""
    norm = normalise(answer or "")
    if not norm or _NEGATION.search(norm):
        return False
    return norm.split()[0] in _YES


class ActionError(RuntimeError):
    """The action could not be executed (blocked or failed)."""


@dataclasses.dataclass
class ActionResult:
    action_id: str
    outcome: str               # VERIFIED | NOT_VERIFIED | FAILED | BLOCKED | CANCELLED | REFUSED
    pid: int | None = None
    detail: str = ""

    @property
    def verified(self) -> bool:
        return self.outcome == "VERIFIED"


def _running_pids(images: tuple[str, ...], runner=subprocess.run) -> set[int]:
    """PIDs of running processes with one of ``images`` (Windows tasklist)."""
    proc = runner(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                  text=True, timeout=15, check=False)
    pids = set()
    for row in csv.reader(io.StringIO(proc.stdout or "")):
        if len(row) >= 2 and row[0].strip().lower() in images:
            try:
                pids.add(int(row[1]))
            except ValueError:
                pass
    return pids


class WindowsActions:
    """Executes allow-listed actions with authorization, confirmation and audit."""

    def __init__(self, *, authorized: bool, audit_dir: Path,
                 is_windows: bool | None = None, system_root: str | None = None,
                 popen=subprocess.Popen, runner=subprocess.run,
                 verify_seconds: float = 6.0, sleep=time.sleep):
        self.authorized = authorized
        self.audit_dir = Path(audit_dir)
        self.is_windows = os.name == "nt" if is_windows is None else is_windows
        self.system_root = system_root or os.environ.get("SystemRoot", r"C:\Windows")
        self._popen, self._runner = popen, runner
        self._verify_seconds, self._sleep = verify_seconds, sleep

    def executable_path(self, action: Action) -> str:
        return str(Path(self.system_root) / "System32" / action.executable)

    def audit(self, result: ActionResult, *, confirmed: bool) -> None:
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        day = dt.datetime.now(dt.timezone.utc)
        record = {"utc": day.isoformat(), "action": result.action_id,
                  "authorized": self.authorized, "confirmed": confirmed,
                  "outcome": result.outcome, "pid": result.pid,
                  "detail": result.detail[:200]}
        path = self.audit_dir / f"actions-{day:%Y%m%d}.jsonl"
        with path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run(self, action_id: str, confirm) -> ActionResult:
        """``confirm(question) -> answer text`` is asked only when authorized."""
        action = ACTIONS[action_id]
        confirmed = False
        if not self.authorized:
            result = ActionResult(action_id, "REFUSED",
                                  detail="session started without --allow-actions")
        else:
            try:
                answer = confirm(f"Queres que eu abra {action.label}? Responde sim ou não.")
            except KeyboardInterrupt:
                answer = None
            confirmed = is_confirmation(answer)
            if not confirmed:
                result = ActionResult(action_id, "CANCELLED", detail="not confirmed")
            else:
                result = self._execute(action)
        self.audit(result, confirmed=confirmed)
        return result

    def _execute(self, action: Action) -> ActionResult:
        if not self.is_windows:
            return ActionResult(action.action_id, "BLOCKED", detail="not a Windows host")
        path = self.executable_path(action)
        if not Path(path).is_file():
            return ActionResult(action.action_id, "FAILED", detail=f"missing {path}")
        try:
            before = _running_pids(action.images, self._runner)
            self._popen([path], shell=False, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        close_fds=True)
        except (OSError, subprocess.SubprocessError) as exc:
            return ActionResult(action.action_id, "FAILED", detail=type(exc).__name__ + ": " + str(exc))
        # A new PID must still be running on a second observation: calc.exe is
        # a launcher that exits at once and hands over to CalculatorApp.exe /
        # win32calc.exe (seen on the Windows CI runner), so a transient PID is
        # not proof that the application opened.
        deadline = self._verify_seconds
        while deadline > 0:
            new = _running_pids(action.images, self._runner) - before
            if new:
                self._sleep(0.5)
                deadline -= 0.5
                stable = new & _running_pids(action.images, self._runner)
                if stable:
                    return ActionResult(action.action_id, "VERIFIED", pid=min(stable))
                continue
            self._sleep(0.5)
            deadline -= 0.5
        return ActionResult(action.action_id, "NOT_VERIFIED",
                            detail="started, but no new process was observed")


def describe(result: ActionResult) -> str:
    """User-facing Portuguese text, derived only from the verified outcome."""
    label = ACTIONS[result.action_id].label
    return {
        "VERIFIED": f"Abri {label}. Confirmei que o processo está em execução.",
        "NOT_VERIFIED": f"Pedi ao Windows para abrir {label}, mas não consegui confirmar que abriu.",
        "FAILED": f"Não consegui abrir {label}: {result.detail}.",
        "BLOCKED": f"Não abri {label}: esta máquina não é Windows.",
        "CANCELLED": f"Cancelado. Não abri {label}.",
        "REFUSED": (f"Não abri {label}: as acções Windows não estão autorizadas nesta sessão. "
                    "Reinicia o Jarvis com --allow-actions para as autorizar."),
    }[result.outcome]
