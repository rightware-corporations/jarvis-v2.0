"""Semantic public browser for the JARVIS agent (WORK-07). No JavaScript.

An interactive, task-scoped browser over the SAME pinned network path as
``web_read`` (``HttpxFetcher``). It is the smallest adapter that lets the
model:
* open a public page;
* locate a search field;
* type a query;
* activate the search;
* follow result links;
* read visible text.

It exposes semantic elements (fields ``F#``, links ``L#``), never selectors,
coordinates, keystrokes or scripts.

Security boundary (enforced here and in ``HttpxFetcher``):
* Task host allowlist, checked on every URL before any connection: open,
  follow, form action and every redirect hop. Also SSRF/``is_global``, DNS
  pinning, peer check, ports 80/443, no proxy, no cookies.
* Only GET forms classified as SEARCH forms can be activated. No POST, no
  password/e-mail/file/textarea forms, no credential-like fields. Hidden
  values come from the page, never from the model.
* Only text/html and text/plain responses: no downloads.
* No JavaScript, no screenshots, no new windows, no filesystem, no shell.
* Page text and element labels go to the model inside the untrusted-data
  frame with a random boundary; a page cannot add tools or capabilities.

State is per task (a fresh instance per ``AgentSession.run``): history, the
element registry and typed values. Nothing persists.
"""
from __future__ import annotations

import dataclasses
from html.parser import HTMLParser
import re
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from rightware.agent.web import MAX_URL, Page, WebRefused, frame

MAX_VIEW_CHARS = 3500
MAX_LINKS_SHOWN = 25
MAX_LINKS_TOTAL = 800
MAX_FIELDS_TOTAL = 40
MAX_QUERY_CHARS = 120
MAX_FIND_RESULTS = 15
MAX_LABEL = 80

_TEXT_TYPES = {"", "text", "search"}
_FORBIDDEN_TYPES = {"password", "file", "email", "tel"}
_CREDENTIAL_NAME = re.compile(r"pass|pwd|user|login|e-?mail|token|otp|card|cvv|cvc|phone|secret|auth|ssn|iban",
                              re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclasses.dataclass
class Step:
    """What one browser operation produced. ``status`` uses the session vocabulary."""
    status: str                 # OK | HTTP_ERROR | EMPTY_CONTENT | REFUSED | FAILED
    content: str                # what the model receives
    evidence: dict              # what code verified (no model text besides the public query)


@dataclasses.dataclass
class _Control:
    kind: str                   # input | select | textarea | button
    type: str
    name: str
    value: str
    checked: bool = False
    disabled: bool = False
    options: list = dataclasses.field(default_factory=list)   # (value, selected)
    label: str = ""
    elem_id: str = ""


@dataclasses.dataclass
class _Form:
    action: str
    method: str
    controls: list
    search_ok: bool = False
    reason: str = ""


@dataclasses.dataclass
class _Field:
    fid: str
    form: _Form
    control: _Control
    page_url: str
    typed: str | None = None


class _DomParser(HTMLParser):
    """Collects links, forms, controls and labels. Script/style content is ignored."""
    _SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.forms: list[_Form] = []
        self.labels: dict[str, str] = {}
        self._skip = 0
        self._a: list | None = None
        self._form: _Form | None = None
        self._select: _Control | None = None
        self._option: list | None = None
        self._label_for: str | None = None
        self._label_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in self._SKIP:
            self._skip += 1
            return
        if tag == "a" and a.get("href"):
            self._a = [a["href"], [], a.get("aria-label") or a.get("title") or ""]
        elif tag == "form":
            self._form = _Form(a.get("action", ""), (a.get("method") or "get").strip().lower(), [])
            self.forms.append(self._form)
        elif tag == "label":
            self._label_for, self._label_text = a.get("for") or None, []
        elif tag in ("input", "button", "textarea", "select"):
            default_type = {"input": "text", "button": "submit"}.get(tag, tag)
            ctl = _Control(tag, (a.get("type") or default_type).strip().lower(), a.get("name", ""),
                           a.get("value", ""), "checked" in a, "disabled" in a,
                           label=(a.get("aria-label") or a.get("placeholder") or a.get("title") or "")[:MAX_LABEL],
                           elem_id=a.get("id", ""))
            if self._form is not None:
                self._form.controls.append(ctl)
            if tag == "select":
                self._select = ctl
        elif tag == "option" and self._select is not None:
            self._option = [a.get("value"), "selected" in a, []]

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if tag == "a" and self._a is not None:
            href, parts, aria = self._a
            text = " ".join(" ".join(parts).split()) or aria
            self.links.append((href, text[:MAX_LABEL]))
            self._a = None
        elif tag == "form":
            self._form = None
        elif tag == "label":
            if self._label_for:
                self.labels[self._label_for] = " ".join(" ".join(self._label_text).split())[:MAX_LABEL]
            self._label_for = None
        elif tag == "option" and self._option is not None and self._select is not None:
            value, selected, parts = self._option
            text = " ".join(" ".join(parts).split())
            self._select.options.append((text if value is None else value, selected))
            self._option = None
        elif tag == "select":
            self._select = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._a is not None:
            self._a[1].append(data)
        if self._label_for is not None:
            self._label_text.append(data)
        if self._option is not None:
            self._option[2].append(data)


def _classify_form(form: _Form, page_url: str) -> None:
    """Only GET search forms are activatable; everything else fails closed."""
    action = urljoin(page_url, form.action or page_url)
    form.action = action
    if form.method != "get":
        form.reason = f"método {form.method.upper()} (só pesquisas GET)"
    elif urlsplit(action).scheme not in ("http", "https"):
        form.reason = "destino não http(s)"
    elif any(c.kind == "textarea" or (c.kind == "input" and c.type in _FORBIDDEN_TYPES) for c in form.controls):
        form.reason = "pede dados pessoais, ficheiros ou texto livre"
    elif any(c.kind == "input" and c.type in _TEXT_TYPES and _CREDENTIAL_NAME.search(c.name) for c in form.controls):
        form.reason = "campo semelhante a credenciais"
    elif not any(c.kind == "input" and c.type in _TEXT_TYPES and c.name and not c.disabled for c in form.controls):
        form.reason = "sem campo de texto de pesquisa"
    else:
        form.search_ok = True


def _strip_fragment(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))


