"""JRV-INT01 (UNIT/FAKE): ID01-A link confirmation (GET never consumes; explicit POST with exact Origin, challenge
cookie and CSRF consumes atomically; Origin null refused; replay/expiry), server-declared owners bound to sessions,
owner isolation of memory and documents through the REAL bridge routes, routes only with the capability, and the
Origin-null analysis of the Manus CROSS_ORIGIN failure. Not evidence about a real browser (see the E2E evidence)."""
import asyncio
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from labs.k01.fixtures import REPORT_2025, make_pdf
    from rightware.gui import auth as A
    from rightware.gui import bridge as B
    from rightware.gui import policy as P
    from rightware.knowledge.library import DocumentLibrary
    from rightware.knowledge.store import KnowledgeStore
    from rightware.memory.identity import SessionOwner
    from rightware.memory.personal import PersonalMemory
    from rightware.memory.store import MemoryStore
    from tests.test_b6_private_access import ORIGIN, PUB, PUB_HOST, TOKEN, Clock, confirm_login
    from tests.test_ui01_gui import Inner, call, run
except ImportError:
    P = None


@unittest.skipIf(P is None, "pinned OpenJarvis venv required")
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "static").mkdir()
        (self.tmp / "static/index.html").write_text("<html>JARVIS</html>")
        self.clock = Clock()
        self.auth = A.LocalAuth(TOKEN, single_use=True, token_ttl=900, session_ttl=3600, max_failures=20,
                                clock=self.clock, owner="lab:operador", label="operador")
        self.memory = PersonalMemory(MemoryStore(self.tmp / "m.sqlite3"), SessionOwner())
        self.docs = DocumentLibrary(KnowledgeStore(self.tmp / "k.sqlite3"), SessionOwner())
        from rightware.console import build
        from tests.test_ui01_gui import TextModel
        self.bridge = B.ChatBridge(entries={"m": build("m", TextModel(), 30.0)}, default_model="m",
                                   audit=P.AuditLog(None))
        self.bridge.memory, self.bridge.documents = self.memory, self.docs
        self.app = P.PolicyApp(inner=Inner(), bridge=self.bridge, static_dir=self.tmp / "static", port=8000,
                               audit=P.AuditLog(self.tmp / "audit.jsonl"), auth=self.auth, public_origin=PUB,
                               public_until=self.clock.t + 3600, clock=self.clock,
                               allow={**P.ALLOW, **P.DOCUMENT_ALLOW, **P.MEMORY_ALLOW})

    def get_login(self, token=TOKEN):
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(m):
            sent.append(m)
        run(self.app({"type": "http", "method": "GET", "path": "/rw-login", "raw_path": b"/rw-login",
                      "query_string": f"t={token}".encode(), "headers": [PUB_HOST]}, receive, send))
        return sent

    def post_login(self, cookie, csrf, origin=ORIGIN):
        body = b"csrf=" + csrf
        hdrs = [PUB_HOST, (b"content-type", b"application/x-www-form-urlencoded"),
                (b"content-length", str(len(body)).encode())] + ([origin] if origin else []) + \
               ([(b"cookie", cookie)] if cookie else [])
        sent = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(m):
            sent.append(m)
        run(self.app({"type": "http", "method": "POST", "path": "/rw-login", "raw_path": b"/rw-login",
                      "query_string": b"", "headers": hdrs}, receive, send))
        return sent

    @staticmethod
    def parts(sent):
        cookie = dict(sent[0]["headers"])[b"set-cookie"].split(b";")[0]
        csrf = re.search(rb'name="csrf" value="([^"]+)"', sent[1]["body"]).group(1)
        return cookie, csrf

    def session_for(self, token=TOKEN):
        status, sent, _ = run(confirm_login(self.app, token, PUB_HOST))
        self.assertEqual(status, 303)
        return dict(sent[0]["headers"])[b"set-cookie"].split(b";")[0]


