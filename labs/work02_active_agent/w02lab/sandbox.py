"""Path-safe file access confined to sandbox/input (read) and sandbox/output (write).

Every name is a SIMPLE file name chosen by the model. It is rejected unless it
matches a strict ASCII pattern, so separators, '..', drives, UNC, '~' (8.3),
alternate data streams (':'), unicode homoglyphs and whitespace are impossible
by construction. Reserved Windows device names are rejected. The resolved real
path is checked before and after opening; symlinks/junctions/reparse points and
non-regular files are refused; on POSIX the open uses O_NOFOLLOW and the inode
is compared with the pre-open lstat (TOCTOU).
"""
from __future__ import annotations

import errno
import os
from pathlib import Path
import re
import stat
import uuid

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,58}\.(txt|md)$")
REPORT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,58}\.md$")
RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
            *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_READ_BYTES = 20_000
MAX_WRITE_BYTES = 20_000
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class SandboxError(ValueError):
    """Request refused by the sandbox. Message never contains internal paths."""


def check_name(name, *, report: bool = False) -> str:
    if not isinstance(name, str):
        raise SandboxError("nome inválido: tem de ser texto")
    pattern = REPORT_RE if report else NAME_RE
    if not pattern.fullmatch(name):
        raise SandboxError("nome inválido: usa apenas um nome simples (letras, números, _ ou -) "
                           + ("terminado em .md" if report else "terminado em .txt ou .md"))
    if name.split(".")[0].upper() in RESERVED:
        raise SandboxError("nome reservado do Windows")
    return name


def _is_link_or_reparse(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & _REPARSE)


class Sandbox:
    def __init__(self, sandbox_root: Path):
        self.root = Path(os.path.realpath(sandbox_root))
        self.input_dir = self.root / "input"
        self.output_dir = self.root / "output"
        self._staging = self.root / ".staging"
        for d in (self.input_dir, self.output_dir):
            if Path(os.path.realpath(d)) != d or _is_link_or_reparse(os.lstat(d)):
                raise SandboxError("directório do sandbox inválido")
        self.fault_hook = None   # tests: called between staging write and publish

    # -- helpers -----------------------------------------------------------
    def _inside(self, path: Path, directory: Path) -> bool:
        real = Path(os.path.realpath(path))
        return real.parent == directory

    def _exact_entry(self, directory: Path, name: str) -> bool:
        """Case-sensitive match against the real listing (case-insensitive FS)."""
        return name in os.listdir(directory)

    def list_input(self) -> list[str]:
        names = []
        for entry in sorted(os.listdir(self.input_dir)):
            p = self.input_dir / entry
            st = os.lstat(p)
            if NAME_RE.fullmatch(entry) and stat.S_ISREG(st.st_mode) and not _is_link_or_reparse(st):
                names.append(entry)
        return names

    # -- read --------------------------------------------------------------
    def read(self, name: str) -> str:
        check_name(name)
        path = self.input_dir / name
        if not self._exact_entry(self.input_dir, name):
            raise SandboxError("documento não encontrado")
        before = os.lstat(path)
        if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
            raise SandboxError("só ficheiros regulares podem ser lidos")
        if not self._inside(path, self.input_dir):
            raise SandboxError("documento fora da pasta autorizada")
        if before.st_size > MAX_READ_BYTES:
            raise SandboxError("documento demasiado grande")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if (opened.st_ino, opened.st_dev) != (before.st_ino, before.st_dev) \
                    or not stat.S_ISREG(opened.st_mode):
                raise SandboxError("o documento mudou durante a leitura")
            data = os.read(fd, MAX_READ_BYTES + 1)
        finally:
            os.close(fd)
        if len(data) > MAX_READ_BYTES or not self._inside(path, self.input_dir):
            raise SandboxError("documento inválido")
        return data.decode("utf-8", errors="replace")

    # -- write (new file only, atomic publish) ----------------------------
    def write_new(self, name: str, content: str) -> tuple[str, int]:
        check_name(name, report=True)
        if not isinstance(content, str):
            raise SandboxError("conteúdo inválido")
        data = content.encode("utf-8")
        if not data.strip() or len(data) > MAX_WRITE_BYTES:
            raise SandboxError("conteúdo vazio ou demasiado grande")
        lowered = {n.lower() for n in os.listdir(self.output_dir)}
        if name.lower() in lowered:
            raise SandboxError("já existe um relatório com esse nome; não é permitido sobrescrever")
        self._staging.mkdir(exist_ok=True)
        tmp = self._staging / f"{uuid.uuid4().hex}.part"
        final = self.output_dir / name
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        try:
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            if self.fault_hook:
                self.fault_hook()
            try:
                os.link(tmp, final)          # atomic, fails if final exists
            except FileExistsError:
                raise SandboxError("já existe um relatório com esse nome; não é permitido sobrescrever")
            except OSError as exc:
                if exc.errno in (errno.EXDEV, errno.EPERM, errno.ENOTSUP):
                    raise SandboxError("não foi possível publicar o relatório") from None
                raise
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
        if not self._inside(final, self.output_dir):
            os.unlink(final)
            raise SandboxError("destino inválido")
        return name, len(data)

    def read_output(self, name: str) -> str:
        check_name(name, report=True)
        path = self.output_dir / name
        if not self._exact_entry(self.output_dir, name):
            raise SandboxError("relatório não encontrado")
        st = os.lstat(path)
        if _is_link_or_reparse(st) or not stat.S_ISREG(st.st_mode) or st.st_size > MAX_WRITE_BYTES:
            raise SandboxError("relatório inválido")
        return path.read_bytes().decode("utf-8", errors="replace")

    def output_files(self) -> list[str]:
        return sorted(os.listdir(self.output_dir))

    def staging_leftovers(self) -> list[str]:
        return sorted(os.listdir(self._staging)) if self._staging.exists() else []