class PublicBrowser:
    """One task's browser. ``sites`` is the operator-approved host allowlist (exact host names)."""

    def __init__(self, sites, fetcher):
        hosts = {str(h).strip().rstrip(".").lower() for h in sites}
        if not hosts or any(not h or "/" in h or ":" in h or "*" in h for h in hosts):
            raise ValueError("a navegação exige uma lista de servidores exactos autorizados")
        self.sites = frozenset(hosts)
        self.fetcher = fetcher
        self.links: dict[str, tuple[str, str]] = {}          # L# -> (url, text)
        self._link_by_url: dict[str, str] = {}
        self.fields: dict[str, _Field] = {}                 # F# -> field
        self.current: Page | None = None
        self.current_text = ""
        self.pages = 0
        self.events: list[dict] = []

    # -- helpers --------------------------------------------------------------
    def allowed(self, host: str) -> bool:
        return host.rstrip(".").lower() in self.sites

    def _load(self, url: str, op: str, extra: dict) -> Step:
        event = {"op": op, "requested_url": url[:MAX_URL], **extra}
        try:
            page = self.fetcher.fetch(url, host_allowed=self.allowed)
        except WebRefused as exc:
            self.events.append({**event, "outcome": "REFUSED", "reason": str(exc)[:120]})
            return Step("REFUSED", f"Navegação recusada: {exc}.", {})
        except Exception as exc:              # fail closed, no internals
            self.events.append({**event, "outcome": "FAILED", "error": type(exc).__name__})
            return Step("FAILED", f"A navegação falhou ({type(exc).__name__}).", {})
        first = page.text.split("\n", 1)[0]
        evidence = {"final_url": page.final_url, "status": page.status, "content_type": page.content_type,
                    "sha256": page.sha256, "chars": len(page.text), "truncated": page.truncated,
                    "title": first[len("Título: "):][:160] if first.startswith("Título: ") else ""}
        if not 200 <= page.status < 300:
            self.events.append({**event, **evidence, "outcome": "HTTP_ERROR"})
            return Step("HTTP_ERROR", f"A página respondeu com HTTP {page.status}; não foi lida.", evidence)
        if not page.text.strip():
            self.events.append({**event, **evidence, "outcome": "EMPTY_CONTENT"})
            return Step("EMPTY_CONTENT", "A página não tem texto legível (pode depender de JavaScript).", evidence)
        self.pages += 1
        self.current = page
        view = self._index(page)
        self.events.append({**event, **evidence, "outcome": "OK"})
        return Step("OK", frame(dataclasses.replace(page, text=view)), evidence)

    def _register_link(self, url: str, text: str) -> str | None:
        if url in self._link_by_url:
            lid = self._link_by_url[url]
            if not self.links[lid][1] and text:
                self.links[lid] = (url, text)
            return lid
        if len(self.links) >= MAX_LINKS_TOTAL:
            return None
        lid = f"L{len(self.links) + 1}"
        self.links[lid] = (url, text)
        self._link_by_url[url] = lid
        return lid

    def _index(self, page: Page) -> str:
        """Register this page's elements and build the model's view (untrusted text)."""
        parser = _DomParser()
        try:
            parser.feed(page.markup or "")
            parser.close()
        except Exception:                     # malformed markup: text only, no elements
            parser = _DomParser()
        here = _strip_fragment(page.final_url)
        page_links, skipped = [], 0
        for href, text in parser.links:
            target = _strip_fragment(urljoin(page.final_url, href.strip()))
            parts = urlsplit(target)
            if parts.scheme not in ("http", "https") or len(target) > MAX_URL or target == here:
                continue
            if not self.allowed(parts.hostname or ""):
                skipped += 1
                continue
            lid = self._register_link(target, _CONTROL.sub(" ", text))
            if lid and lid not in [p[0] for p in page_links]:
                page_links.append((lid, target, text))
        field_lines, unsupported = [], []
        for form in parser.forms:
            _classify_form(form, page.final_url)
            if not form.search_ok:
                unsupported.append(form.reason)
                continue
            for ctl in form.controls:
                ctl.label = ctl.label or parser.labels.get(ctl.elem_id, "") or ctl.name
                if ctl.kind == "input" and ctl.type in _TEXT_TYPES and ctl.name and not ctl.disabled \
                        and len(self.fields) < MAX_FIELDS_TOTAL:
                    fid = f"F{len(self.fields) + 1}"
                    self.fields[fid] = _Field(fid, form, ctl, page.final_url)
                    dest = urlsplit(form.action)
                    field_lines.append(f'{fid}: campo de pesquisa "{_CONTROL.sub(" ", ctl.label)[:MAX_LABEL]}" '
                                       f"(formulário de pesquisa -> {dest.hostname}{dest.path})")
        self.current_text = page.text
        lines = [f"Endereço: {page.final_url}"]
        if field_lines:
            lines += ["Campos de pesquisa (usa web_type e depois web_submit):"] + field_lines
        if unsupported:
            lines.append(f"Formulários não suportados nesta página: {len(unsupported)} "
                         f"({'; '.join(sorted(set(unsupported)))[:200]}).")
        body = page.text[:MAX_VIEW_CHARS]
        lines += ["Texto visível" + (" (início)" if len(page.text) > MAX_VIEW_CHARS else "") + ":", body]
        if page_links:
            shown = page_links[:MAX_LINKS_SHOWN]
            lines.append(f"Ligações ({len(shown)} de {len(page_links)}; web_find procura as restantes; "
                         "web_follow abre uma):")
            lines += [f'{lid}: "{text[:MAX_LABEL]}" -> {url[:160]}' for lid, url, text in shown]
        if skipped:
            lines.append(f"({skipped} ligação(ões) para servidores não autorizados foram omitidas.)")
        return "\n".join(lines)

    # -- tools ------------------------------------------------------------------
    def open(self, url: str) -> Step:
        return self._load(url, "open", {})

    def follow(self, link: str) -> Step:
        target = self.links.get(link.strip().upper()) if isinstance(link, str) else None
        if target is None:
            self.events.append({"op": "follow", "link": str(link)[:12], "outcome": "REFUSED", "reason": "unknown link"})
            return Step("REFUSED", "Ligação desconhecida: usa um identificador L# mostrado numa página desta tarefa.", {})
        return self._load(target[0], "follow", {"link": link.strip().upper()})

    def type(self, field: str, text: str) -> Step:
        f = self.fields.get(field.strip().upper()) if isinstance(field, str) else None
        if f is None:
            return Step("REFUSED", "Campo desconhecido: usa um identificador F# de um campo de pesquisa mostrado.", {})
        query = " ".join(text.split()) if isinstance(text, str) else ""
        if not query or len(query) > MAX_QUERY_CHARS or _CONTROL.search(text):
            return Step("REFUSED", f"Pesquisa inválida: uma linha curta (até {MAX_QUERY_CHARS} caracteres).", {})
        f.typed = query
        return Step("OK", f'Escrevi "{query}" no campo {f.fid}. Usa web_submit com o campo {f.fid} para pesquisar.',
                    {"field": f.fid, "chars": len(query)})

    def submit(self, field: str) -> Step:
        f = self.fields.get(field.strip().upper()) if isinstance(field, str) else None
        if f is None:
            return Step("REFUSED", "Campo desconhecido: usa um identificador F# de um campo de pesquisa mostrado.", {})
        if not f.form.search_ok:                              # defence in depth: never registered otherwise
            return Step("REFUSED", "Este formulário não é uma pesquisa permitida.", {})
        typed = {id(x.control): x.typed for x in self.fields.values() if x.form is f.form and x.typed}
        if not typed:
            return Step("REFUSED", f"Escreve primeiro a pesquisa no campo {f.fid} com web_type.", {})
        pairs, button = [], False
        for c in f.form.controls:
            if c.disabled or not c.name:
                continue
            if c.kind == "input" and c.type in _TEXT_TYPES:
                pairs.append((c.name, typed.get(id(c), c.value)))
            elif c.kind == "input" and c.type == "hidden":
                pairs.append((c.name, c.value))
            elif c.kind == "input" and c.type in ("checkbox", "radio"):
                if c.checked:
                    pairs.append((c.name, c.value or "on"))
            elif c.kind == "select":
                chosen = [v for v, sel in c.options if sel] or [v for v, _ in c.options[:1]]
                pairs += [(c.name, v) for v in chosen[:1]]
            elif c.type == "submit" and not button:
                pairs.append((c.name, c.value))
                button = True
        p = urlsplit(f.form.action)
        url = urlunsplit((p.scheme, p.netloc, p.path, urlencode(pairs), ""))
        if len(url) > MAX_URL:
            return Step("REFUSED", "A pesquisa gera um endereço demasiado longo.", {})
        return self._load(url, "submit", {"field": f.fid, "query": " | ".join(typed.values())})

    def find(self, text: str) -> Step:
        needle = " ".join(text.split()).casefold() if isinstance(text, str) else ""
        if not needle or len(needle) > MAX_LABEL:
            return Step("REFUSED", "Texto de procura inválido (1 a 80 caracteres).", {})
        hits = [(lid, url, t) for lid, (url, t) in self.links.items()
                if needle in t.casefold() or needle in url.casefold()][:MAX_FIND_RESULTS]
        lines = [l for l in self.current_text.splitlines() if needle in l.casefold()][:5]
        body = [f'Procura por "{needle}" nas ligações e na página actual desta tarefa (sem nova navegação).']
        body += [f'{lid}: "{t[:MAX_LABEL]}" -> {url[:160]}' for lid, url, t in hits] or ["Nenhuma ligação encontrada."]
        if lines:
            body += ["Linhas da página actual:"] + [l[:200] for l in lines]
        url = self.current.final_url if self.current else "(nenhuma página aberta)"
        page = Page(url, url, 200, "text/plain", "\n".join(body), "", False)
        return Step("OK", frame(page), {"matches": len(hits)})
