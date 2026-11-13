"""Trusted task contracts for the JARVIS agent: WORK-07 Milestone A1 (opt-in, default OFF).

A task contract names the MANDATORY objectives of a narrow class of public, read-only
browser tasks. In A1 a contract is only selected, validated and stored on the session. It
changes nothing the agent does or reports:
* no completion state;
* no receipts;
* no continuation (A2/A3/A4 are not implemented);
* its status is always ``NOT_EVALUATED``.

Trust boundary
--------------
Authority comes ONLY from the code-owned catalog ``TRUSTED_PRESETS`` in this module, which is
built and validated at import time and is read-only afterwards. The public entry
(``select_preset`` / ``AgentSession(task_preset=...)``) accepts nothing but a preset id string.

Dicts, JSON text, model output, page content, memory, ``TaskContract`` objects built by a
caller, or any ``trusted=True`` flag are rejected: they are not catalog entries. Selecting a
preset never grants anything:
* the session must already allow ``browse``;
* every preset host must already be one of the session's sites.

``AgentPolicy`` remains the only authority over tools, quotas and budgets.

Identity limits
---------------
An expected URL is a locator, not proof that a page is the authentic original. A1 has no
trusted identity rule (``identity_rule = "NONE"``). A future completion gate must therefore
report unknown identity rather than verified, until a trusted rule exists.
"""
from __future__ import annotations

import dataclasses
import ipaddress
import re
from types import MappingProxyType
from urllib.parse import urlsplit

SCHEMA_VERSION = "A1"
ORIGIN = "code_catalog"
STATUS_NOT_EVALUATED = "NOT_EVALUATED"          # A1 never evaluates completion
ACTIONS = ("read_page", "open_original")
MAX_OBJECTIVES = 8
MAX_HOSTS = 4
MAX_ID = 64
MAX_LABEL = 120
MAX_URL = 2048
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")            # ASCII, lowercase, no spaces
_OID = re.compile(r"[A-Z][A-Z0-9_]{0,31}\Z")
_HOST_LABEL = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)\Z")


class TaskContractError(ValueError):
    """A contract or selection was rejected (fail-closed)."""


@dataclasses.dataclass(frozen=True)
class BrowserObjective:
    oid: str                      # unique within the contract, e.g. "AX101"
    action: str                   # one of ACTIONS (read-only)
    url: str                      # canonical HTTPS locator on an approved host
    label: str                    # short code-owned description (never page text)
    identity_rule: str = "NONE"   # A1: no trusted identity proof exists


@dataclasses.dataclass(frozen=True)
class TaskContract:
    preset_id: str
    schema_version: str
    origin: str
    synthetic: bool               # True = test fixture only, never a claim about real publishers
    hosts: tuple[str, ...]
    objectives: tuple[BrowserObjective, ...]
    max_continuations: int = 0    # reserved for A3; NOT active in A1 (must be 0 or 1)

    @property
    def objective_ids(self) -> tuple[str, ...]:
        return tuple(o.oid for o in self.objectives)


# -- validation ------------------------------------------------------------------------
def _check_host(host: object) -> str:
    if not isinstance(host, str) or not host or len(host) > 253 or not host.isascii():
        raise TaskContractError("host inválido (só nomes ASCII; IDN só em forma punycode)")
    if host != host.lower() or host.endswith(".") or "." not in host:
        raise TaskContractError("host não canónico")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise TaskContractError("endereços IP não são permitidos como host")
    if not all(_HOST_LABEL.match(label) for label in host.split(".")):
        raise TaskContractError("host com caracteres não permitidos")
    return host


def _check_url(url: object, hosts: tuple[str, ...]) -> str:
    if not isinstance(url, str) or not url or len(url) > MAX_URL or not url.isascii():
        raise TaskContractError("URL inválido (vazio, demasiado longo ou não-ASCII)")
    if any(c in url for c in "\\%#?@ ") or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise TaskContractError("URL com caracteres não permitidos (encoding, query, fragmento ou credenciais)")
    try:
        parts = urlsplit(url)
        port = parts.port                                # may raise ValueError on a malformed port
    except ValueError:
        raise TaskContractError("URL malformado") from None
    if parts.scheme != "https":
        raise TaskContractError("só https é permitido")
    if port is not None or parts.netloc != parts.hostname:
        raise TaskContractError("URL com porta ou autoridade não canónica")
    if parts.hostname not in hosts:
        raise TaskContractError("host do objectivo fora dos hosts do contrato")
    path = parts.path
    if not path.startswith("/") or "//" in path:
        raise TaskContractError("caminho não canónico")
    if any(seg in (".", "..") for seg in path.split("/")):
        raise TaskContractError("caminho com segmentos relativos")
    return url


