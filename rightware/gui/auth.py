"""UI-02 (R-2): local authentication for the GUI process.

At start the server mints a random launch token (never logged) and writes the one-time login URL
``http://127.0.0.1:PORT/rw-login?t=<token>`` to ``.runtime/gui/session-url`` (mode 0600) and the terminal. Opening it
exchanges the token for a session cookie (``rw_session``: random id, HttpOnly, SameSite=Strict, Path=/). Every
API route requires a valid session; static assets of the original frontend are public (they contain no data).
Sessions live in memory only and die with the process. This authenticates the LOCAL operator's browser; it is not
an account system and does not replace TLS/authentication on a future private host (B6).
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
    def __init__(self, token: str | None = None):
        self.token = token or secrets.token_urlsafe(32)
        self._sessions: dict[str, float] = {}
        self._lock = threading.Lock()

    def login(self, presented: str) -> str | None:
        if not isinstance(presented, str) or not secrets.compare_digest(presented, self.token):
            return None
        sid = secrets.token_urlsafe(24)
        with self._lock:
            while len(self._sessions) >= MAX_SESSIONS:
                self._sessions.pop(min(self._sessions, key=self._sessions.get))
            self._sessions[sid] = time.time()
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
            return values[0] if values[0] in self._sessions else None

    @staticmethod
    def cookie_header(sid: str) -> bytes:
        return f"{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/".encode()

    def write_url(self, path: Path, port: int) -> str:
        url = f"http://127.0.0.1:{port}/rw-login?t={self.token}"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(url + "\n")
        return url
