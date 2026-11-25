"""VOICE & routing (UNIT/FAKE): voice routes only with --voz, body caps and Origin in public mode; model router
(fail-safe), direct conversation path and the ANSWERED_WITH_TOOLS state. Not evidence about Qwen, Whisper or Kokoro."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from rightware.gui import auth as A
    from rightware.gui import policy as P
    from tests.test_b6_private_access import Clock, ORIGIN, PUB, PUB_HOST, TOKEN
    from tests.test_ui01_gui import Inner, call, run
    from rightware.assistant_tools import ModelRouter, ToolChatAdapter
    from tests.test_op01 import Scripted, call as tcall
except ImportError:
    P = None


@unittest.skipIf(P is None, "pinned OpenJarvis venv required")
class VoicePolicy(unittest.TestCase):
    def app(self, voice):
        tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "static").mkdir(); (tmp / "static/index.html").write_text("x")
        clock = Clock()
        auth = A.LocalAuth(TOKEN, single_use=True, token_ttl=900, session_ttl=3600, max_failures=5, clock=clock)
        app = P.PolicyApp(inner=Inner(), bridge=Inner(), static_dir=tmp / "static", port=8000,
                          audit=P.AuditLog(tmp / "a.jsonl"), auth=auth, public_origin=PUB, public_until=clock.t + 3600,
                          clock=clock, allow={**P.ALLOW, **P.VOICE_ALLOW} if voice else None)
        sent = []

        async def login():
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(m):
                sent.append(m)
            await app({"type": "http", "method": "GET", "path": "/rw-login", "raw_path": b"/rw-login",
                       "query_string": f"t={TOKEN}".encode(), "headers": [PUB_HOST]}, receive, send)
        run(login())
        return app, dict(sent[0]["headers"])[b"set-cookie"].split(b";")[0]

    def test_voice_routes_only_with_voz_and_bounded(self):
        off, sid = self.app(voice=False)
        self.assertEqual(run(call(off, "GET", "/v1/speech/health", headers=[PUB_HOST, (b"cookie", sid)]))[0], 403)
        on, sid = self.app(voice=True)
        h = [PUB_HOST, (b"cookie", sid)]
        self.assertEqual(run(call(on, "GET", "/v1/speech/health", headers=h))[0], 200)
        ok = h + [ORIGIN, (b"content-length", b"1000")]
        self.assertEqual(run(call(on, "POST", "/v1/speech/transcribe", headers=ok))[0], 200)
        self.assertIn(b"BODY_TOO_LARGE", run(call(on, "POST", "/v1/speech/transcribe",
                                                   headers=h + [ORIGIN, (b"content-length", str(6 * 2**20).encode())]))[1])
        self.assertIn(b"BODY_TOO_LARGE", run(call(on, "POST", "/v1/speech/transcribe", headers=h + [ORIGIN]))[1])  # unsized
        self.assertIn(b"ORIGIN_REQUIRED", run(call(on, "POST", "/v1/speech/synthesize",
                                                    headers=h + [(b"content-length", b"10")]))[1])
        self.assertEqual(run(call(on, "GET", "/v1/speech/health", headers=[PUB_HOST]))[0], 401)   # anonymous
        self.assertIn(b"media-src 'self' blob:", P.CSP)


@unittest.skipIf(P is None, "pinned OpenJarvis venv required")
class Routing(unittest.TestCase):
    def test_router_is_model_decided_and_fail_safe(self):
        r = ModelRouter("m", "calc", call=lambda s, u: json.dumps({"rota": "conversa"}))
        self.assertEqual(r("Olá", ()), "conversa")
        self.assertEqual(ModelRouter("m", "calc", call=lambda s, u: "lixo")("x", ()), "ferramentas")
        self.assertEqual(ModelRouter("m", "calc", call=lambda s, u: json.dumps({"rota": "outra"}))("x", ()), "ferramentas")

        def boom(s, u):
            raise RuntimeError("down")
        self.assertEqual(ModelRouter("m", "calc", call=boom)("x", ()), "ferramentas")

    def test_direct_path_skips_tools_and_tool_success_is_not_a_failure(self):
        class Direct:
            def reply(self, text, history):
                return "Bom dia, Issa."
        engine = Scripted([])
        a = ToolChatAdapter("m", sites=(), persona="JARVIS", allow=("calc",), engine_factory=lambda: engine,
                            router=lambda t, h: "conversa", direct=Direct())
        self.assertEqual(a.reply("Bom dia", ()), "Bom dia, Issa.")
        self.assertEqual(engine.seen, [])                                       # tool engine never called
        self.assertEqual(a.activity()["last"]["completion"], "ANSWERED_DIRECT")
        from rightware.agent.policy import ToolDef
        from rightware.agent.session import ToolOutcome
        calc = ToolDef("calculator", "calc", {"expression": {"type": "string", "maxLength": 50}}, ("expression",),
                       session_flag="calc", consequential=False, max_calls=2)
        tools = lambda: ({"calculator": (calc, lambda a: ToolOutcome("calculator", "OK", "84.0", {}))}, lambda: [])  # noqa: E731
        engine2 = Scripted([tcall("calculator", {"expression": "12*7"}), {"content": "12 × 7 = 84."}])
        b = ToolChatAdapter("m", sites=(), persona="JARVIS", allow=("calc",), engine_factory=lambda: engine2,
                            extra_tools_factory=tools, router=lambda t, h: "ferramentas", direct=Direct())
        out = b.reply("Quanto é 12 vezes 7?", ())
        self.assertIn("84", out)
        self.assertNotIn("não foi possível concluir", out)                      # no contradictory state
        self.assertEqual(b.activity()["last"]["completion"], "ANSWERED_WITH_TOOLS")


if __name__ == "__main__":
    unittest.main()
