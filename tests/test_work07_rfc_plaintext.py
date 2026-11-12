"""WORK-07: official RFC plain-text title metadata, no model and no network."""
import unittest

from rightware.agent.browser import _rfc_plaintext_title, PublicBrowser
from rightware.agent import web as W

try:
    import httpx
except ImportError:
    httpx = None

def printed_rfc(number, title):
    return (
        "\ufeff\n\nInternet Engineering Task Force (IETF)         Editor\n"
        f"Request for Comments: {number}                    Example\n"
        "Category: Standards Track                       November 2026\n"
        "ISSN: 2070-1721\n\n\n"
        f"                         {title}\n\n"
        "Abstract\n\n"
        "   This is a synthetic public text document for tests.\n"
    )

class PlainTextRFC(unittest.TestCase):
    def test_extracts_any_number_and_title_from_printed_header(self):
        for number, title in [("9110", "HTTP Semantics"), ("9112", "HTTP/1.1"),
                              ("9888", "A Synthetic Web Draft")]:
            with self.subTest(number=number):
                self.assertEqual(_rfc_plaintext_title(printed_rfc(number, title)),
                                 f"RFC {number}: {title}")

    def test_refuses_without_an_rfc_header_or_abstract_or_title(self):
        for bad in [
            "The title is HTTP Semantics",
            "HTTP/1.1\nAbstract\n",
            "Request for Comments: 9112\n\nHTTP/1.1",
            "Request for Comments: 9112\n\nAbstract\n",
            "Request for Comments: 9112\n\n" + "X" * 121 + "\n\nAbstract\n",
        ]:
            with self.subTest(data=bad[:65]):
                self.assertEqual(_rfc_plaintext_title(bad), "")

@unittest.skipIf(httpx is None, "pinned httpx venv required")
class BrowserRFCText(unittest.TestCase):
    def test_text_document_has_title_evidence_without_html_metadata(self):
        def handler(req):
            return httpx.Response(200, headers={"content-type": "text/plain; charset=utf-8"},
                                  text=printed_rfc("9888", "A Synthetic Web Draft"))
        fetcher = W.HttpxFetcher(resolver=lambda _: ["93.184.216.34"],
                                 transport=httpx.MockTransport(handler),
                                 peer_check=lambda _: True, ssrf=lambda _: None)
        b = PublicBrowser(["www.rfc-editor.org"], fetcher)
        result = b.open("https://www.rfc-editor.org/rfc/rfc9888.txt")
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.evidence["title"], "RFC 9888: A Synthetic Web Draft")
        self.assertEqual(b.events[-1]["title"], "RFC 9888: A Synthetic Web Draft")
        self.assertIn("A Synthetic Web Draft", result.content)

if __name__ == "__main__":
    unittest.main()
