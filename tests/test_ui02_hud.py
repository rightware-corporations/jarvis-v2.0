"""UI-02: HUD backend (local auth, explicit sessions, cancellation, structured state, mission API, audit rotation,
model-tap thread pinning, overlay manifest drift). FAKE/offline: fake text model and fake executor; no Docker/model.
Real-browser and real-model evidence lives in docs/evidence/ui02/."""
import asyncio
import json
import re
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
try:
    import httpx  # noqa: F401
    from rightware import control_plane as CP
    from rightware.console import build
    from rightware.gui import auth as A
    from rightware.gui import bridge as B
    from rightware.gui import policy as P
    from rightware.gateway import model_tap as MT
    from rightware.text_facade import TextFacade
    from tests.test_ui01_gui import FakeMission, Inner, TextModel, call, run
except ImportError:
    CP = None

PORT = 8000
HOST = (b"host", f"127.0.0.1:{PORT}".encode())


class SlowModel(TextModel):
    """Blocks until aborted (FAKE): stands in for a long local generation."""

    def __init__(self):
        super().__init__()
        self.aborted = threading.Event()
        self.started = threading.Event()

    def reply(self, text, history):
        self.seen.append((text, tuple(history)))
        if text.startswith("longo"):
            self.started.set()
            if not self.aborted.wait(10):
                return "não devia chegar aqui"
            raise ConnectionError("engine closed by abort")
        return f"rápido: {text}"

    def abort(self):
        self.aborted.set()
        return True


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class LocalAuthPolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "static/assets").mkdir(parents=True)
        (self.tmp / "static/index.html").write_text("<html>JARVIS</html>")
        (self.tmp / "static/assets/app.js").write_text("js")
        self.auth = A.LocalAuth("tok-" + "x" * 30)
        self.inner, self.bridge = Inner(), Inner()
        self.app = P.PolicyApp(inner=self.inner, bridge=self.bridge, static_dir=self.tmp / "static", port=PORT,
                               audit=P.AuditLog(self.tmp / "audit.jsonl"), auth=self.auth)

    async def _login(self, token):
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(m):
            sent.append(m)
        await self.app({"type": "http", "method": "GET", "path": "/rw-login", "raw_path": b"/rw-login",
                        "query_string": f"t={token}".encode(), "headers": [HOST]}, receive, send)
        return sent[0]["status"], b"", None, sent

    def test_api_and_pages_require_the_local_session(self):
        self.assertEqual(run(call(self.app, "GET", "/v1/rightware/state", headers=[HOST]))[0], 401)
        self.assertEqual(run(call(self.app, "POST", "/v1/chat/completions", headers=[HOST]))[0], 401)
        status, body, _, _ = run(call(self.app, "GET", "/", headers=[HOST]))
        self.assertEqual(status, 401)
        self.assertIn(b"Sess\xc3\xa3o local necess\xc3\xa1ria", body)
        self.assertEqual(run(call(self.app, "GET", "/assets/app.js", headers=[HOST]))[0], 200)   # public bundle
        self.assertEqual(self.inner.calls + self.bridge.calls, [])

    def test_login_sets_a_strict_cookie_and_unlocks_the_allowlist_only(self):
        status, _, _, sent = run(self._login("errado"))
        self.assertEqual(status, 403)
        status, _, _, sent = run(self._login("tok-" + "x" * 30))
        self.assertEqual(status, 303)
        headers = dict(sent[0]["headers"])
        cookie = headers[b"set-cookie"]
        self.assertIn(b"HttpOnly", cookie)
        self.assertIn(b"SameSite=Strict", cookie)
        sid = cookie.split(b";")[0]
        hdrs = [HOST, (b"cookie", sid)]
        self.assertEqual(run(call(self.app, "GET", "/v1/rightware/state", headers=hdrs))[0], 200)
        self.assertEqual(run(call(self.app, "GET", "/", headers=hdrs))[1], b"<html>JARVIS</html>")
        self.assertEqual(run(call(self.app, "POST", "/v1/agents", headers=hdrs))[0], 403)       # still denied
        self.assertEqual(run(call(self.app, "GET", "/v1/info", headers=[HOST, (b"cookie", b"rw_session=forged")]))[0], 401)
        self.assertEqual(run(call(self.app, "GET", "/v1/info", headers=[HOST, (b"cookie", sid + b"; " + sid)]))[0], 401)

    def test_session_url_file_is_private(self):
        path = self.tmp / "session-url"
        url = self.auth.write_url(path, PORT)
        self.assertTrue(url.startswith("http://127.0.0.1:8000/rw-login?t="))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_audit_rotates_by_size(self):
        log = P.AuditLog(self.tmp / "a.jsonl", max_bytes=200, keep=2)
        for _ in range(30):
            log.record("http", "GET", "/x", "DENY", "TEST")
        self.assertTrue((self.tmp / "a.jsonl.1").exists())
        self.assertTrue((self.tmp / "a.jsonl.2").exists())
        self.assertFalse((self.tmp / "a.jsonl.3").exists())
        self.assertLess((self.tmp / "a.jsonl").stat().st_size, 400)


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class HudBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.mission = FakeMission()
        self.model = SlowModel()
        self.cp = CP.ControlPlane(TextFacade(adapter=self.model), goose=self.mission)
        self.addCleanup(self.cp.close)
        self.bridge = B.ChatBridge(entries={"qwen3.5:2b": self.cp.entry}, default_model="qwen3.5:2b", control=self.cp,
                                   audit=P.AuditLog(self.tmp / "audit.jsonl"))
        mock.patch.object(B.ChatBridge, "installed_models", return_value={"qwen3.5:2b"}).start()
        self.addCleanup(mock.patch.stopall)

    def api(self, method, path, body=None, headers=()):
        status, data, _, _ = run(call(self.bridge, method, path, body=json.dumps(body).encode() if body is not None else b"",
                                      headers=[HOST, *headers]))
        return status, json.loads(data)

    def test_state_reports_real_capabilities_and_never_the_code(self):
        status, st = self.api("GET", "/v1/rightware/state")
        self.assertEqual(status, 200)
        caps = {c["id"]: c["status"] for c in st["capabilities"]}
        self.assertEqual(caps["missao-sintetica"], "INTEGRADA")
        self.assertEqual((caps["voz"], caps["inteligencia-financeira"], caps["internet-publica"]),
                         ("NAO_INTEGRADA", "NAO_INTEGRADA", "BLOQUEADA"))
        status, req = self.api("POST", "/v1/rightware/tasks/request", {"capability": "missao-sintetica"})
        self.assertEqual(req["state"], "AUTORIZACAO_NECESSARIA")
        st = self.api("GET", "/v1/rightware/state")[1]
        self.assertEqual(st["pending"]["capability"], "missao-sintetica")
        self.assertNotIn(req["code"], json.dumps(st))                         # the code never leaks via state

    def test_mission_api_authorises_only_with_the_code(self):
        self.assertEqual(self.api("POST", "/v1/rightware/tasks/authorize", {})[0], 400)
        self.assertEqual(self.api("POST", "/v1/rightware/tasks/authorize", {"approve": True})[0], 400)
        self.assertEqual(self.mission.started, 0)
        code = self.api("POST", "/v1/rightware/tasks/request", {"capability": "missao-sintetica"})[1]["code"]
        status, out = self.api("POST", "/v1/rightware/tasks/authorize", {"code": code})
        self.assertIn("Tarefa em execução", out["text"])
        self.assertTrue(out["hud"]["task"]["running"])
        self.assertEqual(out["hud"]["task"]["capability"], "missao-sintetica")
        self.mission.release.set()
        for _ in range(200):
            if not self.bridge.task_thread.is_alive():
                break
            time.sleep(0.02)
        last = self.api("GET", "/v1/rightware/state")[1]["last"]
        self.assertEqual((last["state"], last["verified"]), ("RESULTADO_VERIFICADO", True))
        self.assertEqual([r["tool"] for r in last["receipts"]], ["web_open", "submit_report"])
        self.assertEqual(last["commentary_unverified"], "Relatório: TerraLens")

    def test_mission_cancel_through_the_control_plane(self):
        code = self.api("POST", "/v1/rightware/tasks/request", {"capability": "missao-sintetica"})[1]["code"]
        self.api("POST", "/v1/rightware/tasks/authorize", {"code": code})
        self.assertEqual(self.api("POST", "/v1/rightware/tasks/cancel", {})[1]["state"], "CANCELAMENTO_PEDIDO")
        for _ in range(200):
            if not self.bridge.task_thread.is_alive():
                break
            time.sleep(0.02)
        self.assertEqual(self.api("GET", "/v1/rightware/state")[1]["last"]["state"], "TAREFA_CANCELADA")

    def test_client_disconnect_aborts_the_generation_and_frees_the_model(self):
        sent = []
        body = json.dumps({"model": "qwen3.5:2b", "stream": True,
                           "messages": [{"role": "user", "content": "longo pedido"}]}).encode()
        msgs = [{"type": "http.request", "body": body, "more_body": False}]

        async def scenario():
            gone = asyncio.Event()

            async def receive():
                if msgs:
                    return msgs.pop(0)
                await gone.wait()
                return {"type": "http.disconnect"}

            async def send(m):
                sent.append(m)
            req = asyncio.ensure_future(self.bridge({"type": "http", "method": "POST", "path": "/v1/chat/completions",
                                                     "headers": [HOST]}, receive, send))
            await asyncio.to_thread(self.model.started.wait, 5)
            t0 = time.monotonic()
            gone.set()                                           # the user pressed Stop / closed the tab
            await asyncio.wait_for(req, 5)
            return time.monotonic() - t0
        elapsed = run(scenario())
        self.assertTrue(self.model.aborted.is_set())
        self.assertLess(elapsed, 3)
        audit = (self.tmp / "audit.jsonl").read_text()
        self.assertIn("CANCELLED_BY_CLIENT", audit)
        t0 = time.monotonic()
        status, data, _, _ = run(call(self.bridge, "POST", "/v1/chat/completions", headers=[HOST], body=json.dumps(
            {"model": "qwen3.5:2b", "stream": False, "messages": [{"role": "user", "content": "curto"}]}).encode()))
        self.assertIn("rápido: curto", json.loads(data)["choices"][0]["message"]["content"])
        self.assertLess(time.monotonic() - t0, 2)

    def test_explicit_conversation_ids_isolate_sessions(self):
        def say(conv, text, auth="s1"):
            body = json.dumps({"model": "qwen3.5:2b", "stream": False,
                               "messages": [{"role": "user", "content": text}]}).encode()
            scope_headers = [HOST, (b"x-rightware-conversation", conv.encode())]
            return run(self._call_with_session(body, scope_headers, auth))
        say("conv-aaaaaaaa", "um")
        say("conv-aaaaaaaa", "dois")
        self.assertEqual(self.model.seen[-1][1], (("user", "um"), ("assistant", "rápido: um")))
        say("conv-bbbbbbbb", "três")
        self.assertEqual(self.model.seen[-1][1], ())
        say("conv-aaaaaaaa", "quatro", auth="s2")                 # same id, another local session: isolated
        self.assertEqual(self.model.seen[-1][1], ())

    async def _call_with_session(self, body, headers, auth):
        sent = []
        msgs = [{"type": "http.request", "body": body, "more_body": False}]

        async def receive():
            if msgs:
                return msgs.pop(0)
            await asyncio.Event().wait()

        async def send(m):
            sent.append(m)
        await self.bridge({"type": "http", "method": "POST", "path": "/v1/chat/completions", "headers": headers,
                           "rightware.session": auth}, receive, send)
        return sent


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class ModelTapThreadPinning(unittest.TestCase):
    def test_chat_requests_are_forwarded_to_the_pinned_derived_model(self):
        created = []
        ensure = lambda base, derived: created.append((base, derived)) or True
        body = json.dumps({"model": "qwen3.5:4b", "messages": []}).encode()
        new, info = MT.pin_threads("/v1/chat/completions", body, 3, ensure)
        self.assertEqual(json.loads(new)["model"], "qwen3.5:4b-rw-t3")
        self.assertEqual(info, {"num_thread_pinned": 3, "model_forwarded": "qwen3.5:4b-rw-t3"})
        self.assertEqual(created, [("qwen3.5:4b", "qwen3.5:4b-rw-t3")])
        self.assertEqual(MT.pin_threads("/api/show", body, 3, ensure), (body, {}))
        self.assertEqual(MT.pin_threads("/v1/chat/completions", b"{bad", 3, ensure), (b"{bad", {}))
        new, info = MT.pin_threads("/v1/chat/completions", body, 3, lambda b, d: False)
        self.assertEqual((json.loads(new)["model"], info["num_thread_pinned"]), ("qwen3.5:4b", False))

    def test_adapter_passes_cores_minus_one(self):
        from rightware import goose_adapter as G
        r = G.DockerGooseRunner(G.GooseRuntime(Path("/g"), Path("/o"), Path("/m")), Path("/tmp/p2-x"),
                                mission_id="0a1b2c3d")
        tap = r.commands()["ollama-tap"]
        self.assertEqual(int(tap[tap.index("--num-thread") + 1]), max(1, (__import__("os").cpu_count() or 2) - 1))

    def test_cli_rejects_out_of_range(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            MT.main(["--upstream", "http://x:1", "--log", "/tmp/x.jsonl", "--num-thread", "0"])


if __name__ == "__main__":
    unittest.main()


VENDOR_FE = ROOT / "vendor/openjarvis/frontend"


@unittest.skipIf(CP is None or not VENDOR_FE.is_dir(), "pinned vendor checkout required")
class OverlayManifest(unittest.TestCase):
    """The HUD overlay must match the PINNED frontend exactly (drift fails here and in the build)."""

    def setUp(self):
        import hashlib
        self.sha = lambda p: hashlib.sha256((VENDOR_FE / p).read_bytes()).hexdigest()
        self.m = json.loads((ROOT / "rightware/gui/frontend/overlay.manifest.json").read_text())

    def test_pin_and_replaced_modules(self):
        from rightware.runtime import PIN
        self.assertEqual(self.m["pin"], PIN)
        self.assertGreaterEqual(len(self.m["replacements"]), 10)
        for r in self.m["replacements"]:
            with self.subTest(upstream=r["upstream"]):
                self.assertEqual(self.sha(r["upstream"]), r["sha256"])
                self.assertTrue((ROOT / "rightware/gui/frontend" / r["replacement"]).is_file())
                self.assertTrue(r["reason"])

    def test_string_patches_match_the_pinned_files_exactly(self):
        for s in self.m["strings"] + [self.m["html"]]:
            text = (VENDOR_FE / s["file"]).read_text()
            self.assertEqual(self.sha(s["file"]), s["sha256"])
            for it in s["items"]:
                with self.subTest(file=s["file"], find=it["find"][:40]):
                    self.assertEqual(text.count(it["find"]), it["count"])

    def test_replaced_tests_exist_upstream_and_overlay_has_no_vendor_writes(self):
        for t in self.m["replacedTests"]:
            self.assertTrue((VENDOR_FE / t).is_file(), t)
        cfg = (ROOT / "rightware/gui/frontend/vite.rightware.ts").read_text()
        self.assertIn("RIGHTWARE overlay drift", cfg)
        self.assertNotIn("writeFile", cfg)

    def test_no_simulated_data_in_hud_sources(self):
        src = ROOT / "rightware/gui/frontend/src"
        for f in list((src / "hud").glob("*.tsx")) + list((src / "overrides").glob("*.tsx")):
            if f.name.endswith(".test.tsx"):
                continue
            text = f.read_text()
            with self.subTest(file=f.name):
                self.assertNotRegex(text, r"Math\.random|setTimeout\([^)]*fake|mock", "no invented state in the HUD")


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class AbortableEngineClient(unittest.TestCase):
    """R-4 at the socket level: a request blocked waiting for the engine is interrupted by abort()."""

    def test_abort_interrupts_a_blocked_request(self):
        import http.server
        from rightware.text_adapter import abortable_client
        release = threading.Event()

        class Slow(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                release.wait(10)                          # an engine that is still generating
                try:
                    self.send_response(200)
                    self.end_headers()
                except OSError:
                    pass

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(release.set)
        client, backend = abortable_client(f"http://127.0.0.1:{srv.server_address[1]}", 30)
        box = {}

        def call():
            t0 = time.monotonic()
            try:
                client.post("/api/chat", json={})
                box["result"] = "completed"
            except Exception as exc:
                box["result"] = type(exc).__name__
            box["seconds"] = time.monotonic() - t0
        th = threading.Thread(target=call)
        th.start()
        time.sleep(0.5)
        self.assertEqual(backend.abort_all(), 1)
        th.join(3)
        self.assertFalse(th.is_alive())
        self.assertNotEqual(box["result"], "completed")
        self.assertLess(box["seconds"], 2)

    def test_adapter_abort_uses_the_socket_backend(self):
        from rightware.text_adapter import LocalSimpleTextAdapter
        a = LocalSimpleTextAdapter("qwen3.5:2b")
        calls = []
        a._abort_backend = mock.Mock(abort_all=lambda: calls.append(1) or 1)
        a._engine = mock.Mock()
        self.assertTrue(a.abort())
        self.assertEqual(calls, [1])
        self.assertIsNone(a._engine)
