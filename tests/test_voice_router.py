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
        from tests.test_b6_private_access import confirm_login
        _, sent, _ = run(confirm_login(app, TOKEN, PUB_HOST))
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




class HostLabels(unittest.TestCase):
    def test_imitated_host_annotations_are_removed_and_attribute_is_line_local(self):
        from labs.presentation.serve import strip_imitated
        from labs.f01.integrity import check
        from tests.test_f01_fx import tool
        txt = ("Compra: 71,02 MT\nFonte: https://www.bancomoc.mz/x.pdf — dados de 2031-03-10\n"
               "✓ Verificação do anfitrião: 3 valor(es) financeiro(s) conferem com o registo.")
        clean, n = strip_imitated(txt)
        self.assertEqual((clean, n), ("Compra: 71,02 MT", 2))
        r = [tool()("USD", "MZN")]
        self.assertEqual(check("**Taxa média:** 72,44 MT\n**Compra:** 71,02 MT", r)["issues"][0]["problem"],
                         "WRONG_ATTRIBUTE_OR_CURRENCY")                       # 72,44 is the sell rate, not the mid


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(P is None, "pinned OpenJarvis venv required")
class VoiceSpeed(unittest.TestCase):
    """The approved profile speed reaches every synthesis that goes through the upstream route (greeting, progressive
    sentences, 'ouvir'), and the phrase cache is keyed by speed (an old 1.00 entry is never served at 1.15). FAKE engine."""

    def test_profile_speed_applies_and_cache_is_keyed_by_speed(self):
        from rightware.gui import voice as V
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        saved = (V.PROFILE, V.CACHE_DIR)
        self.addCleanup(lambda: (setattr(V, "PROFILE", saved[0]), setattr(V, "CACHE_DIR", saved[1])))
        V.CACHE_DIR = tmp / "cache"
        V.PROFILE = tmp / "profile.json"
        calls = []

        class Eng:
            def create(self, text, voice, speed, lang):
                import numpy as np
                calls.append(speed)
                return np.zeros(240, dtype="float32"), 24000

            def get_voices(self):
                return ["pf_dora"]

        def write(speed):
            V.PROFILE.write_text(json.dumps({"voice": {"voice_id": "pf_dora", "status": "APROVADA", "speed": speed}}))

        tts = V.make_tts()
        tts._engine = lambda: Eng()
        write(1.0)
        self.assertEqual(tts.synthesize("Boa noite, Issa.").metadata["cache"], "miss")
        write(1.15)
        r = tts.synthesize("Boa noite, Issa.")                 # same text, new speed: NOT the cached 1.00 audio
        self.assertEqual(r.metadata["cache"], "miss")
        self.assertEqual(calls, [1.0, 1.15])
        self.assertEqual(tts.synthesize("Boa noite, Issa.").metadata["cache"], "hit")
        tts.synthesize("Frase explícita.", speed=1.3)          # an explicit non-default request is honoured
        self.assertEqual(calls[-1], 1.3)
        write(9.0)                                              # out of range → safe default 1.0
        tts.synthesize("Outra frase.")
        self.assertEqual(calls[-1], 1.0)

    def test_repository_profile_is_dora_at_1_15(self):
        d = json.loads((Path(__file__).resolve().parents[1] / "configs" / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual((d["voice"]["voice_id"], d["voice"]["status"], d["voice"]["speed"]), ("pf_dora", "APROVADA", 1.15))
