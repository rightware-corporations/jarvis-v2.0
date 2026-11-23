"""WEB-01 W1: in-process FIXTURE corpus (no socket is ever opened).

Pages under ``pages/<host>/<path>.html`` are local, synthetic pages written by RIGHTWARE for testing; each one says
so in its body. Hosts are under the reserved ``.fixture.example`` domain so they can never be mistaken for real
sites. ``pesquisa.fixture.example/search?q=`` is a deterministic search engine over the same corpus (token
overlap), so a search is just another receipted GET through the egress guard.

Special routes used by the policy tests:
* ``enciclopedia.fixture.example/wiki/Capital_de_Mocambique`` → 301 to ``/wiki/Maputo`` (allowed redirect);
* ``forum.fixture.example/sair?…`` → 302 to ``https://fora.fixture.example/`` (host NOT in the allowlist).
"""
from __future__ import annotations

import html
import re
import threading
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlsplit, parse_qs

import httpx

PAGES = Path(__file__).resolve().parent / "pages"
SEARCH_HOST = "pesquisa.fixture.example"
FIXTURE_IP = "93.184.216.34"      # documentation-style global address: satisfies check_url; the transport is the route
REDIRECTS = {("enciclopedia.fixture.example", "/wiki/Capital_de_Mocambique"): (301, "/wiki/Maputo")}
MAX_RESULTS = 5


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", _fold(text))}


def corpus() -> dict[str, str]:
    """{url: html} for every fixture page (deterministic order)."""
    out = {}
    for f in sorted(PAGES.rglob("*.html")):
        rel = f.relative_to(PAGES)
        host, path = rel.parts[0], "/" + "/".join(rel.parts[1:])[:-len(".html")]
        out[f"https://{host}{path}"] = f.read_text(encoding="utf-8")
    return out


def _visible(markup: str) -> tuple[str, str]:
    from rightware.agent.web import html_to_text
    text = html_to_text(markup)
    title = text.split("\n", 1)[0].removeprefix("Título: ") if text.startswith("Título: ") else ""
    return title, text


def search(query: str) -> list[dict]:
    q = _tokens(query)
    scored = []
    for url, markup in corpus().items():
        title, text = _visible(markup)
        score = len(q & _tokens(text)) + 2 * len(q & _tokens(title))
        if score:
            line = next((ln for ln in text.splitlines()[1:] if _tokens(ln) & q and "FIXTURE" not in ln), "")
            scored.append((-score, url, title, line[:200]))
    return [{"url": u, "title": t, "snippet": s} for _, u, t, s in sorted(scored)[:MAX_RESULTS]]


def search_page(query: str) -> str:
    items = "".join(f'<li><a href="{html.escape(r["url"])}">{html.escape(r["title"])}</a><p>{html.escape(r["snippet"])}'
                    f"</p></li>" for r in search(query))
    return (f'<!doctype html><html lang="pt"><head><meta charset="utf-8"><title>Pesquisa (fixture): '
            f'{html.escape(query)}</title></head><body><p class="fixture">FIXTURE RIGHTWARE — motor de pesquisa local '
            f"sobre o corpus de ensaio WEB-01; sem acesso à Internet.</p><ol>{items}</ol></body></html>")


def search_url(query: str) -> str:
    return f"https://{SEARCH_HOST}/search?q={quote(query)}"


class FixtureCorpusTransport(httpx.BaseTransport):
    """Serves only the fixture corpus. Any other host, method or path is a 404/refusal; nothing leaves the process."""

    def __init__(self, delay: float = 0.0, cancel: threading.Event | None = None):
        self.delay, self.cancel = delay, cancel
        self.served: list[str] = []
        self._pages = corpus()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if request.method != "GET" or not host.endswith(".fixture.example"):
            raise httpx.ConnectError(f"fixture transport refuses {request.method} {host}")
        if self.delay and (self.cancel.wait(self.delay) if self.cancel else threading.Event().wait(self.delay)):
            raise httpx.ReadError("fixture transport: aborted")
        self.served.append(f"{host}{path}")
        html_type = {"content-type": "text/html; charset=utf-8"}
        if (host, path) in REDIRECTS:
            code, loc = REDIRECTS[(host, path)]
            return httpx.Response(code, headers={"location": loc}, request=request)
        if host == "forum.fixture.example" and path == "/sair":
            return httpx.Response(302, headers={"location": "https://fora.fixture.example/recolha"}, request=request)
        if host == SEARCH_HOST and path == "/search":
            q = parse_qs(urlsplit(str(request.url)).query).get("q", [""])[0][:200]
            return httpx.Response(200, headers=html_type, content=search_page(q).encode(), request=request)
        markup = self._pages.get(f"https://{host}{path}")
        if markup is None:
            return httpx.Response(404, headers=html_type, content=b"<p>Nao encontrado (fixture)</p>", request=request)
        return httpx.Response(200, headers=html_type, content=markup.encode("utf-8"), request=request)


def fixture_fetcher(delay: float = 0.0, cancel: threading.Event | None = None):
    """An ``HttpxFetcher`` whose ONLY route is the fixture transport (resolver/SSRF/peer hooks are satisfied by
    construction because no socket exists). Host allowlisting is still enforced by the egress guard per hop."""
    from rightware.agent.web import HttpxFetcher
    return HttpxFetcher(resolver=lambda host: [FIXTURE_IP], transport=FixtureCorpusTransport(delay, cancel),
                        peer_check=lambda response: True, ssrf=lambda url: None)
