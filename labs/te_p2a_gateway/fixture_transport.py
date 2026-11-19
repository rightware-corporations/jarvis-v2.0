"""Experimental, SEPARATE transport for the synthetic catalogue (labs only).

The production ``HttpxFetcher`` refuses private addresses (SSRF protection), so it cannot reach the
fixture container on an internal Docker network — and it must keep refusing. This module does NOT
change it. Instead the gateway builds its OWN fetcher instance whose transport:

* accepts exactly ONE synthetic host, ``catalog.fixture.example`` (any other host raises),
* forwards the request path to the fixture container (``http://fixture:8765``) and returns its
  response unchanged,
* is constructed only by the gateway process; nothing in the model's text can select or alter it.

The ``PublicBrowser`` host allowlist still applies on top (only ``catalog.fixture.example``).
"""
from __future__ import annotations

import httpx

SYNTHETIC_HOST = "catalog.fixture.example"
BASE_URL = f"https://{SYNTHETIC_HOST}/"


class FixtureOnlyTransport(httpx.BaseTransport):
    def __init__(self, upstream: str = "http://fixture:8765", inner: httpx.BaseTransport | None = None):
        self.upstream = httpx.URL(upstream)
        self.inner = inner or httpx.HTTPTransport()
        self.forwarded: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != SYNTHETIC_HOST or request.method != "GET":
            raise httpx.ConnectError(f"experimental transport refuses {request.url.host}")
        target = self.upstream.copy_with(path=request.url.path, query=request.url.query or None)
        self.forwarded.append(request.url.path)
        upstream_request = httpx.Request("GET", target, headers={"Accept": "text/html"})
        response = self.inner.handle_request(upstream_request)
        response.read()
        return httpx.Response(response.status_code, headers=response.headers, content=response.content,
                              request=request)


def fixture_fetcher(upstream: str = "http://fixture:8765", inner=None):
    """An HttpxFetcher bound to the fixture transport. The resolver/peer/SSRF hooks are satisfied by
    a documentation-range public address because the transport itself is the only route (one host)."""
    from rightware.agent.web import HttpxFetcher
    return HttpxFetcher(resolver=lambda host: ["93.184.216.34"], transport=FixtureOnlyTransport(upstream, inner),
                        peer_check=lambda response: True, ssrf=lambda url: None)
