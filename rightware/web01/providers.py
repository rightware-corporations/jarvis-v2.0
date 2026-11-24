"""WEB-01 search providers. A provider only builds the search URL and extracts result URLs from a page that was
already fetched (and receipted) through the ``EgressGuard``; it never opens a connection itself.

* ``FixtureSearch`` — the local fixture engine (W1/W2), no network.
* ``WikipediaSearch`` — W3: the public HTML search page of ONE Wikipedia language host
  (``https://<host>/w/index.php?search=…&fulltext=1&ns0=1``). Results are taken only from the result headings
  (``mw-search-result-heading``), limited to article paths ``/wiki/<Title>`` on the same host; navigation, special,
  file, talk and external links are ignored. Content is never trusted: articles go through the same verifier.
"""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit

from rightware.web01 import fixture as FX
from rightware.web01.research import links as all_links

NON_ARTICLE = ("Especial:", "Special:", "Ficheiro:", "File:", "Ajuda:", "Help:", "Wikipédia:", "Wikipedia:",
               "Discussão:", "Talk:", "Categoria:", "Category:", "Predefinição:", "Template:", "Portal:", "Usuário",
               "User:", "Utilizador")


class FixtureSearch:
    name = "fixture"

    def search_url(self, query: str) -> str:
        return FX.search_url(query)

    def results(self, page) -> list[str]:
        return all_links(page)


class _Headings(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0                  # >0 while inside a result heading element
        self.stack: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.depth:
            self.depth += 1
            if tag == "a" and a.get("href"):
                self.hrefs.append(a["href"])
        elif "mw-search-result-heading" in (a.get("class") or "").split():
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1


class WikipediaSearch:
    name = "wikipedia"

    def __init__(self, host: str):
        if not host.endswith(".wikipedia.org") or host.count(".") != 2:
            raise ValueError("WikipediaSearch: um único host <lingua>.wikipedia.org")
        self.host = host

    def search_url(self, query: str) -> str:
        return (f"https://{self.host}/w/index.php?search={quote(query)}&title=Especial:Pesquisar"
                f"&profile=default&fulltext=1&ns0=1")

    def results(self, page) -> list[str]:
        p = _Headings()
        p.feed(page.markup or "")
        out = []
        for href in p.hrefs:
            u = urljoin(page.final_url, href)
            parts = urlsplit(u)
            if parts.scheme != "https" or parts.hostname != self.host or not parts.path.startswith("/wiki/"):
                continue
            title = unquote(parts.path[len("/wiki/"):])
            if not title or title.startswith(NON_ARTICLE) or parts.query:
                continue
            clean = f"https://{self.host}/wiki/{quote(title, safe=':()_,-.')}"
            if clean not in out:
                out.append(clean)
        return out


def for_policy(policy):
    """The provider a policy allows: fixture mode → local engine; public mode → Wikipedia on the FIRST allowed
    host, which must be a Wikipedia language host (the search service is part of the operator's authorisation)."""
    if policy.mode == "fixture":
        return FixtureSearch()
    return WikipediaSearch(policy.allowed_hosts[0])
