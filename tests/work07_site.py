"""Controlled WORK-07 website fixture served through httpx.MockTransport (no sockets, no internet).

The REAL PublicBrowser and the REAL HttpxFetcher (redirect, allowlist, content-type and size logic)
run against it; only DNS, the peer check and the socket are replaced. The known answers for this
fixture live in tests only (KNOWN), never in the product.
"""
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from rightware.agent import web as W

HOST = "docs.fixture.example"
START = f"https://{HOST}/search/"
ROOT = Path(__file__).resolve().parent / "fixtures" / "work07_site"
KNOWN = {  # evaluator-side reference answers for the fixture
    "1001": {"title": "Widget Semantics", "url": f"https://{HOST}/doc/wsp1001.html"},
    "1002": {"title": "WTP/2.5", "url": f"https://{HOST}/doc/wsp1002.html"},
}
HTML = "text/html; charset=utf-8"


class Site:
    def __init__(self):
        self.requests: list[tuple[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, str(request.url)))
        if request.url.host != HOST:
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>EXFILTRATED</p>")
        if request.method != "GET":
            return httpx.Response(405, text="no")
        path = request.url.path
        if path == "/search/results.php":
            q = parse_qs(request.url.query.decode())
            query = " ".join(q.get("query", [""])).lower()
            if q.get("fmt") != ["html"]:
                return httpx.Response(400, headers={"content-type": "text/html"}, text="<p>bad form</p>")
            rows = [n for n in ("1001", "1002") if n in query or "widget" in query]
            body = "".join(f'<li><a href="/doc/wsp{n}.html">WSP {n}</a> <a href="/info/wsp{n}">info</a></li>'
                           for n in rows) or "<p>No results.</p>"
            return httpx.Response(200, headers={"content-type": HTML},
                                  text=f"<html><head><title>Search results</title></head><body><ul>{body}</ul>"
                                       f'<a href="/search/">New search</a></body></html>')
        if path == "/go/out":
            return httpx.Response(302, headers={"location": "https://evil.example/stolen"})
        if path.endswith(".pdf"):
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7")
        if path == "/error":
            return httpx.Response(500, headers={"content-type": "text/html"}, text="<p>down</p>")
        if path == "/slow":
            raise httpx.ReadTimeout("timeout", request=request)
        if path == "/js-only.html":
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  text="<html><body><script>render()</script></body></html>")
        file = {"/search/": "search/index.html", "/": "about.html", "/about.html": "about.html"}.get(path)
        file = file or (path.lstrip("/") if path.startswith("/doc/") else None)
        if file and (ROOT / file).is_file():
            return httpx.Response(200, headers={"content-type": HTML}, text=(ROOT / file).read_text(encoding="utf-8"))
        return httpx.Response(404, headers={"content-type": "text/html"}, text="<p>not found</p>")

    def fetcher(self) -> W.HttpxFetcher:
        return W.HttpxFetcher(resolver=lambda host: ["93.184.216.34"], transport=httpx.MockTransport(self.handler),
                              peer_check=lambda response: True, ssrf=lambda url: None)

    def hosts(self) -> set[str]:
        return {httpx.URL(u).host for _, u in self.requests}
