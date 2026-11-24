"""WEB-01 W0: declarative egress policy and the guard every WEB-01 read goes through.

The policy (``configs/web01/egress.json``) is DATA read by the host; nothing the model writes can change it.
Validation is strict and fail-closed: unknown keys, wrong types or out-of-range limits refuse the whole policy.

Enforced on every request (on top of ``rightware.agent.web.HttpxFetcher``, which keeps its own guarantees:
GET only, http/https on 80/443, no credentials/cookies/model headers, SSRF check of the upstream OpenJarvis guard
plus a stricter "every resolved address is global" check, DNS pinning, peer re-check, redirect re-validation):

* host allowlist (exact names), checked on the first URL AND on every redirect hop before connecting;
* method allowlist (only GET in WEB-01);
* per-response limits (bytes, timeout, redirects) — a policy can only TIGHTEN the fetcher's built-in maxima;
* per-mission budgets (requests, total bytes, wall-clock seconds) and cancellation;
* an audit entry for every decision (allowed or refused, with the reason; never page content).

Modes:
* ``fixture`` — the only mode buildable in W0–W2. Every allowed host must be under ``.fixture.example`` and the
  transport is the in-process fixture corpus (``rightware.web01.fixture``): no socket is ever opened.
* ``public`` — real egress (W3). ``build_fetcher`` REFUSES it unless the policy carries ``network_enabled: true``
  and an operator ``authorization_ref`` AND the host passes ``allow_public=True`` (only ``ResearchMission`` does,
  in one place). Until the specific authorisation exists the product cannot open external connections.

Transports for ``public`` (optional ``transport`` key, default ``direct``):
* ``direct`` — the product path (operator's computer): ``HttpxFetcher`` with local DNS, "every address global"
  check, DNS pinning and peer re-check.
* ``session_proxy`` — ONLY for validating inside a sandbox whose sole egress is an operator-approved HTTPS proxy
  (e.g. a Claude Code cloud session: no local DNS). The proxy resolves DNS, so the local IP checks cannot run; what
  remains enforced here: exact-host allowlist on every hop, https on 443 only, no IP-literal hosts, redirect
  re-validation, GET only, byte/time/request budgets, receipts. Declared as a weaker guarantee; never the default.
"""
from __future__ import annotations

import dataclasses
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from rightware.agent import web as W

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "configs" / "web01" / "egress.json"
POLICY_VERSION = "web01.egress.v1"
FIXTURE_SUFFIX = ".fixture.example"
_KEYS = {"version": str, "mode": str, "network_enabled": bool, "authorization_ref": (str, type(None)),
         "allowed_hosts": list, "methods": list, "max_bytes_per_response": int, "timeout_s": (int, float),
         "max_redirects": int, "max_requests_per_mission": int, "max_total_bytes_per_mission": int,
         "max_seconds_per_mission": (int, float)}
_OPTIONAL = {"transport": str, "user_agent": str}
TRANSPORTS = ("direct", "session_proxy")


class PolicyError(ValueError):
    """The egress policy file is invalid: nothing is allowed."""


class EgressRefused(W.WebRefused):
    """A request was refused by the egress policy (before any connection)."""


class NetworkNotAuthorised(PermissionError):
    """Real (public) egress was requested without the operator's specific WEB-01 W3 authorisation."""


