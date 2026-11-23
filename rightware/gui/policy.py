"""UI-01: deny-by-default ENTRY layer in front of the original OpenJarvis application (pure ASGI, no deps).

Every HTTP request and every WebSocket handshake reaching the GUI process passes through ``PolicyApp`` FIRST.
Only an exact (method, canonical path) in ``ALLOW`` is dispatched; everything else is refused (HTTP 403 JSON /
WebSocket close 1008) and recorded in a sanitised audit log (method, path, decision, reason; never bodies,
queries or conversation text). Path canonicalisation is strict: the raw request path must be plain ASCII without
percent-encoding, ``//``, ``.``/``..`` segments, backslashes or a trailing slash — no variant is "normalised
into" an allowed route, it is refused. The Host header must be the loopback address the server is bound to
(DNS-rebinding guard) and a state-changing request carrying an Origin must come from that same origin.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

# Allowed surface. Target: "inner" = original OpenJarvis app (read-only routes), "bridge" = RIGHTWARE runtime.
ALLOW: dict[tuple[str, str], str] = {
    ("GET", "/health"): "inner",                    # engine health as reported by OpenJarvis (503 if Ollama down)
    ("GET", "/v1/info"): "inner",                   # engine / model / agent=None
    ("GET", "/v1/models"): "bridge",                # host-allowed models (∩ installed when Ollama answers)
    ("POST", "/v1/chat/completions"): "bridge",     # conversation + Control Plane commands (RIGHTWARE)
    ("GET", "/v1/analytics/identity"): "bridge",    # analytics forced OFF (no key, no host)
    ("POST", "/v1/analytics/preference"): "bridge", # only the "do not share" choice is accepted (no effect)
}
# SPA pages of the original frontend (App.tsx routes). They only serve index.html; their data routes stay denied.
SPA_PAGES = frozenset({"/", "/dashboard", "/settings", "/get-started", "/data-sources", "/agents", "/logs"})
_CANONICAL = re.compile(r"^/(?:[A-Za-z0-9_.@~:+-]+(?:/[A-Za-z0-9_.@~:+-]+)*)?$")
_MAX_LOG_PATH = 160
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml",
                 ".png": "image/png", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json",
                 ".woff2": "font/woff2", ".woff": "font/woff", ".txt": "text/plain; charset=utf-8",
                 ".map": "application/json"}
SECURITY_HEADERS = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"), (b"cache-control", b"no-store")]
# The browser itself may only talk to this origin: the original frontend's optional analytics (PostHog) and
# leaderboard (Supabase) calls are blocked even if a user opts in by mistake.
CSP = (b"default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       b"img-src 'self' data: blob:; font-src 'self' data:; worker-src 'self'; manifest-src 'self'; "
       b"object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


def canonical_path(scope: dict) -> str | None:
    """The request path if it is canonical, else None (refused, never normalised)."""
    raw = scope.get("raw_path")
    path = scope.get("path", "")
    if raw is not None:
        try:
            raw_s = bytes(raw).decode("ascii")
        except (UnicodeDecodeError, TypeError):
            return None
        if raw_s != path:                       # any percent-encoding or decoding difference
            return None
    if "%" in path or "\\" in path or "//" in path:
        return None
    if path != "/" and path.endswith("/"):
        return None
    if any(seg in (".", "..") for seg in path.split("/")):
        return None
    if not _CANONICAL.fullmatch(path):
        return None
    return path


class AuditLog:
    """Append-only sanitised decision log (JSON lines). Thread-safe; failures to write never open the gate."""

    def __init__(self, path: Path | None):
        self.path, self._lock, self.failures = path, threading.Lock(), 0
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, kind: str, method: str, path: str, decision: str, reason: str, **extra) -> None:
        row = {"t": round(time.time(), 3), "kind": kind, "method": method[:10],
               "path": (path or "")[:_MAX_LOG_PATH].encode("ascii", "replace").decode(), "decision": decision,
               "reason": reason, **{k: v for k, v in extra.items() if isinstance(v, (str, int, float, bool))}}
        if self.path is None:
            return
        try:
            with self._lock, self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
        except OSError:
            self.failures += 1


async def send_json(send, status: int, payload: dict, extra_headers=()) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            *SECURITY_HEADERS, *extra_headers]})
    await send({"type": "http.response.body", "body": body})


class PolicyApp:
    """Outermost ASGI app: deny-by-default router for the GUI process."""

    def __init__(self, *, inner, bridge, static_dir: Path | None, port: int, audit: AuditLog,
                 allow: dict | None = None):
        self.inner, self.bridge, self.port, self.audit = inner, bridge, port, audit
        self.allow = dict(ALLOW if allow is None else allow)
        self.hosts = {f"127.0.0.1:{port}".encode(), f"localhost:{port}".encode()}
        self.origins = {f"http://127.0.0.1:{port}".encode(), f"http://localhost:{port}".encode()}
        self.static: dict[str, Path] = {}
        if static_dir is not None and static_dir.is_dir():
            root = static_dir.resolve()
            for p in sorted(root.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    rel = "/" + p.relative_to(root).as_posix()
                    if _CANONICAL.fullmatch(rel) and p.resolve().is_relative_to(root):
                        self.static[rel] = p

    def _headers(self, scope) -> dict[bytes, bytes]:
        h: dict[bytes, bytes] = {}
        for k, v in scope.get("headers") or []:
            k = bytes(k).lower()
            if k in h:                            # duplicated security-relevant header → ambiguous → refuse
                h[k] = b"\x00DUPLICATE"
            else:
                h[k] = bytes(v)
        return h

    def decide(self, scope) -> tuple[str, str]:
        """(target, reason). target in {"inner", "bridge", "static", "spa", "deny"}."""
        method = scope.get("method", "WS") if scope["type"] == "http" else "WS"
        path = canonical_path(scope)
        if path is None:
            return "deny", "NON_CANONICAL_PATH"
        headers = self._headers(scope)
        if headers.get(b"host") not in self.hosts:
            return "deny", "HOST_NOT_LOOPBACK"
        if scope["type"] == "websocket":
            return "deny", "WEBSOCKET_NOT_ALLOWED"
        origin = headers.get(b"origin")
        if method not in ("GET",) and origin is not None and origin not in self.origins:
            return "deny", "CROSS_ORIGIN"
        target = self.allow.get((method, path))
        if target:
            return target, "ALLOWLISTED"
        if method == "GET" and path in self.static:
            return "static", "STATIC_FILE"
        if method == "GET" and path in SPA_PAGES and "/index.html" in self.static:
            return "spa", "SPA_PAGE"
        return "deny", "NOT_IN_ALLOWLIST"

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind == "lifespan":
            return await self.inner(scope, receive, send)
        if kind not in ("http", "websocket"):
            return None
        method = scope.get("method", "WS") if kind == "http" else "WS"
        try:
            target, reason = self.decide(scope)
        except Exception:                          # policy error → fail closed
            target, reason = "deny", "POLICY_ERROR"
        path = scope.get("path", "")
        if target == "deny":
            self.audit.record(kind, method, path, "DENY", reason)
            if kind == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return None
            return await send_json(send, 403, {"error": "BLOQUEADO_PELA_POLITICA_RIGHTWARE", "reason": reason,
                                               "detail": "Esta função não está integrada no JARVIS (RIGHTWARE)."})
        if target in ("static", "spa"):
            file = self.static["/index.html" if target == "spa" else canonical_path(scope)]
            body = file.read_bytes()
            ctype = CONTENT_TYPES.get(file.suffix, "application/octet-stream").encode()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", ctype), (b"content-length", str(len(body)).encode()),
                                    (b"content-security-policy", CSP), *SECURITY_HEADERS]})
            await send({"type": "http.response.body", "body": body})
            return None
        self.audit.record(kind, method, path, "ALLOW", reason, target=target)
        app = self.inner if target == "inner" else self.bridge
        return await app(scope, receive, send)
