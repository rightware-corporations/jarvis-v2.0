"""OP01 LAB: offline FIXTURE corpus for the tool-using JARVIS chat (fictional entities; no socket is opened).

The fetcher is the REAL ``rightware.agent.web.HttpxFetcher`` (allowlist on every hop, content types, size limits)
with an in-process ``httpx.MockTransport`` serving ``labs/op01/corpus/<host>/<path>.html``. ``/search?q=`` on the
search host is a deterministic token-overlap index over the corpus. ``/wiki/Arquivo`` answers HTTP 503 (error-
recovery test). Evidence produced with it is FIXTURE evidence: never real Internet or real financial data."""
from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from rightware.agent.web import HttpxFetcher

DEFAULT = Path(__file__).resolve().parent / "corpus"
SEARCH_HOST = "pesquisa.op01.example"


def _fold(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def _pages(root: Path) -> dict[str, str]:
    out = {}
    for f in sorted(root.rglob("*.html")):
        rel = f.relative_to(root)
        path = "/" + "/".join(rel.parts[1:])[:-5]
        out[f"https://{rel.parts[0]}{'/' if path == '/index' else path}"] = f.read_text(encoding="utf-8")
    return out


def fixture_sites(root: Path | None = None) -> tuple[str, ...]:
    return tuple(sorted({p.name for p in Path(root or DEFAULT).iterdir() if p.is_dir()}))


def fixture_fetcher(root: Path | None = None) -> HttpxFetcher:
    pages = _pages(Path(root or DEFAULT))

    def handler(request: httpx.Request) -> httpx.Response:
        url = f"https://{request.url.host}{request.url.path}"
        if request.url.host == SEARCH_HOST and request.url.path == "/search":
            q = {w for w in re.findall(r"[a-z0-9]{3,}", _fold(parse_qs(urlsplit(str(request.url)).query).get("q", [""])[0]))}
            hits = sorted(((len(q & set(re.findall(r"[a-z0-9]{3,}", _fold(re.sub("<[^>]+>", " ", m))))), u)
                           for u, m in pages.items() if SEARCH_HOST not in u), reverse=True)
            items = "".join(f'<li><a href="{html.escape(u)}">{html.escape(re.search("<title>(.*?)</title>", pages[u]).group(1))}</a></li>'
                            for n, u in hits if n > 0)[:4000]
            body = f"<html><head><title>Resultados</title></head><body><h1>Resultados</h1><ol>{items}</ol></body></html>"
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=body.encode())
        if request.url.path == "/wiki/Arquivo":
            return httpx.Response(503, headers={"content-type": "text/html"}, content=b"<p>Servico indisponivel</p>")
        if url in pages:
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=pages[url].encode())
        return httpx.Response(404, headers={"content-type": "text/html"}, content=b"<p>Nao encontrado</p>")

    return HttpxFetcher(resolver=lambda host: ["93.184.216.34"], transport=httpx.MockTransport(handler),
                        peer_check=lambda response: True, ssrf=lambda url: None)   # FIXTURE only: no DNS


__all__ = ["fixture_fetcher", "fixture_sites", "quote"]
