"""B6: temporary private access through an authenticated tunnel (FAKE/offline: routing and auth only; no tunnel,
no network). Proves: exact public origin, anonymous denial (static included), single-use expiring link, replay and
brute-force refusal, Secure cookie, Origin required for state changes, expiring sessions and a hard access deadline."""
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    import httpx  # noqa: F401
    from rightware.gui import auth as A
    from rightware.gui import policy as P
    from tests.test_ui01_gui import Inner, call, run
except ImportError:
    P = None

PORT = 8000
PUB = "https://abc123x-8000.euw.devtunnels.ms"
PUB_HOST = (b"host", b"abc123x-8000.euw.devtunnels.ms")
LOOP_HOST = (b"host", b"127.0.0.1:8000")
ORIGIN = (b"origin", PUB.encode())
TOKEN = "tok-" + "y" * 30


async def confirm_login(app, token, host, origin=(b"origin", PUB.encode())):
    """ID01-A two-step login used by tests: GET (confirmation, nothing consumed) → explicit POST (consumes).
    Returns (final status, sent messages of the last step, GET status)."""
    import re as _re

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    got = []

    async def send(m):
        got.append(m)
    await app({"type": "http", "method": "GET", "path": "/rw-login", "raw_path": b"/rw-login",
               "query_string": f"t={token}".encode(), "headers": [host]}, receive, send)
    if got[0]["status"] != 200:
        return got[0]["status"], got, got[0]["status"]
    cookie = dict(got[0]["headers"])[b"set-cookie"].split(b";")[0]
    csrf = _re.search(rb'name="csrf" value="([^"]+)"', got[1]["body"]).group(1)
    body = b"csrf=" + csrf
    sent = []

    async def receive2():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send2(m):
        sent.append(m)
    await app({"type": "http", "method": "POST", "path": "/rw-login", "raw_path": b"/rw-login", "query_string": b"",
               "headers": [host, origin, (b"cookie", cookie), (b"content-type", b"application/x-www-form-urlencoded"),
                           (b"content-length", str(len(body)).encode())]}, receive2, send2)
    return sent[0]["status"], sent, 200


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@unittest.skipIf(P is None, "pinned OpenJarvis venv required")
class PrivateAccess(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "static/assets").mkdir(parents=True)
        (self.tmp / "static/index.html").write_text("<html>JARVIS</html>")
        (self.tmp / "static/assets/app.js").write_text("js")
        self.clock = Clock()
        self.auth = A.LocalAuth(TOKEN, single_use=True, token_ttl=900, session_ttl=3600, max_failures=5,
                                clock=self.clock)
        self.inner, self.bridge = Inner(), Inner()
        self.app = P.PolicyApp(inner=self.inner, bridge=self.bridge, static_dir=self.tmp / "static", port=PORT,
                               audit=P.AuditLog(self.tmp / "audit.jsonl"), auth=self.auth, public_origin=PUB,
                               public_until=self.clock.t + 3600, clock=self.clock)

    def login(self, token=TOKEN, host=PUB_HOST):
        status, _, _, sent = run(self._login(token, host))
        return status, sent

    async def _login(self, token, host):
        status, sent, _ = await confirm_login(self.app, token, host)
        return status, None, None, sent

    def session(self):
        status, sent = self.login()
        self.assertEqual(status, 303)
        return dict(sent[0]["headers"])[b"set-cookie"]

    def test_public_origin_must_be_exact_https(self):
        for bad in ("http://x.devtunnels.ms", "https://x.devtunnels.ms/", "https://x.devtunnels.ms:443",
                    "https://*.devtunnels.ms", "https://X.devtunnels.ms", "https://user@x.devtunnels.ms",
                    "https://localhost", "https://a.local", "https://x.devtunnels.ms/path", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                P.parse_public_origin(bad)
        with self.assertRaises(ValueError):
            P.PolicyApp(inner=Inner(), bridge=Inner(), static_dir=None, port=PORT, audit=P.AuditLog(self.tmp / "a"),
                        auth=None, public_origin=PUB, public_until=1.0)

    def test_anonymous_is_denied_everywhere_including_static(self):
        for host in (PUB_HOST, LOOP_HOST):            # also if the relay rewrites Host to loopback
            for path in ("/", "/dashboard", "/index.html", "/assets/app.js", "/v1/rightware/state", "/v1/info"):
                with self.subTest(host=host, path=path):
                    self.assertIn(run(call(self.app, "GET", path, headers=[host]))[0], (401, 403))
        self.assertEqual(run(call(self.app, "GET", "/", headers=[(b"host", b"evil.example.com")]))[0], 403)
        self.assertEqual(self.inner.calls + self.bridge.calls, [])

    def test_single_use_link_secure_cookie_and_replay(self):
        cookie = self.session()
        for attr in (b"HttpOnly", b"SameSite=Strict", b"Secure", b"Max-Age=3600", b"Path=/"):
            self.assertIn(attr, cookie)
        sid = cookie.split(b";")[0]
        self.assertEqual(run(call(self.app, "GET", "/assets/app.js", headers=[PUB_HOST, (b"cookie", sid)]))[0], 200)
        self.assertEqual(run(call(self.app, "GET", "/v1/rightware/state", headers=[PUB_HOST, (b"cookie", sid)]))[0], 200)
        self.assertEqual(self.login()[0], 403)                         # replay of the used link
        self.assertEqual(run(call(self.app, "POST", "/v1/agents", headers=[PUB_HOST, (b"cookie", sid), ORIGIN]))[0], 403)

    def test_link_expires_and_brute_force_locks(self):
        self.clock.t += 901
        self.assertEqual(self.login()[0], 403)                         # expired link
        auth = A.LocalAuth(TOKEN, single_use=True, token_ttl=900, max_failures=3, clock=self.clock)
        for _ in range(3):
            self.assertIsNone(auth.login("wrong"))
        self.assertIsNone(auth.login(TOKEN))                           # locked even with the right token

    def test_state_changes_need_the_exact_origin(self):
        sid = self.session().split(b";")[0]
        url = "/v1/rightware/tasks/cancel"
        self.assertEqual(run(call(self.app, "POST", url, headers=[PUB_HOST, (b"cookie", sid)]))[1].count(b"ORIGIN_REQUIRED"), 1)
        evil = (b"origin", b"https://evil.example.com")
        self.assertIn(b"CROSS_ORIGIN", run(call(self.app, "POST", url, headers=[PUB_HOST, (b"cookie", sid), evil]))[1])
        loop = (b"origin", b"http://127.0.0.1:8000")
        self.assertIn(b"CROSS_ORIGIN", run(call(self.app, "POST", url, headers=[PUB_HOST, (b"cookie", sid), loop]))[1])
        self.assertEqual(run(call(self.app, "POST", url, headers=[PUB_HOST, (b"cookie", sid), ORIGIN]))[0], 200)

    def test_sessions_expire_and_access_has_a_hard_deadline(self):
        sid = self.session().split(b";")[0]
        self.clock.t += 3599
        self.assertEqual(run(call(self.app, "GET", "/v1/info", headers=[PUB_HOST, (b"cookie", sid)]))[0], 200)
        self.clock.t += 2
        status, body, _, _ = run(call(self.app, "GET", "/v1/info", headers=[PUB_HOST, (b"cookie", sid)]))
        self.assertEqual(status, 403)
        self.assertIn(b"PUBLIC_ACCESS_EXPIRED", body)
        self.assertEqual(self.auth._sessions, {})                      # revoked
        self.assertEqual(run(call(self.app, "GET", "/", headers=[LOOP_HOST]))[0], 403)

    def test_websocket_and_inner_routes_stay_denied(self):
        sid = self.session().split(b";")[0]
        self.assertEqual(run(call(self.app, "GET", "/ws", headers=[PUB_HOST, (b"cookie", sid)], kind="websocket"))[2], 1008)
        self.assertEqual(run(call(self.app, "GET", "/v1/agents", headers=[PUB_HOST, (b"cookie", sid)]))[0], 403)

    def test_login_token_never_reaches_the_audit_log(self):
        self.login("wrong-token-value")
        self.session()
        text = (self.tmp / "audit.jsonl").read_text()
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("wrong-token-value", text)

    def test_local_mode_is_unchanged(self):
        auth = A.LocalAuth(TOKEN)
        self.assertIsNotNone(auth.login(TOKEN))
        self.assertIsNotNone(auth.login(TOKEN))                        # reusable locally, as in UI-02
        self.assertNotIn(b"Secure", auth.cookie_header("s"))
        path = self.tmp / "u"
        self.assertTrue(auth.write_url(path, PORT, base=PUB).startswith(PUB + "/rw-login?t="))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