class ConfirmFlow(Base):
    def test_get_never_consumes_and_page_is_safe(self):
        for _ in range(3):                                         # previews / prefetch / repeated GET
            sent = self.get_login()
            self.assertEqual(sent[0]["status"], 200)
        self.assertFalse(self.auth.consumed)
        h = dict(sent[0]["headers"])
        self.assertEqual(h[b"referrer-policy"], b"strict-origin")  # not no-referrer (would give Origin: null)
        self.assertEqual(h[b"cache-control"], b"no-store")
        self.assertIn(b"form-action 'self'", h[b"content-security-policy"])
        for attr in (b"HttpOnly", b"Secure", b"SameSite=Strict", b"Path=/rw-login", b"Max-Age=300"):
            self.assertIn(attr, h[b"set-cookie"])
        self.assertNotIn(TOKEN.encode(), sent[1]["body"])          # the link token never appears in the page
        self.assertNotIn(b"<script", sent[1]["body"])

    def test_post_consumes_atomically_and_replay_fails(self):
        cookie, csrf = self.parts(self.get_login())
        ok = self.post_login(cookie, csrf)
        self.assertEqual(ok[0]["status"], 303)
        self.assertIn(b"Secure", dict(ok[0]["headers"])[b"set-cookie"])
        self.assertTrue(self.auth.consumed)
        self.assertEqual(self.post_login(cookie, csrf)[0]["status"], 403)        # replayed challenge
        self.assertEqual(self.get_login()[0]["status"], 403)                     # used link

    def test_origin_null_missing_or_foreign_is_refused_without_consuming(self):
        cookie, csrf = self.parts(self.get_login())
        for origin, reason in (((b"origin", b"null"), "CROSS_ORIGIN"), (None, "ORIGIN_REQUIRED"),
                               ((b"origin", b"https://evil.example"), "CROSS_ORIGIN")):
            sent = self.post_login(cookie, csrf, origin)
            self.assertEqual(sent[0]["status"], 403)
            self.assertEqual(json.loads(sent[1]["body"])["reason"], reason)
        self.assertFalse(self.auth.consumed)

    def test_csrf_cookie_and_expiry_are_required(self):
        cookie, csrf = self.parts(self.get_login())
        self.assertEqual(self.post_login(None, csrf)[0]["status"], 403)          # no challenge cookie
        cookie, csrf = self.parts(self.get_login())
        self.assertEqual(self.post_login(cookie, b"wrong")[0]["status"], 403)    # wrong CSRF burns the challenge
        self.assertEqual(self.post_login(cookie, csrf)[0]["status"], 403)
        cookie, csrf = self.parts(self.get_login())
        self.clock.t += 301
        self.assertEqual(self.post_login(cookie, csrf)[0]["status"], 403)        # challenge expired
        self.assertFalse(self.auth.consumed)


