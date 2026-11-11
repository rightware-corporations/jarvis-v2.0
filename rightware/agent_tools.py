"""WORK-05-A: bounded product tool execution; no model or benchmark dependency.

This module does NOT wire OpenJarvis/Qwen into production. A future adapter may
feed proposed function calls to run_batch. Read content stays untrusted.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time

from rightware.windows_actions import ACTIONS, WindowsActions, describe

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,58}\.(?:txt|md)\Z")
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
_RESERVED.update(f"COM{i}" for i in range(1, 10))
_RESERVED.update(f"LPT{i}" for i in range(1, 10))
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_SCHEMAS = {"read_document": {"name": str},
            "open_windows_action": {"action_id": str}}
_MAX_READ = 20_000


class ToolDenied(RuntimeError):
    """A tool request cannot cross the authorization boundary."""


@dataclass(frozen=True)
class ToolOutcome:
    tool: str
    outcome: str
    verified: bool
    detail: str = ""
    payload: str = ""


def _digest(name: str, args: dict) -> str:
    data = json.dumps({"name": name, "args": args}, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _check_filename(name: str) -> None:
    if type(name) is not str or not _NAME.fullmatch(name):
        raise ToolDenied("nome de documento fora do esquema permitido")
    if name.split(".", 1)[0].upper() in _RESERVED:
        raise ToolDenied("nome reservado do sistema")


def _bad_entry(st: os.stat_result) -> bool:
    return (not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode)
            or bool(getattr(st, "st_file_attributes", 0) & _REPARSE))


def read_scoped_document(root: Path, name: str) -> tuple[str, str]:
    """Read a simple .txt/.md entry in a trusted, explicitly chosen directory.

    Reject links, reparse points, oversized files, and in-read identity changes.
    This is a bounded local reader, NOT unrestricted filesystem access.
    """
    _check_filename(name)
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ToolDenied("pasta autorizada não existe")
    path = root / name
    try:
        before = os.lstat(path)
        if _bad_entry(before) or before.st_size > _MAX_READ:
            raise ToolDenied("documento não regular ou acima do limite")
        if Path(os.path.realpath(path)).parent != root:
            raise ToolDenied("documento fora da pasta autorizada")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if _bad_entry(opened) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ToolDenied("identidade do documento mudou")
            data = os.read(fd, _MAX_READ + 1)
            after = os.fstat(fd)
            if (after.st_mtime_ns, after.st_size) != (opened.st_mtime_ns, opened.st_size):
                raise ToolDenied("documento alterado durante a leitura")
        finally:
            os.close(fd)
        if len(data) > _MAX_READ or Path(os.path.realpath(path)).parent != root:
            raise ToolDenied("leitura excedeu o escopo")
        return data.decode("utf-8", "strict"), hashlib.sha256(data).hexdigest()
    except (OSError, UnicodeError) as exc:
        raise ToolDenied("não foi possível ler o documento autorizado") from exc


def frame_untrusted(content: str) -> str:
    """Mark tool data as untrusted; never promote it to a system/user directive."""
    tag = secrets.token_hex(16)
    end = f"[END_UNTRUSTED_{tag}]"
    safe = content.replace(end, "[escaped end marker]")
    return f"[BEGIN_UNTRUSTED_{tag}]\n{safe}\n{end}"


class AgentToolRuntime:
    """Closed tool registry with preflight + single-use execution authorization.

    The caller must treat every returned payload as *tool data*, never as an
    instruction or a verified answer. No Qwen call occurs in this class.
    """

    def __init__(self, *, document_root: Path, audit_path: Path,
                 windows_actions: WindowsActions | None = None,
                 max_calls: int = 8, per_tool: dict | None = None,
                 deadline_seconds: float = 120.0, clock=time.monotonic):
        self.document_root = Path(document_root)
        self.audit_path = Path(audit_path)
        self.windows_actions = windows_actions
        self.max_calls = max_calls
        self.per_tool = dict(per_tool or {"read_document": 6, "open_windows_action": 2})
        self.deadline_seconds = deadline_seconds
        self._clock = clock
        self._started = clock()
        self._lock = threading.Lock()
        self.calls = 0
        self.counts: dict[str, int] = {}
        self._tickets: dict[str, str] = {}
        self.cancelled = False

    def _audit(self, name: str, args: dict, outcome: str) -> None:
        # Only a digest of potentially sensitive arguments; no text, paths or credentials.
        try:
            fingerprint = _digest(name, args) if type(name) is str and type(args) is dict else None
        except (TypeError, ValueError, OverflowError):
            fingerprint = None
        record = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "tool": name if type(name) is str and name in _SCHEMAS else "unknown",
                  "args_sha256": fingerprint,
                  "outcome": outcome}
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _validate(self, name: str, args: dict) -> None:
        if type(name) is not str or name not in _SCHEMAS or type(args) is not dict:
            raise ToolDenied("ferramenta ou argumentos fora da lista permitida")
        schema = _SCHEMAS[name]
        if set(args) != set(schema):
            raise ToolDenied("argumentos em falta ou inesperados")
        for key, expected in schema.items():
            if type(args[key]) is not expected:
                raise ToolDenied("tipo de argumento inválido")
        if name == "read_document":
            _check_filename(args["name"])
        else:
            if args["action_id"] not in ACTIONS:
                raise ToolDenied("acção Windows não autorizada")
            if self.windows_actions is None or not self.windows_actions.authorized:
                raise ToolDenied("acções Windows não autorizadas nesta sessão")

    def _live(self) -> None:
        if self.cancelled or self._clock() - self._started > self.deadline_seconds:
            raise ToolDenied("sessão cancelada ou prazo esgotado")

    def authorize_batch(self, calls: list[dict]) -> list[str]:
        """Fail-closed: validate the whole batch before issuing any tickets."""
        if type(calls) is not list or not 1 <= len(calls) <= 2:
            raise ToolDenied("lote inválido: máximo de duas ferramentas")
        with self._lock:
            self._live()
            staged: dict[str, int] = {}
            seen: set[str] = set()
            for call in calls:
                if type(call) is not dict or set(call) != {"name", "args"}:
                    raise ToolDenied("formato da chamada inválido")
                name, args = call["name"], call["args"]
                self._validate(name, args)
                signature = _digest(name, args)
                if signature in seen:
                    raise ToolDenied("chamadas duplicadas no lote")
                seen.add(signature)
                staged[name] = staged.get(name, 0) + 1
                if self.counts.get(name, 0) + staged[name] > self.per_tool.get(name, 0):
                    raise ToolDenied("quota da ferramenta esgotada")
            if self.calls + len(calls) > self.max_calls:
                raise ToolDenied("quota total de ferramentas esgotada")
            tokens = []
            for call in calls:
                token = secrets.token_hex(24)
                self._tickets[token] = _digest(call["name"], call["args"])
                tokens.append(token)
                self.counts[call["name"]] = self.counts.get(call["name"], 0) + 1
            self.calls += len(calls)
            return tokens

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True
            self._tickets.clear()

    def execute(self, ticket: str, name: str, args: dict, *, confirm=None) -> ToolOutcome:
        """Second gate: exact token/args match, single-use and deadline check."""
        with self._lock:
            approved = self._tickets.pop(ticket, None) if isinstance(ticket, str) else None
            try:
                self._live()
                self._validate(name, args)
                if approved is None or approved != _digest(name, args):
                    raise ToolDenied("autorização inexistente, alterada ou já utilizada")
            except (ToolDenied, TypeError, ValueError):
                try:
                    self._audit(name, args, "REFUSED")
                except OSError:
                    pass
                return ToolOutcome(str(name), "REFUSED", False, "autorização recusada")
            try:
                self._audit(name, args, "AUTHORIZED")
            except OSError:
                return ToolOutcome(str(name), "FAILED", False, "auditoria indisponível; nada executado")
        try:
            if name == "read_document":
                content, digest = read_scoped_document(self.document_root, args["name"])
                result = ToolOutcome(name, "OK", True,
                                     "documento lido, sha256=" + digest,
                                     frame_untrusted(content))
            elif name == "open_windows_action":
                # WindowsActions independently checks session authorization and prompts.
                reply = self.windows_actions.run(args["action_id"], confirm or (lambda _: "não"))
                result = ToolOutcome(name, reply.outcome,
                                     reply.verified, describe(reply))
            else:
                raise ToolDenied("ferramenta desconhecida")
        except (ToolDenied, OSError, ValueError):
            result = ToolOutcome(name, "FAILED", False, "operação não concluída")
        try:
            self._audit(name, args, result.outcome)
        except OSError:
            return ToolOutcome(name, "AUDIT_FAILED", False,
                               "resultado final sem auditoria; não afirmar conclusão")
        return result

    def run_batch(self, calls: list[dict], *, confirm=None) -> list[ToolOutcome]:
        try:
            tickets = self.authorize_batch(calls)
        except (ToolDenied, TypeError, ValueError):
            try:
                self._audit("<batch>", {}, "REFUSED")
            except OSError:
                pass
            return [ToolOutcome("batch", "REFUSED", False, "lote recusado")]
        return [self.execute(ticket, call["name"], call["args"], confirm=confirm)
                for ticket, call in zip(tickets, calls)]
