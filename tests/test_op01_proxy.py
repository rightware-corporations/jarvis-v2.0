"""OP01-FX-REAL-PROXY experimental fetcher — UNIT tests with httpx.MockTransport (no network, no proxy)."""
import tempfile
import unittest
from pathlib import Path

try:
    import httpx
    from labs.op01.proxy_transport import BudgetExceeded, SessionProxyFetcher
    from rightware.agent.web import WebRefused
except Exception:                       # pragma: no cover
    httpx = None


def handler(request):
    if request.url.path == "/r":
        return httpx.Response(302, headers={"location": "https://evil.example/x"})
    if request.url.path == "/ok-redirect":
        return httpx.Response(301, headers={"location": "https://bancomoc.mz/pt/"})
    if request.url.path == "/doc.pdf":
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4")
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                          content="<html><title>BM</title><p>Taxa 63,90</p><a href='x.pdf'>pdf</a></html>".encode())


@unittest.skipIf(httpx is None, "httpx required")
class ProxyFetcher(unittest.TestCase):
    def f(self, **kw):
        return SessionProxyFetcher(("www.bancomoc.mz", "bancomoc.mz"), authorisation="TEST",
                                   transport=httpx.MockTransport(handler), store=Path(tempfile.mkdtemp()), **kw)

    def test_allowlist_https_ip_and_redirect_hops(self):
        f = self.f()
        for bad in ("http://www.bancomoc.mz/", "https://evil.example/", "https://1.2.3.4/", "https://www.bancomoc.mz:8443/",
                    "https://u:p@www.bancomoc.mz/"):
            with self.assertRaises(WebRefused):
                f.fetch(bad)
        with self.assertRaises(WebRefused):
            f.fetch("https://www.bancomoc.mz/r")                         # redirect off the allowlist refused
        p = f.fetch("https://www.bancomoc.mz/ok-redirect")              # redirect inside the allowlist followed
        self.assertEqual(p.final_url, "https://bancomoc.mz/pt/")
        self.assertIn("63,90", p.text)
        self.assertEqual(f.audit[-1]["pdf_links"], 1)
        self.assertEqual(f.audit[-1]["delegated_not_verified"], ["dns", "ip_publico", "peer_tcp", "tls_ate_origem"])

    def test_budgets_pdf_and_revoke(self):
        f = self.f(per_question=2, per_window=3)
        f.fetch("https://www.bancomoc.mz/a")
        with self.assertRaises(WebRefused):
            f.fetch("https://www.bancomoc.mz/doc.pdf")                   # invalid PDF bytes: converter refuses
        self.assertEqual(f.audit[-1]["content_type"], "application/pdf")
        with self.assertRaises(BudgetExceeded):
            f.fetch("https://www.bancomoc.mz/b")                         # 3rd request in the same question
        f.begin_question()
        f.fetch("https://www.bancomoc.mz/c")
        f.begin_question()
        with self.assertRaises(BudgetExceeded):
            f.fetch("https://www.bancomoc.mz/d")                         # window budget (3) exhausted
        g = self.f()
        g.revoke()
        with self.assertRaises(BudgetExceeded):
            g.fetch("https://www.bancomoc.mz/a")

    def test_requires_authorisation(self):
        with self.assertRaises(ValueError):
            SessionProxyFetcher(("www.bancomoc.mz",), authorisation=" ", transport=httpx.MockTransport(handler))


if __name__ == "__main__":
    unittest.main()
