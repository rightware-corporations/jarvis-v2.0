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
    # UI-02: RIGHTWARE HUD state and missions (the SAME ControlPlane; authorisation only by operator code)
    ("GET", "/v1/rightware/state"): "bridge",
    ("POST", "/v1/rightware/tasks/request"): "bridge",
    ("POST", "/v1/rightware/tasks/authorize"): "bridge",
    ("POST", "/v1/rightware/tasks/cancel"): "bridge",
}
# VOICE (opt-in, only when the host started with --voz): the UPSTREAM speech routes, local STT/TTS. Each POST has a
# hard body cap (Content-Length required) enforced here, before the upstream handler reads the body.
VOICE_ALLOW: dict[tuple[str, str], str] = {
    ("GET", "/v1/speech/health"): "inner",
    ("GET", "/v1/speech/tts/health"): "inner",
    ("POST", "/v1/speech/transcribe"): "inner",
    ("POST", "/v1/speech/synthesize"): "inner",
}
# JRV-INT01 (K01 gateway contract, approved): document routes, only when the host started with documents enabled.
DOCUMENT_ALLOW: dict[tuple[str, str], str] = {
    ("POST", "/v1/rightware/documents/upload"): "bridge",
    ("GET", "/v1/rightware/documents"): "bridge",
    ("POST", "/v1/rightware/documents/delete"): "bridge",
}
# JRV-INT01: minimal personal-memory screen (list / correct with the user's own typed words / delete), only when the
# host started with memory enabled.
MEMORY_ALLOW: dict[tuple[str, str], str] = {
    ("GET", "/v1/rightware/memory"): "bridge",
    ("POST", "/v1/rightware/memory/correct"): "bridge",
    ("POST", "/v1/rightware/memory/delete"): "bridge",
}
BODY_LIMITS = {"/v1/speech/transcribe": 5 * 1024 * 1024, "/v1/speech/synthesize": 16 * 1024,
               "/v1/rightware/documents/upload": 5 * 1024 * 1024, "/v1/rightware/documents/delete": 1024,
               "/v1/rightware/memory/correct": 2048, "/v1/rightware/memory/delete": 1024, "/rw-login": 1024}
LOGIN_PATH = "/rw-login"
LOGIN_REQUIRED_HTML = (
    "<!doctype html><html lang=\"pt\"><head><meta charset=\"utf-8\"><title>JARVIS — sessão local</title></head>"
    "<body style=\"font-family:system-ui;background:#05070d;color:#cfe8ff;padding:3rem\"><h1>JARVIS</h1>"
    "<p>Sessão local necessária. Abra a ligação de início de sessão mostrada no terminal do anfitrião "
    "(também em <code>.runtime/gui/session-url</code>).</p><p lang=\"en\">Local session required: open the login "
    "link printed by the host.</p></body></html>").encode()
# ID01-A: confirmation page for a private-access link (GET never consumes the link). No script, no external resource.
CONFIRM_HTML = (
    "<!doctype html><html lang=\"pt\"><head><meta charset=\"utf-8\"><title>JARVIS — confirmar entrada</title>"
    "</head><body style=\"font-family:system-ui;background:#05070d;color:#cfe8ff;padding:3rem\"><h1>JARVIS</h1>"
    "<p>Ligação de acesso privado válida. Confirme para entrar; a ligação só pode ser usada uma vez.</p>"
    "<form method=\"post\" action=\"/rw-login\"><input type=\"hidden\" name=\"csrf\" value=\"{csrf}\">"
    "<button type=\"submit\" style=\"font-size:1.1rem;padding:.6rem 1.4rem\">Entrar no JARVIS</button></form>"
    "<p lang=\"en\">Valid private link. Confirm to sign in; the link works once.</p></body></html>")
# A native form POST is a navigation: with "Referrer-Policy: no-referrer" the browser sends "Origin: null" (Fetch
# standard, origin serialisation), which the exact-Origin check correctly refuses (the CROSS_ORIGIN seen in the
# Manus repair). The confirmation page alone uses "strict-origin" (origin only, never path/query/token) so the
# POST carries the real Origin; "null" is still refused.
CONFIRM_HEADERS = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"strict-origin"),
                   (b"x-frame-options", b"DENY"), (b"cache-control", b"no-store")]
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
       b"img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; worker-src 'self'; manifest-src 'self'; "
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

    def __init__(self, path: Path | None, max_bytes: int = 5 * 1024 * 1024, keep: int = 3):
        self.path, self._lock, self.failures = path, threading.Lock(), 0
        self.max_bytes, self.keep = max_bytes, keep                 # UI-02 (R-10): size-based rotation
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, kind: str, method: str, path: str, decision: str, reason: str, **extra) -> None:
        row = {"t": round(time.time(), 3), "kind": kind, "method": method[:10],
               "path": (path or "")[:_MAX_LOG_PATH].encode("ascii", "replace").decode(), "decision": decision,
               "reason": reason, **{k: v for k, v in extra.items() if isinstance(v, (str, int, float, bool))}}
        if self.path is None:
            return
        try:
            with self._lock:
                if self.path.exists() and self.path.stat().st_size >= self.max_bytes:
                    for i in range(self.keep - 1, 0, -1):
                        older = self.path.with_name(f"{self.path.name}.{i}")
                        if older.exists():
                            older.replace(self.path.with_name(f"{self.path.name}.{i + 1}"))
                    self.path.replace(self.path.with_name(f"{self.path.name}.1"))
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=True) + "\n")
        except OSError:
            self.failures += 1