class Identity(Base):
    def test_session_owner_comes_from_the_link_and_new_links_are_per_label(self):
        sid = self.session_for()
        self.assertEqual(self.auth.owner_of(sid.split(b"=", 1)[1].decode()), "lab:operador")
        tok = self.auth.issue("lab:issa", "issa")
        sid2 = self.session_for(tok)
        self.assertEqual(self.auth.owner_of(sid2.split(b"=", 1)[1].decode()), "lab:issa")

    def test_memory_and_documents_isolated_by_session_owner_through_bridge_routes(self):
        a = self.session_for()
        b = self.session_for(self.auth.issue("lab:issa", "issa"))
        body = make_pdf(REPORT_2025)
        st, raw, _, _ = run(call(self.app, "POST", "/v1/rightware/documents/upload", body=body, headers=[
            PUB_HOST, ORIGIN, (b"cookie", a), (b"x-rightware-filename", b"relatorio.pdf"),
            (b"x-rightware-owner", b"lab:issa"), (b"content-length", str(len(body)).encode())]))
        self.assertEqual(st, 200)
        self.assertEqual([d.owner for d in self.docs.store.list("lab:operador")], ["lab:operador"])
        self.assertEqual(self.docs.store.list("lab:issa"), [])                   # a header cannot pick the owner
        st, raw, _, _ = run(call(self.app, "GET", "/v1/rightware/documents", headers=[PUB_HOST, (b"cookie", b)]))
        self.assertEqual(json.loads(raw)["documents"], [])
        self.memory.store.add("lab:operador", "preferencia", "moeda", "Prefiro meticais", {})
        st, raw, _, _ = run(call(self.app, "GET", "/v1/rightware/memory", headers=[PUB_HOST, (b"cookie", b)]))
        self.assertEqual(json.loads(raw)["memories"], [])
        st, raw, _, _ = run(call(self.app, "GET", "/v1/rightware/memory", headers=[PUB_HOST, (b"cookie", a)]))
        mem = json.loads(raw)["memories"]
        self.assertEqual([m["content"] for m in mem], ["Prefiro meticais"])
        req = json.dumps({"memory_id": mem[0]["id"], "text": "Prefiro dólares"}).encode()
        st, _, _, _ = run(call(self.app, "POST", "/v1/rightware/memory/correct", body=req, headers=[
            PUB_HOST, ORIGIN, (b"cookie", b), (b"content-length", str(len(req)).encode())]))
        self.assertEqual(st, 404)                                                 # other owner cannot correct
        st, raw, _, _ = run(call(self.app, "POST", "/v1/rightware/memory/correct", body=req, headers=[
            PUB_HOST, ORIGIN, (b"cookie", a), (b"content-length", str(len(req)).encode())]))
        self.assertEqual((st, json.loads(raw)["content"]), (200, "Prefiro dólares"))
        bad = json.dumps({"memory_id": mem[0]["id"], "text": "a minha senha é abc123"}).encode()
        st, _, _, _ = run(call(self.app, "POST", "/v1/rightware/memory/correct", body=bad, headers=[
            PUB_HOST, ORIGIN, (b"cookie", a), (b"content-length", str(len(bad)).encode())]))
        self.assertEqual(st, 422)
        req = json.dumps({"memory_id": mem[0]["id"]}).encode()
        st, _, _, _ = run(call(self.app, "POST", "/v1/rightware/memory/delete", body=req, headers=[
            PUB_HOST, ORIGIN, (b"cookie", a), (b"content-length", str(len(req)).encode())]))
        self.assertEqual(st, 200)
        self.assertEqual(self.memory.store.active("lab:operador"), [])

    def test_long_ids_round_trip_through_bridge(self):
        from unittest.mock import patch
        from rightware.knowledge.ingest import extract
        a = self.session_for()
        b = self.session_for(self.auth.issue("lab:issa", "issa"))
        # Synthetic 32-hex IDs in real SQLite fixtures mirror DB01 format, not a live PG test.
        with patch("rightware.memory.store.secrets.token_hex", return_value="a" * 32):
            mem, _ = self.memory.store.add("lab:operador", "preferencia", "moeda", "Meticais", {})
        with patch("rightware.knowledge.store.secrets.token_hex", return_value="b" * 32):
            doc, _ = self.docs.store.add("lab:operador", extract("synthetic.txt", b"Resultado 96"), False)
        self.assertEqual((len(mem.id), len(doc.id)), (34, 34))

        def post(path, payload, cookie):
            req = json.dumps(payload).encode()
            return run(call(self.app, "POST", path, body=req, headers=[
                PUB_HOST, ORIGIN, (b"cookie", cookie), (b"content-length", str(len(req)).encode())]))[0]

        correct = "/v1/rightware/memory/correct"
        forget = "/v1/rightware/memory/delete"
        delete = "/v1/rightware/documents/delete"
        self.assertEqual(post(correct, {"memory_id": mem.id, "text": "Dólares"}, b), 404)
        self.assertEqual(post(delete, {"document_id": doc.id}, b), 404)
        self.assertEqual(post(correct, {"memory_id": mem.id + "x", "text": "Dólares"}, a), 400)
        self.assertEqual(post(delete, {"document_id": doc.id + "x"}, a), 400)
        self.assertEqual(post(correct, {"memory_id": mem.id, "text": "Dólares"}, a), 200)
        self.assertEqual(self.memory.store.get("lab:operador", mem.id).content, "Dólares")
        self.assertEqual(post(forget, {"memory_id": mem.id}, a), 200)
        self.assertEqual(post(delete, {"document_id": doc.id}, a), 200)
        self.assertIsNone(self.memory.store.get("lab:operador", mem.id))
        self.assertIsNone(self.docs.store.get("lab:operador", doc.id))

    def test_routes_exist_only_with_the_capability_and_need_a_session(self):
        app = P.PolicyApp(inner=Inner(), bridge=self.bridge, static_dir=self.tmp / "static", port=8000,
                          audit=P.AuditLog(None), auth=self.auth, public_origin=PUB,
                          public_until=self.clock.t + 3600, clock=self.clock)
        self.assertEqual(run(call(app, "GET", "/v1/rightware/documents", headers=[PUB_HOST]))[0], 403)
        self.assertEqual(run(call(self.app, "GET", "/v1/rightware/documents", headers=[PUB_HOST]))[0], 401)
        self.assertEqual(run(call(self.app, "GET", "/v1/rightware/memory", headers=[PUB_HOST]))[0], 401)

    def test_unsized_or_oversized_upload_is_refused_by_the_gateway(self):
        a = self.session_for()
        st, _, _, _ = run(call(self.app, "POST", "/v1/rightware/documents/upload", body=b"x", headers=[
            PUB_HOST, ORIGIN, (b"cookie", a), (b"x-rightware-filename", b"a.txt")]))
        self.assertEqual(st, 413)                                                 # no Content-Length
        st, _, _, _ = run(call(self.app, "POST", "/v1/rightware/documents/upload", body=b"x", headers=[
            PUB_HOST, ORIGIN, (b"cookie", a), (b"content-length", str(6 * 1024 * 1024).encode())]))
        self.assertEqual(st, 413)


if __name__ == "__main__":
    unittest.main()