def validate_contract(contract: object) -> TaskContract:
    """Structural validation, fail-closed. Exact types only (no subclasses, no dicts)."""
    if type(contract) is not TaskContract:
        raise TaskContractError("só contratos do catálogo de código são aceites")
    c = contract
    if c.schema_version != SCHEMA_VERSION:
        raise TaskContractError("versão de contrato desconhecida")
    if c.origin != ORIGIN:
        raise TaskContractError("origem não confiável")
    if not isinstance(c.preset_id, str) or not _ID.match(c.preset_id):
        raise TaskContractError("identificador de preset inválido")
    if type(c.synthetic) is not bool:
        raise TaskContractError("marca 'synthetic' inválida")
    if type(c.max_continuations) is not int or c.max_continuations not in (0, 1):
        raise TaskContractError("limite de continuação inválido")
    if type(c.hosts) is not tuple or not 1 <= len(c.hosts) <= MAX_HOSTS:
        raise TaskContractError("número de hosts inválido")
    hosts = tuple(_check_host(h) for h in c.hosts)
    if len(set(hosts)) != len(hosts):
        raise TaskContractError("hosts duplicados")
    if type(c.objectives) is not tuple or not 1 <= len(c.objectives) <= MAX_OBJECTIVES:
        raise TaskContractError("número de objectivos inválido (1 a 8)")
    seen_ids, seen_targets = set(), set()
    for o in c.objectives:
        if type(o) is not BrowserObjective:
            raise TaskContractError("objectivo inválido")
        if not isinstance(o.oid, str) or not _OID.match(o.oid) or o.oid in seen_ids:
            raise TaskContractError("identificador de objectivo inválido ou duplicado")
        seen_ids.add(o.oid)
        if o.action not in ACTIONS:
            raise TaskContractError("acção não suportada (só leitura pública)")
        if not isinstance(o.label, str) or not o.label.strip() or len(o.label) > MAX_LABEL \
                or any(ord(ch) < 32 for ch in o.label):
            raise TaskContractError("rótulo de objectivo inválido")
        if o.identity_rule != "NONE":
            raise TaskContractError("regras de identidade ainda não são suportadas em A1")
        _check_url(o.url, hosts)
        if (o.action, o.url) in seen_targets:
            raise TaskContractError("objectivos repetidos não são suportados em A1")
        seen_targets.add((o.action, o.url))
    return c


def _build_catalog(entries: tuple[TaskContract, ...]) -> MappingProxyType:
    by_id: dict[str, TaskContract] = {}
    for entry in entries:
        validate_contract(entry)
        if entry.preset_id in by_id:
            raise TaskContractError("preset duplicado no catálogo")
        by_id[entry.preset_id] = entry
    return MappingProxyType(by_id)


# -- the code-owned catalog (the ONLY source of contract authority) ----------------------
TRUSTED_PRESETS = _build_catalog((
    # SYNTHETIC test fixture (labs/work07_r3c1/site.py). Not a real publisher, not an RFC.
    TaskContract(
        preset_id="synthetic-archive-two-originals",
        schema_version=SCHEMA_VERSION, origin=ORIGIN, synthetic=True,
        hosts=("archive.fixture.example",),
        objectives=(
            BrowserObjective("AX101", "open_original", "https://archive.fixture.example/docs/ax-101.html",
                             "abrir o documento original AX-101 (fixture sintética)"),
            BrowserObjective("AX202", "open_original", "https://archive.fixture.example/docs/ax-202.html",
                             "abrir o documento original AX-202 (fixture sintética)"),
        )),
))


def select_preset(preset_id: object, *, allow: set[str] | frozenset[str], sites: tuple[str, ...]) -> TaskContract:
    """Select a catalog preset for a session. Grants nothing: the session must already allow
    ``browse`` and already list every preset host among its sites."""
    if type(preset_id) is not str:
        raise TaskContractError("o preset é seleccionado só por identificador (texto), nunca por objecto ou JSON")
    contract = TRUSTED_PRESETS.get(preset_id)
    if contract is None:
        raise TaskContractError("preset desconhecido: contratos fora do catálogo não têm autoridade")
    if "browse" not in allow:
        raise TaskContractError("o preset exige a capacidade 'browse' já autorizada nesta sessão")
    session_hosts = {str(h).strip().rstrip(".").lower() for h in sites}
    if not set(contract.hosts) <= session_hosts:
        raise TaskContractError("o preset não pode acrescentar hosts aos sites autorizados da sessão")
    return validate_contract(contract)