async def send_json(send, status: int, payload: dict, extra_headers=()) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            *SECURITY_HEADERS, *extra_headers]})
    await send({"type": "http.response.body", "body": body})


PUBLIC_ORIGIN_RE = re.compile(r"https://([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)")


def parse_public_origin(origin: str) -> tuple[bytes, bytes]:
    """B6: exactly one HTTPS origin, no port, path, query, user info or wildcard. Returns (origin, host)."""
    if not isinstance(origin, str) or not PUBLIC_ORIGIN_RE.fullmatch(origin):
        raise ValueError("public origin must be exactly https://<lowercase-host> (no port, path or wildcard)")
    host = origin[len("https://"):]
    if host in ("localhost",) or host.endswith((".localhost", ".local")):
        raise ValueError("public origin must not be a local name")
    return origin.encode(), host.encode()


class PolicyApp:
    """Outermost ASGI app: deny-by-default router for the GUI process.

    B6 private-access mode (``public_origin`` set, for a temporary authenticated tunnel that forwards to this
    loopback server): the strict rules apply to EVERY request, whatever Host the relay forwards — the Host must be
    loopback or the public host; every route (static bundle files included) needs a session, except the login
    link; a state-changing request must carry ``Origin`` equal to the public origin; the session cookie is Secure;
    and after ``public_until`` every request is refused and all sessions are revoked (a real time limit)."""

    def __init__(self, *, inner, bridge, static_dir: Path | None, port: int, audit: AuditLog, auth,
                 allow: dict | None = None, public_origin: str | None = None, public_until: float | None = None,
                 clock=time.time):
        """``auth``: a ``LocalAuth`` (UI-02, required in the product); ``None`` only in unit tests of routing."""
        self.inner, self.bridge, self.port, self.audit, self.auth = inner, bridge, port, audit, auth
        self.allow = dict(ALLOW if allow is None else allow)
        self.hosts = {f"127.0.0.1:{port}".encode(), f"localhost:{port}".encode()}
        self.origins = {f"http://127.0.0.1:{port}".encode(), f"http://localhost:{port}".encode()}
        self.public = public_origin is not None
        self.clock, self.public_until, self._expired = clock, public_until, False
        if self.public:
            if auth is None or public_until is None:
                raise ValueError("private-access mode needs authentication and an expiry")
            self.public_origin, self.public_host = parse_public_origin(public_origin)
            self.hosts = self.hosts | {self.public_host}
            self.origins = {self.public_origin}
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
        if self.public and self.clock() > self.public_until:
            if not self._expired:
                self._expired = True
                self.auth.revoke_all()
            return "deny", "PUBLIC_ACCESS_EXPIRED"
        if headers.get(b"host") not in self.hosts:
            return "deny", "HOST_NOT_LOOPBACK"
        if scope["type"] == "websocket":
            return "deny", "WEBSOCKET_NOT_ALLOWED"
        origin = headers.get(b"origin")
        if method not in ("GET",) and origin is not None and origin not in self.origins:
            return "deny", "CROSS_ORIGIN"
        if self.public and method not in ("GET",) and origin is None:
            return "deny", "ORIGIN_REQUIRED"
        if method == "GET" and path == LOGIN_PATH and self.auth is not None:
            return "login", "LOGIN"
        if method == "POST" and path == LOGIN_PATH and self.auth is not None and self.public:
            return "login_post", "LOGIN_CONFIRM"
        target = self.allow.get((method, path))
        if not target and method == "GET" and path in self.static and path != "/index.html":
            if not self.public:
                return "static", "STATIC_FILE"              # local mode: bundle files are public, no data
            target = "static"                               # private-access mode: session required
        if not target and method == "GET" and (path in SPA_PAGES or path == "/index.html") \
                and "/index.html" in self.static:
            target = "spa"
        if not target:
            return "deny", "NOT_IN_ALLOWLIST"
        if self.auth is not None:
            sid = self.auth.session_from_cookie(headers.get(b"cookie"))
            if sid is None:
                return ("login_page" if target == "spa" else "unauth"), "AUTH_REQUIRED"
            scope["rightware.session"] = sid
            scope["rightware.owner"] = self.auth.owner_of(sid) if hasattr(self.auth, "owner_of") else None
        if target == "static":
            return "static", "STATIC_FILE_SESSION"
        return target, ("SPA_PAGE" if target == "spa" else "ALLOWLISTED")

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
        if target == "login_post":
            return await self._login_post(scope, receive, send, kind, method, path)
        if target in ("login", "login_page", "unauth"):
            return await self._auth_response(target, scope, send, kind, method, path)
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
        limit = BODY_LIMITS.get(path) if kind == "http" and method == "POST" else None
        if limit is not None:
            headers = dict((bytes(k).lower(), bytes(v)) for k, v in scope.get("headers") or [])
            size = headers.get(b"content-length", b"")
            if not size.isdigit() or int(size) > limit:
                self.audit.record(kind, method, path, "DENY", "BODY_TOO_LARGE_OR_UNSIZED")
                return await send_json(send, 413, {"error": "BLOQUEADO_PELA_POLITICA_RIGHTWARE",
                                                   "reason": "BODY_TOO_LARGE_OR_UNSIZED"})
        self.audit.record(kind, method, path, "ALLOW", reason, target=target)
        app = self.inner if target == "inner" else self.bridge
        return await app(scope, receive, send)

    async def _login_post(self, scope, receive, send, kind, method, path):
        """ID01-A explicit confirmation: exact Origin was already enforced by ``decide`` (null is refused there);
        challenge cookie + CSRF + expiry → atomic one-time consumption of the link."""
        headers = self._headers(scope)
        size = headers.get(b"content-length", b"")
        ctype = headers.get(b"content-type", b"").split(b";")[0].strip()
        body = b""
        if size.isdigit() and int(size) <= BODY_LIMITS[LOGIN_PATH] and ctype == b"application/x-www-form-urlencoded":
            while True:
                msg = await receive()
                body += msg.get("body", b"")
                if len(body) > BODY_LIMITS[LOGIN_PATH] or not msg.get("more_body"):
                    break
        from urllib.parse import parse_qs
        form = parse_qs(body.decode("ascii", "replace")) if len(body) <= BODY_LIMITS[LOGIN_PATH] else {}
        csrf = form.get("csrf", [None])
        cid = self.auth.cookie_value(headers.get(b"cookie"), "rw_challenge")
        sid = self.auth.redeem(cid, csrf[0] if len(csrf) == 1 else None)
        self.audit.record(kind, method, path, "LOGIN_OK" if sid else "DENY", "LOGIN" if sid else "BAD_CHALLENGE")
        if sid is None:
            return await send_json(send, 403, {"error": "LIGACAO_DE_SESSAO_INVALIDA"},
                                   [(b"set-cookie", self.auth.clear_challenge_cookie(True))])
        await send({"type": "http.response.start", "status": 303,
                    "headers": [(b"location", b"/"), (b"set-cookie", self.auth.clear_challenge_cookie(True)),
                                (b"set-cookie", self.auth.cookie_header(sid, secure=True)),
                                (b"content-length", b"0"), *SECURITY_HEADERS]})
        return await send({"type": "http.response.body", "body": b""})

    async def _auth_response(self, target, scope, send, kind, method, path):
        if target == "unauth":
            self.audit.record(kind, method, path, "DENY", "AUTH_REQUIRED")
            return await send_json(send, 401, {"error": "SESSAO_LOCAL_NECESSARIA", "reason": "AUTH_REQUIRED"})
        if target == "login":
            query = bytes(scope.get("query_string") or b"").decode("ascii", "replace")
            token = [p[2:] for p in query.split("&") if p.startswith("t=")]
            if self.public and hasattr(self.auth, "challenge"):
                # ID01-A: GET shows a confirmation; the link is consumed only by the explicit POST.
                pair = self.auth.challenge(token[0]) if len(token) == 1 else None
                self.audit.record(kind, method, path, "CONFIRM" if pair else "DENY",
                                  "LOGIN_CONFIRM_PAGE" if pair else "BAD_TOKEN")
                if pair is None:
                    return await send_json(send, 403, {"error": "LIGACAO_DE_SESSAO_INVALIDA"})
                body = CONFIRM_HTML.replace("{csrf}", pair[1]).encode()
                await send({"type": "http.response.start", "status": 200,
                            "headers": [(b"content-type", b"text/html; charset=utf-8"),
                                        (b"content-length", str(len(body)).encode()),
                                        (b"set-cookie", self.auth.challenge_cookie(pair[0], secure=True)),
                                        (b"content-security-policy", CSP), *CONFIRM_HEADERS]})
                return await send({"type": "http.response.body", "body": body})
            sid = self.auth.login(token[0]) if len(token) == 1 else None
            self.audit.record(kind, method, path, "LOGIN_OK" if sid else "DENY", "LOGIN" if sid else "BAD_TOKEN")
            if sid is None:
                return await send_json(send, 403, {"error": "LIGACAO_DE_SESSAO_INVALIDA"})
            await send({"type": "http.response.start", "status": 303,
                        "headers": [(b"location", b"/"), (b"set-cookie", self.auth.cookie_header(sid, secure=self.public)),
                                    (b"content-length", b"0"), *SECURITY_HEADERS]})
            return await send({"type": "http.response.body", "body": b""})
        self.audit.record(kind, method, path, "DENY", "AUTH_REQUIRED")
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"text/html; charset=utf-8"),
                                (b"content-length", str(len(LOGIN_REQUIRED_HTML)).encode()),
                                (b"content-security-policy", CSP), *SECURITY_HEADERS]})
        return await send({"type": "http.response.body", "body": LOGIN_REQUIRED_HTML})