@dataclasses.dataclass(frozen=True)
class EgressPolicy:
    version: str
    mode: str
    network_enabled: bool
    authorization_ref: str | None
    allowed_hosts: tuple[str, ...]
    methods: tuple[str, ...]
    max_bytes_per_response: int
    timeout_s: float
    max_redirects: int
    max_requests_per_mission: int
    max_total_bytes_per_mission: int
    max_seconds_per_mission: float
    transport: str = "direct"
    user_agent: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "EgressPolicy":
        if not isinstance(d, dict):
            raise PolicyError("a política tem de ser um objecto JSON")
        if not set(_KEYS) <= set(d) <= set(_KEYS) | set(_OPTIONAL):
            raise PolicyError(f"chaves inválidas: em falta {sorted(set(_KEYS) - set(d))}, "
                              f"desconhecidas {sorted(set(d) - set(_KEYS) - set(_OPTIONAL))}")
        transport = d.get("transport", "direct")
        if transport not in TRANSPORTS:
            raise PolicyError("transporte desconhecido")
        ua = d.get("user_agent")
        if ua is not None and not (ua.isprintable() and 8 <= len(ua) <= 200 and ua.startswith("RIGHTWARE-Jarvis/")):
            raise PolicyError("user_agent: texto imprimível 'RIGHTWARE-Jarvis/<versão> (<contacto>)', até 200")
        for k, typ in _KEYS.items():
            v = d[k]
            if isinstance(v, bool) and typ is not bool:     # bool is an int subclass: never accept it as a number
                raise PolicyError(f"{k}: tipo inválido")
            if not isinstance(v, typ):
                raise PolicyError(f"{k}: tipo inválido")
        if d["version"] != POLICY_VERSION:
            raise PolicyError("versão de política desconhecida")
        if d["mode"] not in ("fixture", "public"):
            raise PolicyError("modo desconhecido")
        hosts = d["allowed_hosts"]
        if not hosts or len(hosts) > 64 or not all(isinstance(h, str) and h == h.strip().lower().rstrip(".")
                                                   and 3 <= len(h) <= 253 and "." in h and "*" not in h
                                                   and "/" not in h and ":" not in h for h in hosts):
            raise PolicyError("allowed_hosts: nomes exactos em minúsculas, sem curingas, portas ou caminhos")
        if d["methods"] != ["GET"]:
            raise PolicyError("WEB-01 só permite GET")
        limits = {"max_bytes_per_response": (1, W.MAX_BYTES), "timeout_s": (0.1, W.TIMEOUT_S),
                  "max_redirects": (0, W.MAX_REDIRECTS), "max_requests_per_mission": (1, 200),
                  "max_total_bytes_per_mission": (1, 50 * W.MAX_BYTES), "max_seconds_per_mission": (1, 1800)}
        for k, (lo, hi) in limits.items():
            if not lo <= d[k] <= hi:
                raise PolicyError(f"{k} fora do intervalo [{lo}, {hi}]")
        if d["mode"] == "fixture":
            if d["network_enabled"] or d["authorization_ref"] is not None:
                raise PolicyError("modo fixture: network_enabled=false e authorization_ref=null")
            if not all(h.endswith(FIXTURE_SUFFIX) for h in hosts):
                raise PolicyError(f"modo fixture: só servidores *{FIXTURE_SUFFIX}")
        if d["mode"] == "public":
            if any(h.endswith(FIXTURE_SUFFIX) for h in hosts):
                raise PolicyError("modo public: servidores fixture não são permitidos")
            if d["network_enabled"] and not (d["authorization_ref"] or "").strip():
                raise PolicyError("modo public com rede exige authorization_ref do operador")
            if any(h.replace(".", "").isdigit() or h.startswith("[") for h in hosts):
                raise PolicyError("modo public: só nomes de servidor, nunca endereços IP")
        if d["mode"] == "fixture" and transport != "direct":
            raise PolicyError("modo fixture não usa transporte de rede")
        return cls(d["version"], d["mode"], d["network_enabled"], d["authorization_ref"], tuple(hosts),
                   tuple(d["methods"]), d["max_bytes_per_response"], float(d["timeout_s"]), d["max_redirects"],
                   d["max_requests_per_mission"], d["max_total_bytes_per_mission"],
                   float(d["max_seconds_per_mission"]), transport, ua)

    @classmethod
    def load(cls, path: Path = DEFAULT_POLICY) -> "EgressPolicy":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PolicyError(f"política ilegível: {type(exc).__name__}") from None
        return cls.from_dict(data)

    def host_allowed(self, host: str) -> bool:
        return (host or "").rstrip(".").lower() in self.allowed_hosts


def build_fetcher(policy: EgressPolicy, *, allow_public: bool = False):
    """The only constructor of a WEB-01 fetcher. W0–W2 always get the in-process fixture transport."""
    if policy.mode == "fixture":
        from rightware.web01.fixture import fixture_fetcher
        return fixture_fetcher()
    if not (allow_public and policy.network_enabled and (policy.authorization_ref or "").strip()):
        raise NetworkNotAuthorised("WEB-01: acesso externo à rede exige a autorização específica do operador (W3); "
                                   "nada foi contactado.")
    if policy.transport == "session_proxy":
        return session_proxy_fetcher(user_agent=policy.user_agent)
    return W.HttpxFetcher(user_agent=policy.user_agent)           # W3 product path: real SSRF/pinning guarantees


