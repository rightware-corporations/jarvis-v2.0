"""WORK-07 R2: URL query credential redaction; no external network."""
import json
import unittest
from urllib.parse import parse_qs
from rightware.agent.web import Page, frame, redact_url, redact_text_urls

try:
    import httpx
    from rightware.agent import web as W
    from rightware.agent.browser import PublicBrowser
except ImportError:
    httpx = None

HOST = "www.rfc-editor.org"
SECRET = "synthetic-public-search-key-NOT-REAL"
URL = "https://" + HOST + "/api/v1/search/?q=9110&x-typesense-api-key=" + SECRET

class Redaction(unittest.TestCase):
    def test_query_value_redaction_preserves_public_search(self):
        url = URL + "&ACCESS_TOKEN=two&api%2Dkey=three&session_id=four&ordinary=yes"
        shown = redact_url(url)
        for value in (SECRET, "=two", "=three", "=four"):
            self.assertNotIn(value, shown)
        for name in ("x-typesense-api-key", "ACCESS_TOKEN", "api%2Dkey", "session_id"):
            self.assertIn(name + "=REDACTED", shown)
        self.assertIn("q=9110", shown)
        self.assertIn("ordinary=yes", shown)
        self.assertEqual(redact_url("https://" + HOST + "/rfc/rfc9110.html"),
                         "https://" + HOST + "/rfc/rfc9110.html")

    def test_page_frame_and_text_urls_masked(self):
        p = Page(URL, URL, 200, "text/plain", "Visit " + URL, "a" * 64, False)
        self.assertNotIn(SECRET, frame(p))
        self.assertIn("x-typesense-api-key=REDACTED", frame(p))
        self.assertNotIn(SECRET, redact_text_urls("Visit " + URL))

    def test_real_gate_recording_redacts_url_not_live_engine(self):
        from labs.work07_rfc_gate.gate import RecordingEngine
        class Fake:
            engine_id = "fake"
            def generate(self, *args, **kwargs):
                return {"content": "Visit " + URL,
                        "tool_calls": [{"name": "web_open", "arguments": json.dumps({"url": URL})}]}
        engine = RecordingEngine(Fake())
        raw = engine.generate([])
        self.assertIn(SECRET, raw["content"])
        recorded = json.dumps(engine.responses)
        self.assertNotIn(SECRET, recorded)
        self.assertIn("x-typesense-api-key=REDACTED", recorded)

@unittest.skipIf(httpx is None, "pinned httpx venv required")
class BrowserMockTransport(unittest.TestCase):
    def test_public_get_uses_key_while_model_views_and_evidence_are_redacted(self):
        sent = []
        def handler(req):
            sent.append(str(req.url))
            if req.url.path == "/search/":
                body = ('<html><head><title>Search</title></head><body><form method="GET" '
                        'action="/api/v1/search/"><input type="search" name="q">'
                        '<input type="hidden" name="x-typesense-api-key" value="' + SECRET + '">'
                        '</form></body></html>')
            elif req.url.path == "/api/v1/search/":
                qs = parse_qs(req.url.query.decode())
                self.assertEqual(qs.get("q"), ["9110"])
                self.assertEqual(qs.get("x-typesense-api-key"), [SECRET])
                body = ('<html><head><title>Results</title></head><body>'
                        '<a href="/info/rfc9110/?token=' + SECRET + '">RFC 9110</a></body></html>')
            elif req.url.path == "/info/rfc9110/":
                self.assertEqual(parse_qs(req.url.query.decode()).get("token"), [SECRET])
                body = '<html><head><title>RFC 9110: HTTP Semantics</title></head><body>HTTP</body></html>'
            else:
                return httpx.Response(404, headers={"content-type": "text/html"}, text="Missing")
            return httpx.Response(200, headers={"content-type": "text/html"}, text=body)
        fetcher = W.HttpxFetcher(resolver=lambda host: ["93.184.216.34"],
                                 transport=httpx.MockTransport(handler),
                                 peer_check=lambda resp: True, ssrf=lambda url: None)
        b = PublicBrowser([HOST], fetcher)
        opened = b.open("https://" + HOST + "/search/")
        self.assertEqual(opened.status, "OK")
        self.assertEqual(b.type("F1", "9110").status, "OK")
        search = b.submit("F1")
        self.assertEqual(search.status, "OK")
        found = b.find("rfc9110")
        followed = b.follow("L1")
        self.assertEqual(followed.status, "OK")
        self.assertEqual(len(sent), 3)
        self.assertIn(SECRET, sent[1])
        self.assertIn(SECRET, sent[2])
        exposed = "\n".join((opened.content, search.content, found.content, followed.content,
                             json.dumps(b.events), json.dumps(search.evidence),
                             json.dumps(followed.evidence)))
        self.assertNotIn(SECRET, exposed)
        self.assertIn("x-typesense-api-key=REDACTED", exposed)
        self.assertIn("token=REDACTED", exposed)
        self.assertIn("q=9110", exposed)

if __name__ == "__main__":
    unittest.main()
