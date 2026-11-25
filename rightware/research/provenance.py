"""Provenance policy for research reads (per question, fresh state).

A URL may be opened only if ALL hold:
1. **Provenance:** it was typed by the user in this question, or returned by this question's search (R#), or is a link
   found in a page/document already read in this question (L#), within the maximum depth. URLs written by the model
   (or by a page's text) are never opened.
2. **Static destination rules:** https on port 443, no credentials, no IP literal, no local/internal names, no
   sign-in/account/administration pages, no executable or archive downloads, bounded length.
3. **Destination control:** if the transport cannot verify the real destination IP (``verifies_destination`` False,
   e.g. the experimental session proxy), only hosts in the operator's closed list are allowed. Open reading needs a
   transport that resolves and pins the destination itself (``rightware.agent.web.HttpxFetcher``).
Appearing in a search result is NOT evidence that a URL is safe: rules 2 and 3 and the fetcher's own SSRF checks
(on every redirect hop) still apply.
"""
from __future__ import annotations

import dataclasses
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

MAX_DEPTH = 2                 # search result = 1, link inside a read result = 2
MAX_URL = 2048
LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".intranet", ".corp")
BLOCK_HOST = re.compile(r"(^|\.)(login|logon|signin|sign-in|auth|sso|accounts?|id|oauth|webmail|mail|"
                        r"internetbanking|homebanking|ebanking|netbanking|myaccount|admin|portal-cliente)\.", re.I)
BLOCK_PATH = re.compile(r"/(login|logon|signin|sign-in|entrar|iniciar-sessao|auth|oauth2?|sso|account|minha-conta|"
                        r"conta|checkout|pagamento|wp-admin|wp-login|admin|password|senha)(/|$|\?|\.)", re.I)
BLOCK_EXT = re.compile(r"\.(exe|msi|bat|cmd|ps1|sh|apk|dmg|pkg|deb|rpm|jar|zip|rar|7z|tar|gz|iso|js|vbs|scr)$", re.I)


@dataclasses.dataclass
class Entry:
    ref: str                  # R# / L# / U#
    url: str
    origin: str               # "user" | "search:<query#>" | "link:<S#>"
    depth: int
    title: str = ""


