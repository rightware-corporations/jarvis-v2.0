"""JRV-TE-P2D supervised public egress (labs only; the production ``HttpxFetcher`` is NOT changed).

Why a separate transport
------------------------
In this sandbox there is no DNS and no direct route: every outbound connection must go through the platform
egress proxy on the host loopback (``HTTPS_PROXY``), which also applies its own host allowlist. The production
fetcher therefore cannot work here and must keep failing closed: its DNS-based SSRF layers (upstream
``check_ssrf`` name resolution, pinned resolver, peer ``is_global``) cannot run when name resolution and the
TCP connection to the origin belong to the platform proxy. They are NOT disabled or faked; instead this pilot
uses a different, narrower contract:

* path: goose (internal network, no route) → Gateway (internal networks only) → THIS service through ONE Unix
  socket mounted into the Gateway container → platform egress proxy (CONNECT) → exact allowlisted host;
* ``EgressPolicy.check`` (pure, no I/O): https only; port 443; GET only; no credentials; no IP literals; host
  EXACTLY in the allowlist (default: ``docs.python.org``); path under an allowlisted prefix; no dot-segments,
  no control/backslash characters; bounded length. The audited upstream ``check_ssrf`` is still consulted:
  any verdict other than the expected fail-closed "Could not resolve host" for an EXACTLY allowlisted name refuses;
* connection evidence verified per response: the TCP peer must be the configured platform proxy address and the
  TLS certificate must be valid for the exact requested host (httpx verification with the platform CA bundle;
  subject/SAN recorded);
* no redirect is followed here: a 3xx is returned with its ``Location``; the Gateway re-checks every hop against
  both its host allowlist and this policy before asking again;
* limits: per-request timeout, decoded body cap (stops decompression bombs early), content types text/html and
  text/plain only, per-trial request and byte budgets; no cookies, fixed headers, no request body.

Every decision (allowed or refused) is appended to the evidence log ``egress.jsonl``. Run on the HOST:
``python -m labs.te_p2d_public.egress --socket DIR/egress.sock --log OUT/egress.jsonl --proxy URL --ca FILE``
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import socketserver
import threading
import time
from urllib.parse import urlsplit

USER_AGENT = "RIGHTWARE-Jarvis/0.1 (+read-only; TE-P2D pilot)"
ALLOWED_TYPES = ("text/html", "text/plain")
MAX_URL = 2048
MAX_BODY = 1_000_000
TIMEOUT_S = 15.0
DEFAULT_HOSTS = ("docs.python.org",)
DEFAULT_PREFIXES = ("/3/library/",)
MAX_LINE = 4096


class EgressPolicy:
    """Pure URL policy shared by the Gateway (pre-check) and the egress service (enforcement)."""

    def __init__(self, hosts=DEFAULT_HOSTS, prefixes=DEFAULT_PREFIXES, ssrf=None):
        self.hosts = frozenset(h.lower() for h in hosts)
        self.prefixes = tuple(prefixes)
        if not self.hosts or not self.prefixes:
            raise ValueError("explicit host and path allowlists are required")
        self._ssrf = ssrf

    def check(self, url) -> str | None:
        """Return a refusal reason, or None when the URL is allowed. Never performs I/O."""
        if not isinstance(url, str) or not url or len(url) > MAX_URL:
            return "invalid URL"
        if any(c in url for c in "\r\n\t\x00 \\") or any(ord(c) < 0x20 or ord(c) == 0x7f for c in url):
            return "forbidden characters"
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return "malformed URL"
        if parts.scheme != "https":
            return "only https is allowed"
        if parts.username or parts.password or "@" in parts.netloc:
            return "credentials are not allowed"
        if port not in (None, 443):
            return "only port 443 is allowed"
        host = (parts.hostname or "").rstrip(".").lower()
        try:
            ipaddress.ip_address(host.strip("[]"))
            return "IP literals are not allowed"
        except ValueError:
            pass
        if host not in self.hosts:
            return "host not in the allowlist"
        path = parts.path or "/"
        if any(seg in ("..", ".") for seg in path.split("/")) or "%2e" in path.lower() or "%2f" in path.lower():
            return "dot-segments or encoded separators are not allowed"
        if not any(path.startswith(p) for p in self.prefixes):
            return "path outside the allowlisted prefixes"
        if self._ssrf is not None:
            verdict = self._ssrf(url)
            if verdict and not verdict.startswith("Could not resolve host"):
                return "blocked by the upstream SSRF guard"
        return None


def upstream_ssrf_or_none():
    try:
        from openjarvis.security.ssrf import check_ssrf
        return check_ssrf
    except ImportError:                       # host process without the vendor: the allowlist still applies
        return None


class EgressService:
    """Host-side fetcher. ``client_factory`` exists for offline tests (httpx MockTransport)."""

    def __init__(self, policy: EgressPolicy, log_path, proxy: str | None, ca: str | None, max_requests: int = 12,
                 max_total_bytes: int = 3_000_000, client_factory=None, expected_peer=None, clock=time.time):
        self.policy, self.log_path, self.proxy, self.ca = policy, log_path, proxy, ca
        self.max_requests, self.max_total_bytes = max_requests, max_total_bytes
        self.requests, self.total_bytes = 0, 0
        self._client_factory = client_factory
        self.expected_peer = expected_peer      # (host, port) of the platform proxy; None in offline tests
        self._lock = threading.Lock()
        self._clock = clock
        self.log: list[dict] = []

    fake = False

    def _record(self, row: dict) -> dict:
        row = {"t": round(self._clock(), 3), "seq": len(self.log) + 1, **({"FAKE": True} if self.fake else {}), **row}
        self.log.append(row)
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
        return row

    def _client(self):
        import httpx
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.Client(proxy=self.proxy, verify=self.ca or True, trust_env=False, follow_redirects=False,
                            timeout=TIMEOUT_S, http2=False,
                            headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain",
                                     "Accept-Encoding": "gzip"})

    def fetch(self, url) -> dict:
        with self._lock:                        # one request at a time; budgets are exact
            reason = self.policy.check(url)
            if reason is None and self.requests >= self.max_requests:
                reason = "request budget exhausted"
            if reason is None and self.total_bytes >= self.max_total_bytes:
                reason = "byte budget exhausted"
            if reason is not None:
                self._record({"url": url if isinstance(url, str) else None, "decision": "REFUSED", "reason": reason})
                return {"decision": "REFUSED", "reason": reason}
            self.requests += 1
            started = self._clock()
            try:
                out = self._do_fetch(url)
            except Exception as exc:            # fail closed; no internals beyond the class name
                out = {"decision": "FAILED", "reason": type(exc).__name__}
            body = out.pop("_body", b"")
            self.total_bytes += len(body)
            row = {"url": url, **{k: v for k, v in out.items() if k != "body_b64"},
                   "elapsed": round(self._clock() - started, 3)}
            self._record(row)
            if body:
                out["body_b64"] = base64.b64encode(body).decode()
            return out

    def _do_fetch(self, url) -> dict:
        with self._client() as client:
            with client.stream("GET", url) as resp:
                ext = resp.extensions.get("network_stream")
                peer = ext.get_extra_info("server_addr") if ext is not None else None
                ssl_obj = ext.get_extra_info("ssl_object") if ext is not None else None
                cert = ssl_obj.getpeercert() if ssl_obj is not None else None
                tls = _cert_summary(cert)
                host = (urlsplit(url).hostname or "").lower()
                if self.expected_peer is not None:
                    if peer is None or (str(peer[0]), int(peer[1])) != tuple(self.expected_peer):
                        return {"decision": "REFUSED", "reason": "connection was not through the platform proxy",
                                "peer": list(peer) if peer else None}
                    if not tls or host not in tls["dns_names"]:
                        return {"decision": "REFUSED", "reason": "TLS certificate not valid for the host", "tls": tls}
                base = {"decision": "OK", "status": resp.status_code, "peer": list(peer) if peer else None, "tls": tls,
                        "content_encoding": resp.headers.get("content-encoding")}
                if resp.status_code in (301, 302, 303, 307, 308):
                    return {**base, "location": resp.headers.get("location", "")[:MAX_URL]}
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype not in ALLOWED_TYPES:
                    return {"decision": "REFUSED", "reason": "content type not allowed", "content_type": ctype,
                            "status": resp.status_code}
                chunks, size, truncated = [], 0, False
                for chunk in resp.iter_bytes():                 # decoded: a compression bomb stops at MAX_BODY
                    size += len(chunk)
                    if size > MAX_BODY:
                        chunks.append(chunk[:MAX_BODY - (size - len(chunk))])
                        truncated = True
                        break
                    chunks.append(chunk)
                body = b"".join(chunks)
                return {**base, "content_type": ctype, "encoding": resp.encoding or "utf-8", "bytes": len(body),
                        "sha256": hashlib.sha256(body).hexdigest(), "truncated": truncated, "_body": body}


def _cert_summary(cert) -> dict | None:
    if not cert:
        return None
    names = sorted({v.lower() for k, v in cert.get("subjectAltName", ()) if k == "DNS"})
    issuer = dict(x[0] for x in cert.get("issuer", ()) if x)
    return {"dns_names": names, "issuer_cn": issuer.get("commonName"), "not_after": cert.get("notAfter")}


def fake_client_factory(directory: str):
    """FAKE dry-run only: ``index.json`` maps URL → {"status", "location"?, "file"?, "content_type"?}."""
    import httpx
    index = json.loads(open(os.path.join(directory, "index.json"), encoding="utf-8").read())

    def handler(request):
        entry = index.get(str(request.url))
        if entry is None:
            return httpx.Response(404, headers={"content-type": "text/html"}, text="not found")
        headers = {"content-type": entry.get("content_type", "text/html; charset=utf-8")}
        if entry.get("location"):
            headers["location"] = entry["location"]
        body = open(os.path.join(directory, entry["file"]), "rb").read() if entry.get("file") else b""
        return httpx.Response(entry["status"], headers=headers, content=body)
    return lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def make_server(service: EgressService, socket_path: str):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            line = self.rfile.readline(MAX_LINE + 1)
            try:
                if len(line) > MAX_LINE:
                    raise ValueError
                req = json.loads(line)
                url = req.get("url") if isinstance(req, dict) else None
            except ValueError:
                url = None
            out = service.fetch(url) if isinstance(url, str) else \
                service._record({"url": None, "decision": "REFUSED", "reason": "bad request"}) and \
                {"decision": "REFUSED", "reason": "bad request"}
            self.wfile.write((json.dumps(out) + "\n").encode())

    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = socketserver.ThreadingUnixStreamServer(socket_path, Handler)
    os.chmod(socket_path, 0o666)
    return server


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--socket", required=True)
    p.add_argument("--log", required=True)
    p.add_argument("--proxy", required=True)
    p.add_argument("--ca", required=True)
    p.add_argument("--host", action="append", default=[])
    p.add_argument("--prefix", action="append", default=[])
    p.add_argument("--max-requests", type=int, default=12)
    p.add_argument("--max-total-bytes", type=int, default=3_000_000)
    p.add_argument("--fake-pages", default=None, help="FAKE dry-run ONLY: serve recorded pages, no network")
    a = p.parse_args(argv)
    proxy = urlsplit(a.proxy)
    policy = EgressPolicy(tuple(a.host) or DEFAULT_HOSTS, tuple(a.prefix) or DEFAULT_PREFIXES, upstream_ssrf_or_none())
    if a.fake_pages:
        service = EgressService(policy, a.log, None, None, a.max_requests, a.max_total_bytes,
                                client_factory=fake_client_factory(a.fake_pages))
        service.fake = True
    else:
        service = EgressService(policy, a.log, a.proxy, a.ca, a.max_requests, a.max_total_bytes,
                                expected_peer=(proxy.hostname, proxy.port))
    server = make_server(service, a.socket)
    print(json.dumps({"egress": a.socket, "hosts": sorted(policy.hosts), "prefixes": policy.prefixes}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
