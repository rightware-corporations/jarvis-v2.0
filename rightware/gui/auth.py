"""UI-02 (R-2): local authentication for the GUI process.

At start the server mints a random launch token (never logged) and writes the one-time login URL
``http://127.0.0.1:PORT/rw-login?t=<token>`` to ``.runtime/gui/session-url`` (mode 0600) and the terminal. Opening it
exchanges the token for a session cookie (``rw_session``: random id, HttpOnly, SameSite=Strict, Path=/). Every
API route requires a valid session; static assets of the original frontend are public (they contain no data).
Sessions live in memory only and die with the process. This authenticates the LOCAL operator's browser; it is not
an account system. B6 adds a private-access mode (single-use, expiring link; expiring sessions; Secure cookie)
for a temporary authenticated tunnel; see rightware/gui/policy.py (public origin).
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from pathlib import Path

COOKIE = "rw_session"
MAX_SESSIONS = 16


class LocalAuth:
    """Local mode (defaults): reusable launch token, sessions until the process ends (UI-02 behaviour).
    B6 private-access mode (``single_use=True``): the token works ONCE and only within ``token_ttl`` seconds,
    sessions expire after ``session_ttl`` seconds, and after ``max_failures`` bad tokens every login is refused
    (fail-closed; restarting the host mints a new token). ``revoke_all`` ends every session at once."""

    def __init__(self, token: str | None = None, *, single_use: bool = False, token_ttl: float | None = None,
                 session_ttl: float | None = None, max_failures: int | None = None, clock=time.time):
        self.token = token or secrets.token_urlsafe(32)
        self.single_use, self.token_ttl, self.session_ttl = single_use, token_ttl, session_ttl
        self.max_failures, self.clock = max_failures, clock
        self.minted = clock()
        self.consumed = False
        self.failures = 0
        self._sessions: dict[str, float] = {}
        self._lock = threading.Lock()

    def login(self, presented: str) -> str | None:
        with self._lock:
            if self.max_failures is not None and self.failures >= self.max_failures:
                return None                                  # locked: too many bad tokens
            ok = isinstance(presented, str) and secrets.compare_digest(presented, self.token)
            if ok and self.single_use and self.consumed:
                ok = False                                   # replay of a used link
            if ok and self.token_ttl is not None and self.clock() - self.minted > self.token_ttl:
                ok = False                                   # expired link
            if not ok:
                self.failures += 1
                return None
            if self.single_use:
                self.consumed = True
            sid = secrets.token_urlsafe(24)
            while len(self._sessions) >= MAX_SESSIONS:
                self._sessions.pop(min(self._sessions, key=self._sessions.get))
            self._sessions[sid] = self.clock()
            return sid

    def session_from_cookie(self, header: bytes | None) -> str | None:
        if not header:
            return None
        try:
            text = header.decode("ascii")
        except UnicodeDecodeError:
            return None
        values = [p.strip()[len(COOKIE) + 1:] for p in text.split(";") if p.strip().startswith(COOKIE + "=")]
        if len(values) != 1:                       # missing or ambiguous cookie → not authenticated
            return None
        with self._lock:
            born = self._sessions.get(values[0])
            if born is None:
                return None
            if self.session_ttl is not None and self.clock() - born > self.session_ttl:
                self._sessions.pop(values[0], None)
                return None
            return values[0]

    def revoke_all(self) -> int:
        with self._lock:
            n = len(self._sessions)
            self._sessions.clear()
            self.consumed = True
            return n

    def cookie_header(self, sid: str, secure: bool = False) -> bytes:
        attrs = f"{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/"
        if self.session_ttl is not None:
            attrs += f"; Max-Age={int(self.session_ttl)}"
        return (attrs + ("; Secure" if secure else "")).encode()

    def write_url(self, path: Path, port: int, base: str | None = None) -> str:
        url = f"{base or f'http://127.0.0.1:{port}'}/rw-login?t={self.token}"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(url + "\n")
        os.chmod(path, 0o600)
        return url
