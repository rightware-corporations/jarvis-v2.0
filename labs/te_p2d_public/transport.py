"""JRV-TE-P2D Gateway-side fetcher for the supervised public egress (labs only).

``EgressFetcher.fetch(url, host_allowed)`` has the same contract as ``HttpxFetcher.fetch`` (returns a ``Page``
or raises ``WebRefused``) so the unchanged ``PublicBrowser`` can use it. It never opens a network connection
itself: it talks to the host egress service through ONE Unix socket. Every URL — the first one and every
redirect hop — is checked BEFORE it is sent: the browser's host allowlist (``host_allowed``) and the same pure
``EgressPolicy`` the egress service enforces again on its side (defence in depth). Body integrity: the
SHA-256 sent by the egress service must match the bytes received.
"""
from __future__ import annotations

import base64
import hashlib
import json
import socket
from urllib.parse import urljoin, urlsplit

from rightware.agent.web import MAX_REDIRECTS, MAX_TEXT_CHARS, Page, WebRefused, html_to_text

from labs.te_p2d_public.egress import ALLOWED_TYPES, EgressPolicy

MAX_REPLY = 3_000_000


def uds_request(path: str, url: str, timeout: float = 30.0) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
        s.sendall((json.dumps({"url": url}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_REPLY:
                raise WebRefused("resposta do egress demasiado grande")
    finally:
        s.close()
    return json.loads(buf or b"{}")


class EgressFetcher:
    def __init__(self, socket_path: str | None, policy: EgressPolicy | None = None, request=None):
        self.socket_path = socket_path
        self.policy = policy or EgressPolicy()
        self._request = request or (lambda url: uds_request(self.socket_path, url))
        self.backend = None
        self.hops: list[dict] = []

    def _scoped(self, url: str, host_allowed) -> str:
        host = (urlsplit(url).hostname or "").rstrip(".").lower() if isinstance(url, str) else ""
        if host_allowed is not None and (not host or not host_allowed(host)):
            raise WebRefused("servidor fora dos sites autorizados nesta tarefa")
        reason = self.policy.check(url)
        if reason:
            raise WebRefused(f"bloqueado pela política de egress ({reason})")
        return url

    def fetch(self, url: str, host_allowed=None) -> Page:
        requested = current = self._scoped(url, host_allowed)
        for _ in range(MAX_REDIRECTS + 1):
            try:
                reply = self._request(current)
            except (OSError, ValueError) as exc:
                raise WebRefused(f"transporte de egress indisponível ({type(exc).__name__})") from None
            self.hops.append({"url": current, "decision": reply.get("decision"), "status": reply.get("status")})
            if reply.get("decision") != "OK":
                raise WebRefused(f"recusado pelo egress ({str(reply.get('reason'))[:80]})")
            status = reply.get("status")
            if status in (301, 302, 303, 307, 308):
                current = self._scoped(urljoin(current, str(reply.get("location") or "")), host_allowed)
                continue
            ctype = reply.get("content_type")
            if ctype not in ALLOWED_TYPES:
                raise WebRefused(f"tipo de conteúdo não suportado ({ctype or 'desconhecido'})")
            body = base64.b64decode(reply.get("body_b64") or "")
            digest = hashlib.sha256(body).hexdigest()
            if digest != reply.get("sha256"):
                raise WebRefused("integridade do conteúdo do egress falhou")
            markup = body.decode(reply.get("encoding") or "utf-8", errors="replace")
            text = html_to_text(markup) if "html" in ctype else markup
            truncated = bool(reply.get("truncated"))
            if len(text) > MAX_TEXT_CHARS:
                text, truncated = text[:MAX_TEXT_CHARS], True
            return Page(requested, current, int(status), ctype, text, digest, truncated,
                        markup if "html" in ctype else "")
        raise WebRefused("demasiados redireccionamentos")
