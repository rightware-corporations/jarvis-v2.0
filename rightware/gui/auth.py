"""UI-02 (R-2): local authentication for the GUI process.

At start the server mints a random launch token (never logged) and writes the one-time login URL
``http://127.0.0.1:PORT/rw-login?t=<token>`` to ``.runtime/gui/session-url`` (mode 0600) and the terminal. Opening it
exchanges the token for a session cookie (``rw_session``: random id, HttpOnly, SameSite=Strict, Path=/). Every
API route requires a valid session; static assets of the original frontend are public (they contain no data).
Sessions live in memory only and die with the process. This authenticates the LOCAL operator's browser; it is not
an account system. B6 adds a private-access mode (single-use, expiring link; expiring sessions; Secure cookie)
for a temporary authenticated tunnel; see rightware/gui/policy.py (public origin).

JRV-INT01 (ID01-A reproduction + identity):
* In private-access mode the link is NOT consumed by GET: GET only shows a confirmation page and creates a short-lived
  challenge (random id in an HttpOnly/Secure/SameSite=Strict cookie scoped to /rw-login + a CSRF value in the form).
  The explicit POST (exact Origin, matching challenge + CSRF, within the expiry) consumes the token ATOMICALLY.
  Link previews/prefetch/scanners that only GET cannot burn the link; a replayed POST or challenge fails.
* Each link may be issued for a server-declared OWNER (stable identity, e.g. ``lab:operador``); the session inherits
  it. The browser never chooses the owner. Sessions without an owner get no personal memory/documents.
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from pathlib import Path

COOKIE = "rw_session"
CHALLENGE_COOKIE = "rw_challenge"
MAX_SESSIONS = 16
MAX_CHALLENGES = 16
CHALLENGE_TTL = 300.0


class LocalAuth:
    """Local mode (defaults): reusable launch token, sessions until the process ends (UI-02 behaviour).
    B6 private-access mode (``single_use=True``): the token works ONCE and only within ``token_ttl`` seconds,
    sessions expire after ``session_ttl`` seconds, and after ``max_failures`` bad tokens every login is refused
    (fail-closed; restarting the host mints a new token). ``revoke_all`` ends every session at once."""

    def __init__(self, token: str | None = None, *, single_use: bool = False, token_ttl: float | None = None,
                 session_ttl: float | None = None, max_failures: int | None = None, clock=time.time,
                 owner: str | None = None, label: str = "principal"):
        self.token = token or secrets.token_urlsafe(32)
        self.single_use, self.token_ttl, self.session_ttl = single_use, token_ttl, session_ttl
        self.max_failures, self.clock = max_failures, clock
        self.minted = clock()
        self.failures = 0
        # token → {owner, label, minted, ttl, consumed}; the launch token is the first link
        self._links: dict[str, dict] = {self.token: {"owner": owner, "label": label, "minted": self.minted,
                                                     "ttl": token_ttl, "consumed": False}}
        self._sessions: dict[str, tuple[float, str | None, str]] = {}      # sid → (born, owner, label)
        self._challenges: dict[str, tuple[str, str, float]] = {}            # cid → (token, csrf, created)
        self._lock = threading.Lock()

    @property
    def consumed(self) -> bool:                    # backwards compatible view of the launch link
        return self._links[self.token]["consumed"]

    def issue(self, owner: str | None, label: str, ttl: float | None = None) -> str:
        """Mint an additional single-purpose link for a server-declared owner (e.g. Issa's own link)."""
        tok = secrets.token_urlsafe(32)
        with self._lock:
            self._links[tok] = {"owner": owner, "label": label, "minted": self.clock(),
                                "ttl": self.token_ttl if ttl is None else ttl, "consumed": False}
        return tok

    def _valid_locked(self, presented) -> dict | None:
        if not isinstance(presented, str):
            return None
        link = None
        for tok, info in self._links.items():
            if secrets.compare_digest(presented, tok):
                link = info
        if link is None:
            return None
        if self.single_use and link["consumed"]:
            return None                                      # replay of a used link
        if link["ttl"] is not None and self.clock() - link["minted"] > link["ttl"]:
            return None                                      # expired link
        return link

    def check(self, presented: str) -> bool:
        """Is the link currently usable? Never consumes it (GET confirmation page). Bad tokens count as failures."""
        with self._lock:
            if self.max_failures is not None and self.failures >= self.max_failures:
                return False
            ok = self._valid_locked(presented) is not None
            if not ok:
                self.failures += 1
            return ok

    def login(self, presented: str) -> str | None:
        with self._lock:
            if self.max_failures is not None and self.failures >= self.max_failures:
                return None                                  # locked: too many bad tokens
            link = self._valid_locked(presented)
            if link is None:
                self.failures += 1
                return None
            if self.single_use:
                link["consumed"] = True                      # atomic with the validity check (same lock)
            sid = secrets.token_urlsafe(24)
            while len(self._sessions) >= MAX_SESSIONS:
                self._sessions.pop(min(self._sessions, key=lambda k: self._sessions[k][0]))
            self._sessions[sid] = (self.clock(), link["owner"], link["label"])
            return sid

    # -- ID01-A: GET confirmation → explicit POST -----------------------------------------------------------------
    def challenge(self, presented: str) -> tuple[str, str] | None:
        """For a currently valid link: a fresh (challenge id, csrf) pair. The link is NOT consumed."""
        if not self.check(presented):
            return None
        cid, csrf = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        with self._lock:
            now = self.clock()
            for k in [k for k, v in self._challenges.items() if now - v[2] > CHALLENGE_TTL]:
                self._challenges.pop(k, None)
            while len(self._challenges) >= MAX_CHALLENGES:
                self._challenges.pop(min(self._challenges, key=lambda k: self._challenges[k][2]))
            self._challenges[cid] = (presented, csrf, now)
        return cid, csrf

    def redeem(self, cid: str | None, csrf: str | None) -> str | None:
        """Explicit POST: the challenge is single-use; CSRF must match; then the link is consumed atomically."""
        if not cid or not csrf:
            return None
        with self._lock:
            entry = self._challenges.pop(cid, None)
        if entry is None:
            return None
        token, want, created = entry
        if not secrets.compare_digest(csrf, want) or self.clock() - created > CHALLENGE_TTL:
            with self._lock:
                self.failures += 1
            return None
        return self.login(token)

    def owner_of(self, sid: str | None) -> str | None:
        with self._lock:
            s = self._sessions.get(sid or "")
            return s[1] if s else None

    @staticmethod
    def cookie_value(header: bytes | None, name: str) -> str | None:
        if not header:
            return None
        try:
            text = header.decode("ascii")
        except UnicodeDecodeError:
            return None
        values = [p.strip()[len(name) + 1:] for p in text.split(";") if p.strip().startswith(name + "=")]
        return values[0] if len(values) == 1 else None

    def challenge_cookie(self, cid: str, secure: bool) -> bytes:
        return (f"{CHALLENGE_COOKIE}={cid}; HttpOnly; SameSite=Strict; Path=/rw-login; Max-Age={int(CHALLENGE_TTL)}"
                + ("; Secure" if secure else "")).encode()

    @staticmethod
    def clear_challenge_cookie(secure: bool) -> bytes:
        return (f"{CHALLENGE_COOKIE}=; HttpOnly; SameSite=Strict; Path=/rw-login; Max-Age=0"
                + ("; Secure" if secure else "")).encode()

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
            entry = self._sessions.get(values[0])
            if entry is None:
                return None
            born = entry[0]
            if self.session_ttl is not None and self.clock() - born > self.session_ttl:
                self._sessions.pop(values[0], None)
                return None
            return values[0]

    def revoke_all(self) -> int:
        with self._lock:
            n = len(self._sessions)
            self._sessions.clear()
            self._challenges.clear()
            for link in self._links.values():
                link["consumed"] = True
            return n

    def cookie_header(self, sid: str, secure: bool = False) -> bytes:
        attrs = f"{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/"
        if self.session_ttl is not None:
            attrs += f"; Max-Age={int(self.session_ttl)}"
        return (attrs + ("; Secure" if secure else "")).encode()

    def write_url(self, path: Path, port: int, base: str | None = None, token: str | None = None) -> str:
        url = f"{base or f'http://127.0.0.1:{port}'}/rw-login?t={token or self.token}"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(url + "\n")
        os.chmod(path, 0o600)
        return url