def canonical(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").rstrip(".").lower()
    netloc = host + (f":{parts.port}" if parts.port and parts.port != 443 else "")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


def static_problem(url: str) -> str | None:
    """Static destination rules (no I/O). Returns a reason or None."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL or any(c in url for c in "\r\n\t\x00 \\"):
        return "URL inválido"
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "URL malformado"
    if parts.scheme != "https":
        return "só https é permitido na pesquisa"
    if parts.username or parts.password or "@" in parts.netloc:
        return "credenciais no URL não são permitidas"
    if port not in (None, 443):
        return "só a porta 443 é permitida"
    host = (parts.hostname or "").rstrip(".").lower()
    if not host or "." not in host:
        return "URL sem servidor público"
    try:
        ipaddress.ip_address(host.strip("[]"))
        return "endereços IP directos não são permitidos"
    except ValueError:
        pass
    if host == "localhost" or host.endswith(LOCAL_SUFFIXES):
        return "endereço local não permitido"
    if BLOCK_HOST.search(host + ".") or BLOCK_PATH.search(parts.path or "/"):
        return "páginas de início de sessão, conta ou administração não são lidas"
    if BLOCK_EXT.search(parts.path or ""):
        return "downloads executáveis ou arquivos não são permitidos"
    return None


USER_URL = re.compile(r"https?://[^\s<>\"')\]]+")


class Provenance:
    def __init__(self, *, verifies_destination: bool, closed_hosts: tuple[str, ...] = (),
                 search_hosts: tuple[str, ...] = (), max_depth: int = MAX_DEPTH):
        self.verifies_destination = bool(verifies_destination)
        self.closed_hosts = frozenset(h.lower().rstrip(".") for h in closed_hosts)
        self.search_hosts = frozenset(h.lower().rstrip(".") for h in search_hosts)
        self.max_depth = max_depth
        self.entries: dict[str, Entry] = {}      # ref → entry
        self.by_url: dict[str, Entry] = {}       # canonical url → first entry
        self._n = {"R": 0, "L": 0, "U": 0}
        self.refusals: list[dict] = []

    # -- registration ---------------------------------------------------------------------------------------------
    def _add(self, kind: str, url: str, origin: str, depth: int, title: str = "") -> Entry | None:
        try:
            key = canonical(url)
        except ValueError:
            return None
        if key in self.by_url:
            return self.by_url[key]
        self._n[kind] += 1
        e = Entry(f"{kind}{self._n[kind]}", url, origin, depth, title[:160])
        self.entries[e.ref] = e
        self.by_url[key] = e
        return e

    def add_user_urls(self, instruction: str) -> list[Entry]:
        return [e for u in USER_URL.findall(instruction or "")[:5] if (e := self._add("U", u.rstrip(".,;"), "user", 1))]

    def add_result(self, url: str, title: str, query_no: int) -> Entry | None:
        return self._add("R", url, f"search:{query_no}", 1, title)

    def add_link(self, url: str, text: str, source_id: str, parent_depth: int) -> Entry | None:
        if parent_depth + 1 > self.max_depth:
            return None
        return self._add("L", url, f"link:{source_id}", parent_depth + 1, text)

    # -- decisions ------------------------------------------------------------------------------------------------
    def host_allowed(self, host: str) -> bool:
        """Per redirect hop (given to the fetcher): closed list when the destination cannot be verified."""
        host = (host or "").lower().rstrip(".")
        if host in self.search_hosts:
            return False                         # a read never goes to the search engine itself (no redirect wrapper)
        return self.verifies_destination or host in self.closed_hosts

    def resolve(self, target: str) -> tuple[Entry | None, str | None]:
        """Model target (R#/L#/U# or URL) → (entry, refusal reason)."""
        t = (target or "").strip()
        m = re.match(r"^\s*\[?([RLUrlu]\d{1,3})\b", t)       # "R2", "[R2]", or the copied line "R2. Título — host"
        entry = self.entries.get(m.group(1).upper()) if m else None
        if entry is None and t.lower().startswith(("http://", "https://")):
            try:
                entry = self.by_url.get(canonical(t))
            except ValueError:
                entry = None
            if entry is None:
                return None, self._refuse(t, "o endereço não veio da pesquisa, de uma página lida nem do pedido do "
                                             "utilizador" + self.valid_refs())
        if entry is None and t and re.fullmatch(r"[\w.-]+\.[a-z]{2,}(/\S*)?", t, re.I):
            # A small model often writes "host" or "host/path" instead of R#: match ONLY registered entries
            # (same provenance), first registered = best-ranked.
            want = t.lower()
            for e in self.entries.values():
                u = canonical(e.url)
                bare = u.split("://", 1)[1]
                if bare == want or bare.rstrip("/") == want.rstrip("/") or (
                        "/" not in want and (urlsplit(u).hostname or "") == want):
                    entry = e
                    break
        if entry is None:
            return None, self._refuse(t, "referência desconhecida" + self.valid_refs())
        reason = static_problem(entry.url)
        if reason is None:
            host = (urlsplit(entry.url).hostname or "").lower()
            if not self.host_allowed(host):
                reason = ("o transporte actual não verifica o IP de destino e este servidor não está na lista fechada "
                          "autorizada" if host not in self.search_hosts else "o motor de pesquisa não é uma fonte")
        if reason:
            return None, self._refuse(entry.url, reason)
        return entry, None

    def valid_refs(self) -> str:
        refs = [f"{e.ref} ({(urlsplit(e.url).hostname or '')})" for e in self.entries.values()][:8]
        return ("; referências válidas: " + ", ".join(refs) + " — chama de novo com target igual a uma delas"
                if refs else "; faz primeiro uma pesquisa (web_search)")

    def _refuse(self, url: str, reason: str) -> str:
        host = ""
        try:
            host = (urlsplit(url).hostname or "")[:80]
        except ValueError:
            pass
        self.refusals.append({"host": host, "target": (url or "")[:60] if not host else "", "reason": reason[:120]})
        return reason
