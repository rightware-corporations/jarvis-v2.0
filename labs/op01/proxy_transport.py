"""OP01-FX-REAL-PROXY — EXPERIMENTAL transport delegated to the Claude Code Cloud HTTPS session proxy (LAB ONLY).

Lives in ``labs/`` on purpose: it runs a host binary (``pdftotext``) through ``subprocess``, which the product
boundary forbids in ``rightware/agent`` (no shell in the product). It is not a production component.

NOT the production transport. Production stays ``rightware.agent.web.HttpxFetcher`` (own DNS resolution, public-IP
check, pinned connection, TLS + peer verification). This fetcher exists because this environment has no direct DNS:
all egress goes through the session proxy given by the environment (``HTTPS_PROXY`` + ``SSL_CERT_FILE``).

What THIS fetcher ENFORCES itself (fail-closed, before every request and on every redirect hop):
* exact host allowlist (``host_allowed`` from PublicBrowser AND its own authorised set); HTTPS on port 443 only;
  no IP literals, user info or non-default ports; GET only; manual redirects (each hop counts and is re-checked);
* budgets: requests per question (incl. redirects), requests per window, bytes per response, timeout per request,
  window deadline; allowed content types (HTML/text; complete PDFs are converted to text on the HOST with the
  fixed ``pdftotext`` binary — an experimental dependency; truncated PDFs are refused);
* an audit record per request (time, URL, status, final URL, content type, bytes, sha256) and the raw bytes kept
  under ``.runtime/`` for independent verification of any value shown to the user.
What it DELEGATES to the session proxy and CANNOT verify independently (stated in every audit record):
* DNS resolution, the public/non-private nature of the destination IP and the identity of the TCP peer;
* TLS is verified only up to the session proxy (with the session CA bundle), not end-to-end to the origin server.
It never invents an IP or a peer check to look like the production transport."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from rightware.agent.web import USER_AGENT, Page, WebRefused, html_to_text

DELEGATED = ("dns", "ip_publico", "peer_tcp", "tls_ate_origem")
ENFORCED = ("allowlist_exacta_por_salto", "https_443", "sem_ip_literal", "so_get", "limites_pedidos_bytes_tempo",
            "tipos_de_conteudo", "auditoria_e_bytes_guardados")
TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
PDF_TYPES = ("application/pdf",)
PDFTOTEXT = "/usr/bin/pdftotext"          # host poppler binary (fixed path, fixed arguments); EXPERIMENTAL dependency


def pdf_text(raw: bytes, timeout_s: float = 10.0) -> str:
    """Host-side PDF → text (``pdftotext -layout``). Never exposed to the model as a tool; no shell; bounded output."""
    import subprocess
    import tempfile
    if not os.path.isfile(PDFTOTEXT):
        raise WebRefused("conversor de PDF indisponível neste anfitrião")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(raw)
        tmp.flush()
        out = subprocess.run([PDFTOTEXT, "-layout", "-nopgbrk", "-enc", "UTF-8", tmp.name, "-"], capture_output=True,
                             timeout=timeout_s, check=False)
    if out.returncode != 0:
        raise WebRefused("PDF ilegível pelo conversor")
    return out.stdout[:MAX_TEXT_CHARS * 4].decode("utf-8", errors="replace")
MAX_TEXT_CHARS = 60_000


class BudgetExceeded(WebRefused):
    pass


class SessionProxyFetcher:
    def __init__(self, hosts: tuple[str, ...], *, authorisation: str, per_question: int = 8, per_window: int = 40,
                 max_bytes: int = 512 * 1024, timeout_s: float = 10.0, window_s: float = 3600.0,
                 store: Path | None = None, proxy: str | None = None, ca_file: str | None = None,
                 transport=None, clock=time.time, window_start: float | None = None):
        import httpx
        self.hosts = frozenset(h.strip().rstrip(".").lower() for h in hosts)
        if not self.hosts or any(not h or "/" in h or ":" in h or "*" in h for h in self.hosts):
            raise ValueError("hosts autorizados inválidos")
        if not authorisation.strip():
            raise ValueError("o transporte experimental exige a referência da autorização do operador")
        self.authorisation = authorisation
        self.per_question, self.per_window, self.max_bytes = per_question, per_window, max_bytes
        self.timeout_s, self._clock = timeout_s, clock
        self.started = window_start if window_start is not None else clock()
        self.deadline = self.started + window_s            # fixed authorisation window (shared by every process)
        log = Path(store) / "requests.jsonl" if store is not None else None
        self.requests = sum(1 for _ in open(log, encoding="utf-8")) if log is not None and log.is_file() else 0
        self.question_requests = 0
        self.audit: list[dict] = []
        self.store = store
        self._lock = threading.Lock()
        if transport is None:
            proxy = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
            ca_file = ca_file or os.environ.get("SSL_CERT_FILE")
            if not proxy or not ca_file or not Path(ca_file).is_file():
                raise WebRefused("transporte session_proxy exige HTTPS_PROXY e SSL_CERT_FILE do ambiente")
            transport = httpx.HTTPTransport(proxy=proxy, verify=ssl.create_default_context(cafile=ca_file),
                                            trust_env=False, retries=0, http2=False)
        self._transport = transport
        self.revoked = False

    # -- lifecycle -----------------------------------------------------------------------------------------------
    def begin_question(self) -> None:
        with self._lock:
            self.question_requests = 0

    def revoke(self) -> None:
        with self._lock:
            self.revoked = True

    def guarantees(self) -> dict:
        return {"transport": "session_proxy (EXPERIMENTAL)", "authorisation": self.authorisation,
                "enforced": list(ENFORCED), "delegated_not_verified": list(DELEGATED)}

    # -- checks ----------------------------------------------------------------------------------------------------
    def _check(self, url: str, host_allowed) -> str:
        p = urlsplit(url)
        host = (p.hostname or "").rstrip(".").lower()
        if p.scheme != "https" or p.port not in (None, 443) or p.username or p.password:
            raise WebRefused("só https na porta 443, sem credenciais no URL")
        if not host or host.replace(".", "").isdigit() or ":" in host or host.startswith("0x"):
            raise WebRefused("endereços IP não são permitidos")
        if host not in self.hosts or (host_allowed is not None and not host_allowed(host)):
            raise WebRefused("servidor fora dos sites autorizados nesta tarefa")
        return url

    def _count(self) -> None:
        with self._lock:
            if self.revoked or self._clock() > self.deadline:
                raise BudgetExceeded("autorização de rede expirada ou revogada")
            if self.requests >= self.per_window:
                raise BudgetExceeded(f"limite de {self.per_window} pedidos da janela atingido")
            if self.question_requests >= self.per_question:
                raise BudgetExceeded(f"limite de {self.per_question} pedidos por pergunta atingido")
            self.requests += 1
            self.question_requests += 1

    def _record(self, entry: dict, raw: bytes | None) -> None:
        entry.update(transport="session_proxy", delegated_not_verified=list(DELEGATED), authorisation=self.authorisation)
        if raw is not None and self.store is not None:
            self.store.mkdir(parents=True, exist_ok=True)
            (self.store / f"{entry['sha256']}.bin").write_bytes(raw)
        self.audit.append(entry)
        if self.store is not None:
            with open(self.store / "requests.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -- fetch (PublicBrowser interface) ------------------------------------------------------------------------
    def fetch(self, url: str, host_allowed=None) -> Page:
        import httpx
        requested = current = self._check(url, host_allowed)
        with httpx.Client(transport=self._transport, timeout=self.timeout_s, follow_redirects=False,
                          trust_env=False, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain"}) as client:
            for _ in range(self.per_question + 1):
                self._count()
                t0 = time.monotonic()
                entry = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._clock())), "url": current}
                try:
                    with client.stream("GET", current) as resp:
                        entry.update(status=resp.status_code)
                        if resp.status_code in (301, 302, 303, 307, 308):
                            nxt = urljoin(current, resp.headers.get("location", ""))
                            entry.update(redirect_to=nxt, seconds=round(time.monotonic() - t0, 2))
                            self._record(entry, None)
                            current = self._check(nxt, host_allowed)
                            continue
                        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                        chunks, size, truncated = [], 0, False
                        for chunk in resp.iter_bytes():
                            size += len(chunk)
                            if size > self.max_bytes:
                                chunks.append(chunk[:self.max_bytes - (size - len(chunk))])
                                truncated = True
                                break
                            chunks.append(chunk)
                        raw = b"".join(chunks)
                        digest = hashlib.sha256(raw).hexdigest()
                        markup = raw.decode(resp.encoding or "utf-8", errors="replace")
                        entry.update(final_url=current, content_type=ctype, bytes=len(raw), truncated=truncated,
                                     sha256=digest, seconds=round(time.monotonic() - t0, 2),
                                     pdf_links=markup.lower().count(".pdf") if "html" in ctype else None)
                        self._record(entry, raw)
                        if ctype in PDF_TYPES and not truncated:
                            text = pdf_text(raw)
                            entry_pdf = {"pdf_text_chars": len(text)}
                            self.audit[-1].update(entry_pdf)
                            return Page(requested, current, resp.status_code, ctype,
                                        f"[Documento PDF convertido para texto pelo anfitrião]\n{text[:MAX_TEXT_CHARS]}",
                                        digest, len(text) > MAX_TEXT_CHARS, "")
                        if ctype not in TEXT_TYPES:
                            raise WebRefused(f"tipo de conteúdo não suportado nesta validação ({ctype or 'desconhecido'})")
                        text = html_to_text(markup) if "html" in ctype else markup
                        if len(text) > MAX_TEXT_CHARS:
                            text, truncated = text[:MAX_TEXT_CHARS], True
                        return Page(requested, current, resp.status_code, ctype, text, digest, truncated,
                                    markup if "html" in ctype else "")
                except httpx.HTTPError as exc:
                    entry.update(error=type(exc).__name__, seconds=round(time.monotonic() - t0, 2))
                    self._record(entry, None)
                    raise WebRefused(f"falha de transporte ({type(exc).__name__})") from None
        raise WebRefused("demasiados redireccionamentos")
