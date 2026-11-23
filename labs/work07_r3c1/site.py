"""WORK-07 R3-C1 synthetic archive (SEARCH -> RESULTS -> INFORMATION PAGE -> ORIGINAL DOCUMENT).

Fictional identifiers only (AX-101, AX-202). Served through httpx.MockTransport with the REAL
HttpxFetcher logic (allowlist per hop, redirects, content types, limits): no sockets, no internet.
The reference facts (ORIGINALS) are evaluator/test side: never given to the product or the model.

Shape, matching what real runs met on a public archive (information pages are not originals):
* /search/                 GET search form (field q)
* /search/results?q=...    result links to /info/ax-NNN/ (trailing slash)
* /info/ax-101/            short page: summary, metadata, link to the original in the first view
* /info/ax-202/            LONG page (> 3 500 visible chars) with 30 navigation links BEFORE the
                           link to the original (it is link 31+: not in the first view)
* /docs/ax-NNN.html        the original documents (title + verifiable body)
Off-site mirror links on the information pages test isolation.
"""
from __future__ import annotations

from urllib.parse import parse_qs

HOST = "archive.fixture.example"
START = f"https://{HOST}/search/"
OFFSITE = "https://mirror.other.example"
ORIGINALS = {   # reference facts, evaluator side only
    "AX-101": {"info": f"https://{HOST}/info/ax-101/", "original": f"https://{HOST}/docs/ax-101.html",
               "title": "AX-101: Widget Framing"},
    "AX-202": {"info": f"https://{HOST}/info/ax-202/", "original": f"https://{HOST}/docs/ax-202.html",
               "title": "AX-202: Widget Transport"},
}
HIDDEN_AFTER = 30   # navigation links placed before the AX-202 original link


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><title>{title}</title></head><body>{body}</body></html>"


def _info(doc: str, subject: str, long: bool) -> str:
    n = doc.lower()
    nav = "".join(f'<a href="/topics/t{i}/">Topic {i}</a> ' for i in range(1, HIDDEN_AFTER + 1)) if long else \
        '<a href="/">Home</a> <a href="/search/">Search</a>'
    history = "".join(f"<p>Status history entry {i}: the {doc} record was reviewed by the archive "
                      f"maintainers and its metadata was confirmed without changes to the text. " * 2 + "</p>"
                      for i in range(1, 25)) if long else ""
    return _page(f"Information on {doc}",
                 f"<nav>{nav}</nav><h1>{doc}</h1><p>Summary: {doc} describes widget {subject}. "
                 f"This page is the catalogue record, not the document.</p>{history}"
                 f'<p>Formats: <a href="/docs/{n}.html">View original (HTML)</a> '
                 f'<a href="{OFFSITE}/{n}.html">Mirror copy</a></p>')


class Archive:
    def __init__(self):
        self.requests: list[tuple[str, str]] = []

    def handler(self, request):
        import httpx
        self.requests.append((request.method, str(request.url)))
        html = lambda text, status=200: httpx.Response(  # noqa: E731
            status, headers={"content-type": "text/html; charset=utf-8"}, text=text)
        if request.url.host != HOST:
            return html("<p>OFFSITE CONTENT</p>")
        if request.method != "GET":
            return html("<p>no</p>", 405)
        path = request.url.path
        if path == "/search/":
            return html(_page("Search the Archive", '<form method="get" action="/search/results">'
                              '<label for="q">Identifier or keyword</label><input id="q" name="q"></form>'))
        if path == "/search/results":
            q = " ".join(parse_qs(request.url.query.decode()).get("q", [""])).lower()
            rows = [d for d in ORIGINALS if d.split("-")[1] in q or "widget" in q]
            body = "".join(f'<li><a href="/info/{d.lower()}/">{d} : Widget record</a></li>' for d in rows)
            return html(_page(f'Results "{q}"', f"<ul>{body or '<li>No results</li>'}</ul>"))
        if path == "/info/ax-101/":
            return html(_info("AX-101", "framing", long=False))
        if path == "/info/ax-202/":
            return html(_info("AX-202", "transport", long=True))
        for doc, ref in ORIGINALS.items():
            if f"https://{HOST}{path}" == ref["original"]:
                subject = ref["title"].split(": ", 1)[1]
                return html(_page(ref["title"], f"<pre>{doc}\n\n{subject}\n\nAbstract\n   This original document "
                                                f"specifies {subject.lower()} for widgets.</pre>"))
        return html("<p>not found</p>", 404)

    def fetcher(self):
        import httpx
        from rightware.agent.web import HttpxFetcher
        return HttpxFetcher(resolver=lambda host: ["93.184.216.34"], transport=httpx.MockTransport(self.handler),
                            peer_check=lambda response: True, ssrf=lambda url: None)
