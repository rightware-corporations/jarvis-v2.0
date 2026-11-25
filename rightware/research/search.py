"""DuckDuckGo (HTML endpoint) as the first search engine — through the SAME audited fetcher.

Why not the ``ddgs`` client (installed, 9.16.0): it uses its own ``primp`` HTTP client with random browser
impersonation, POST, and internal redirect handling, so individual requests and redirect hops cannot pass through the
RIGHTWARE network policy, limits and receipts; its "auto" mode also rotates across ~10 other engines. This module keeps
only the knowledge of the result markup and performs ONE GET per query with the host fetcher (per-hop host check,
SSRF, byte/time limits). Result links are DDG redirect wrappers (``/l/?uddg=<target>``): the target is decoded
locally and the wrapper is never followed. A rate-limit / bot-check page is reported as blocked and NOT retried or
worked around.
"""
from __future__ import annotations

import dataclasses
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, urljoin, urlsplit

SEARCH_HOST = "html.duckduckgo.com"
SEARCH_URL = "https://html.duckduckgo.com/html/?q={q}"
MAX_RESULTS = 8
BLOCK_MARKERS = ("anomaly-modal", "challenge-form", "bots use duckduckgo", "unfortunately, bots", "captcha")


@dataclasses.dataclass
class Result:
    url: str
    title: str
    snippet: str


class SearchBlocked(RuntimeError):
    """The engine answered with a rate-limit or bot-check page (never circumvented)."""


class _DdgParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.results: list[dict] = []
        self._cur: dict | None = None
        self._field: str | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "a" and "result__a" in cls.split():
            self._cur = {"href": a.get("href") or "", "title": "", "snippet": "", "ad": False}
            self.results.append(self._cur)
            self._field = "title"
        elif tag in ("a", "div", "td") and "result__snippet" in cls.split() and self.results:
            self._field = "snippet"
            self._cur = self.results[-1]

    def handle_endtag(self, tag):
        if tag in ("a", "div", "td"):
            self._field = None

    def handle_data(self, data):
        if self._field and self._cur is not None:
            self._cur[self._field] += data


def decode_href(href: str, base: str) -> str | None:
    """DDG wrapper → real target (decoded locally); ads and engine-internal links → None."""
    full = urljoin(base, href)
    parts = urlsplit(full)
    host = (parts.hostname or "").lower()
    if host.endswith("duckduckgo.com"):
        if parts.path.startswith("/l/"):
            target = parse_qs(parts.query).get("uddg", [""])[0]
            return target or None
        return None                                   # y.js (ads) or any other engine page
    return full


def build_url(query: str) -> str:
    return SEARCH_URL.replace("{q}", quote_plus(" ".join(query.split())[:120]))


def parse(markup: str, base: str = "https://html.duckduckgo.com/html/") -> list[Result]:
    low = markup.lower()
    if any(m in low for m in BLOCK_MARKERS) and "result__a" not in low:
        raise SearchBlocked("o motor de pesquisa devolveu uma página de verificação ou limite de pedidos")
    p = _DdgParser(base)
    p.feed(markup)
    out, seen = [], set()
    for r in p.results:
        url = decode_href(r["href"], base)
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(Result(url, " ".join(r["title"].split())[:160], " ".join(r["snippet"].split())[:300]))
        if len(out) >= MAX_RESULTS:
            break
    return out
