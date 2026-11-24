"""OP01 — persona, tool-using chat adapter and live activity. UNIT/FAKE tests (scripted engine, offline fixture):
NOT evidence about Qwen, real Internet or real financial data."""
import json
import threading
import unittest

from rightware.persona import RuntimeFacts, system_prompt

try:
    from openjarvis.core.types import Role
    from labs.op01.fixture import fixture_fetcher, fixture_sites
    from rightware.assistant_tools import ToolChatAdapter
    from rightware.text_adapter import LocalSimpleTextAdapter
except Exception:                     # pragma: no cover - plain python without the pinned venv
    ToolChatAdapter = None


def call(name, args, cid=None):
    return {"tool_calls": [{"id": cid or f"c_{name}", "name": name, "arguments": json.dumps(args)}]}


class Scripted:
    """FAKE engine: returns the scripted steps in order and records the messages it was given."""
    engine_id = "fake"

    def __init__(self, steps, gate=None):
        self.steps, self.seen, self.gate = list(steps), [], gate

    def generate(self, messages, **kw):
        self.seen.append([(getattr(m, "role", None), getattr(m, "content", "")) for m in messages])
        if self.gate is not None:
            self.gate.wait(5)
        step = self.steps.pop(0) if self.steps else {"content": "Terminei."}
        out = {"content": step.get("content", ""), "usage": {}}
        if step.get("tool_calls"):
            out["tool_calls"] = step["tool_calls"]
        return out

    def close(self):
        pass


class Persona(unittest.TestCase):
    def test_identity_style_and_true_environment(self):
        p = system_prompt(RuntimeFacts(model="qwen3.5:2b", environment="cloud"))
        self.assertIn("O teu nome é JARVIS", p)
        self.assertIn("assistente pessoal do Issa", p)
        self.assertIn("não te apresentes como OpenJarvis, Qwen, RIGHTWARE", p)
        self.assertIn("português de Moçambique", p)
        self.assertIn("NÃO estás a correr no computador do utilizador", p)
        self.assertIn("nenhuma ferramenta nesta sessão", p)
        self.assertIn("não tens dados actuais", p)
        self.assertNotIn("You are OpenJarvis", p)

    def test_facts_are_declared_not_guessed(self):
        p = system_prompt(RuntimeFacts(model="m", environment="unknown", tools=("pesquisa",), sites=("a.example",)))
        self.assertIn("não sabes", p)
        self.assertIn("a.example", p)
        with self.assertRaises(ValueError):
            RuntimeFacts(model="m", environment="mars")


@unittest.skipIf(ToolChatAdapter is None, "pinned OpenJarvis venv required")
class SimpleAdapterPersona(unittest.TestCase):
    def test_persona_is_the_only_system_message(self):
        engine = Scripted([{"content": "Sou o JARVIS."}])
        a = LocalSimpleTextAdapter("qwen3.5:2b", engine_factory=lambda: engine,
                                   system_prompt=system_prompt(RuntimeFacts(model="qwen3.5:2b", environment="cloud")))
        self.assertEqual(a.reply("Quem és?", (("user", "Olá"), ("assistant", "Olá!"))), "Sou o JARVIS.")
        sent = engine.seen[0]
        systems = [c for r, c in sent if r == Role.SYSTEM]
        self.assertEqual(len(systems), 1)
        self.assertIn("JARVIS", systems[0])
        self.assertNotIn("OpenJarvis, a helpful", systems[0])          # upstream default NOT used
        self.assertEqual([r for r, _ in sent][1:], [Role.USER, Role.ASSISTANT, Role.USER])