SESSION_PROXY_IP = "93.184.216.34"     # placeholder global address: the egress proxy, not this host, resolves DNS


def session_proxy_fetcher(proxy: str | None = None, ca_file: str | None = None, user_agent: str | None = None):
    """W3 validation transport (see module doc). Refuses to build without an explicit HTTPS proxy and CA bundle."""
    import ssl

    import httpx
    proxy = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    ca_file = ca_file or os.environ.get("SSL_CERT_FILE")
    if not proxy or not ca_file or not Path(ca_file).is_file():
        raise NetworkNotAuthorised("transporte session_proxy exige HTTPS_PROXY e SSL_CERT_FILE da sessão")
    transport = httpx.HTTPTransport(proxy=proxy, verify=ssl.create_default_context(cafile=ca_file),
                                    trust_env=False, retries=0, http2=False)

    def https_only(url: str) -> str | None:
        """String-level guard only: the upstream OpenJarvis SSRF check resolves DNS locally and (correctly) fails
        closed where there is no local DNS, so it cannot run here; the exact-host allowlist does the real work."""
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.port not in (None, 443):
            return "transporte session_proxy: só https na porta 443"
        host = (parts.hostname or "")
        if not host or host.replace(".", "").isdigit() or ":" in host or host.startswith("0x"):
            return "transporte session_proxy: endereços IP não são permitidos"
        return None

    return W.HttpxFetcher(resolver=lambda host: [SESSION_PROXY_IP], transport=transport,
                          peer_check=lambda response: True, ssrf=https_only, user_agent=user_agent)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class EgressGuard:
    """Per-mission enforcement of one policy over one fetcher. Thread-compatible for a single mission."""

    def __init__(self, policy: EgressPolicy, fetcher=None, *, clock=time.monotonic, now=utc_now, cancelled=None):
        self.policy = policy
        self.fetcher = fetcher if fetcher is not None else build_fetcher(policy)
        self.clock, self.now, self.cancelled = clock, now, cancelled
        self.started = clock()
        self.requests = 0
        self.total_bytes = 0
        self.audit: list[dict] = []

    def _refuse(self, url: str, reason: str, code: str):
        self.audit.append({"t": self.now(), "decision": "REFUSED", "code": code, "url": W.redact_url(url)[:300],
                           "reason": reason})
        raise EgressRefused(reason)

    def fetch(self, url: str, method: str = "GET") -> W.Page:
        p = self.policy
        if self.cancelled is not None and self.cancelled.is_set():
            self._refuse(url, "missão cancelada", "CANCELLED")
        if method not in p.methods:
            self._refuse(url, f"método {method!r} não permitido", "METHOD")
        if self.clock() - self.started > p.max_seconds_per_mission:
            self._refuse(url, "tempo da missão esgotado", "BUDGET_TIME")
        if self.requests >= p.max_requests_per_mission:
            self._refuse(url, "orçamento de pedidos da missão esgotado", "BUDGET_REQUESTS")
        if self.total_bytes >= p.max_total_bytes_per_mission:
            self._refuse(url, "orçamento de bytes da missão esgotado", "BUDGET_BYTES")
        host = (urlsplit(url).hostname or "") if isinstance(url, str) else ""
        if not p.host_allowed(host):
            self._refuse(url, "servidor fora da allowlist de egress", "HOST")
        self.requests += 1
        remaining = p.max_total_bytes_per_mission - self.total_bytes
        try:
            page = self.fetcher.fetch(url, host_allowed=p.host_allowed, max_bytes=min(p.max_bytes_per_response,
                                      remaining), timeout=p.timeout_s, max_redirects=p.max_redirects)
        except W.WebRefused as exc:
            self.audit.append({"t": self.now(), "decision": "REFUSED", "code": "FETCHER",
                               "url": W.redact_url(url)[:300], "reason": str(exc)[:200]})
            raise
        self.total_bytes += len(page.raw)
        self.audit.append({"t": self.now(), "decision": "ALLOWED", "url": W.redact_url(url)[:300],
                           "final_url": W.redact_url(page.final_url)[:300], "status": page.status,
                           "bytes": len(page.raw), "sha256": page.sha256})
        return page