@unittest.skipIf(ToolChatAdapter is None, "pinned OpenJarvis venv required")
class ToolChat(unittest.TestCase):
    P = system_prompt(RuntimeFacts(model="fake", environment="cloud", tools=("pesquisa",), sites=fixture_sites()
                                   if ToolChatAdapter else ()))

    def adapter(self, engine):
        return ToolChatAdapter("fake", sites=fixture_sites(), persona=self.P, browser_fetcher=fixture_fetcher(),
                               engine_factory=lambda: engine)

    def test_direct_answer_without_tools(self):
        engine = Scripted([{"content": "Bom dia, Issa."}])
        a = self.adapter(engine)
        out = a.reply("Bom dia", ())
        self.assertTrue(out.startswith("Bom dia, Issa."))
        self.assertEqual(a.activity()["last"]["tools"], [])
        self.assertEqual(a.activity()["phase"], "Resposta concluída")
        self.assertIn("JARVIS", engine.seen[0][0][1])                  # persona in the orchestrator system prompt
        self.assertIn("Só podes usar as ferramentas fornecidas", engine.seen[0][0][1])   # tool rules kept

    def test_model_selects_search_reads_and_cites_sources(self):
        engine = Scripted([call("web_open", {"url": "https://pesquisa.op01.example/search?q=moeda+Corvana"}),
                           call("web_open", {"url": "https://enciclopedia.op01.example/wiki/Corvana"}),
                           {"content": "A moeda de Corvana é a dracma corvanense (DRC)."}])
        a = self.adapter(engine)
        out = a.reply("Qual é a moeda de Corvana?", (("user", "Olá"), ("assistant", "Olá, Issa.")))
        self.assertIn("dracma corvanense", out)
        self.assertIn("Fontes lidas", out)
        self.assertIn("https://enciclopedia.op01.example/wiki/Corvana", out)
        self.assertEqual(a.activity()["last"]["completion"], "ANSWERED_WITH_SOURCES")
        roles = [r for r, _ in engine.seen[0]]
        self.assertEqual(roles[:4], [Role.SYSTEM, Role.USER, Role.ASSISTANT, Role.USER])   # history kept

    def test_host_outside_allowlist_refused_and_error_reported(self):
        engine = Scripted([call("web_open", {"url": "https://evil.example/"}),
                           call("web_open", {"url": "https://enciclopedia.op01.example/wiki/Arquivo"}),
                           {"content": "Não consegui obter a informação."}])
        a = self.adapter(engine)
        out = a.reply("Lê o arquivo de Corvana", ())
        self.assertNotIn("Fontes lidas", out)
        self.assertIn("respondeu HTTP 503", out)
        self.assertNotEqual(a.activity()["last"]["completion"], "ANSWERED_WITH_SOURCES")

    def test_live_activity_comes_from_the_policy_log(self):
        gate = threading.Event()
        engine = Scripted([call("web_open", {"url": "https://enciclopedia.op01.example/wiki/Tessar"}),
                           {"content": "Tessar foi fundada em 1488."}], gate=gate)
        a = self.adapter(engine)
        phases = []
        t = threading.Thread(target=lambda: a.reply("Quando foi fundada Tessar?", ()))
        t.start()
        phases.append(a.activity()["phase"])
        gate.set()
        t.join(10)
        phases.append(a.activity()["phase"])
        self.assertEqual(phases[0], "A interpretar")
        self.assertEqual(phases[-1], "Resposta concluída")
        self.assertEqual(a.activity()["last"]["tools"], ["web_open"])

    def test_host_built_search_tool(self):
        engine = Scripted([call("web_search", {"query": "Corvana mar"}), call("web_follow", {"link": "L1"}),
                           {"content": "Corvana fica no mar de Selmo."}])
        a = ToolChatAdapter("fake", sites=fixture_sites(), persona=self.P, browser_fetcher=fixture_fetcher(),
                            engine_factory=lambda: engine, search_template="https://pesquisa.op01.example/search?q={q}")
        out = a.reply("Em que mar fica Corvana?", ())
        self.assertIn("mar de Selmo", out)
        self.assertIn("https://enciclopedia.op01.example/wiki/Corvana", out)
        self.assertEqual(a.activity()["last"]["tools"], ["web_search", "web_follow"])
        with self.assertRaises(ValueError):                                  # template outside the allowlist
            ToolChatAdapter("fake", sites=fixture_sites(), persona=self.P, browser_fetcher=fixture_fetcher(),
                            engine_factory=lambda: Scripted([]), search_template="https://evil.example/?q={q}"
                            ).reply("x", ())

    def test_requires_allowlist(self):
        with self.assertRaises(ValueError):
            ToolChatAdapter("fake", sites=(), persona=self.P)


if __name__ == "__main__":
    unittest.main()
