"""WORK-05 R1-C/R1-D: session-level correctness and truthful completion.
Real OrchestratorAgent + scripted FAKE engine; no model, no network."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

try:
    from rightware.agent import session as S
except ImportError:
    S = None
from rightware.agent import web as W


def call(name, args, cid=None):
    return {"tool_calls": [{"id": cid or f"c_{name}", "name": name, "arguments": json.dumps(args)}]}


class Scripted:
    engine_id = "fake"

    def __init__(self, steps):
        self.steps, self.i = list(steps), 0

    def generate(self, messages, **kw):
        if self.i >= len(self.steps):
            return {"content": "Terminei.", "usage": {}}
        step = self.steps[self.i]
        self.i += 1
        out = {"content": step.get("content", ""), "usage": {}}
        if step.get("tool_calls"):
            out["tool_calls"] = step["tool_calls"]
        return out


class Fetcher:
    def __init__(self, page=None, exc=None, side_effect=None):
        self.page, self.exc, self.side_effect, self.calls = page, exc, side_effect, []

    def fetch(self, url):
        self.calls.append(url)
        if self.side_effect:
            self.side_effect()
        if self.exc:
            raise self.exc
        return self.page or W.Page(url, url, 200, "text/html", "Conteúdo útil.", "b" * 64, False)


@unittest.skipIf(S is None, "needs the pinned OpenJarvis venv (product CI job)")
class SessionR1(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_session(self, steps, allow=frozenset({"web"}), fetcher=None, audit=None):
        self.fetcher = fetcher or Fetcher()
        return S.AgentSession(Scripted(steps), "fake", allow=set(allow), confirm=lambda q: "sim",
                              fetcher=self.fetcher, audit_path=audit).run("pedido")

    # -- R1-C -------------------------------------------------------------------
    def test_only_refused_tools_is_not_an_answered_success(self):
        r = self.run_session([call("windows_action", {"action_id": "notepad"}), {"content": "Não foi possível."}])
        self.assertEqual(r.completion, "TOOLS_REFUSED")
        self.assertIn("TOOL_REFUSALS", r.flags)

    def test_full_batch_prevalidation_through_the_orchestrator(self):
        batch = {"tool_calls": [{"id": "a", "name": "web_read", "arguments": json.dumps({"url": "https://e.org"})},
                                {"id": "b", "name": "windows_action", "arguments": json.dumps({"action_id": "notepad"})}]}
        r = self.run_session([batch, {"content": "Nada."}])
        self.assertEqual(self.fetcher.calls, [])
        self.assertEqual(r.completion, "TOOLS_REFUSED")

    def test_audit_unavailable_before_execution_means_nothing_runs(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("x")
        r = self.run_session([call("web_read", {"url": "https://e.org"}), {"content": "Ok."}],
                             audit=blocker / "agent.jsonl")
        self.assertEqual(self.fetcher.calls, [])
        self.assertEqual(r.completion, "ERROR")
        self.assertIn("AUDIT_FAILED", r.flags)

    def test_audit_lost_after_execution_is_an_error_not_a_success(self):
        path = self.tmp / "agent.jsonl"

        def break_audit():
            path.unlink(missing_ok=True)
            path.mkdir()
        r = self.run_session([call("web_read", {"url": "https://e.org"}), {"content": "Segundo a página, ok."}],
                             fetcher=Fetcher(side_effect=break_audit), audit=path)
        self.assertEqual(len(self.fetcher.calls), 1)
        self.assertEqual(r.completion, "ERROR")
        self.assertIn("AUDIT_FAILED", r.flags)
        self.assertEqual(r.outcomes[0].evidence.get("audit"), "FAILED")

    # -- R1-D -------------------------------------------------------------------
    def test_http_error_is_not_a_source(self):
        for code in (404, 500, 403):
            with self.subTest(code=code):
                page = W.Page("https://e.org/x", "https://e.org/x", code, "text/html", "Not Found", "c" * 64, False)
                r = self.run_session([call("web_read", {"url": "https://e.org/x"}),
                                      {"content": "Segundo a página, o valor é 10."}], fetcher=Fetcher(page=page))
                self.assertEqual(r.outcomes[0].status, "HTTP_ERROR")
                self.assertEqual(r.sources, [])
                self.assertNotIn("Fontes lidas", r.text)
                self.assertIn(f"HTTP {code}", r.text)
                self.assertEqual(r.completion, "TOOLS_FAILED")
                self.assertIn("UNSUPPORTED_READ_CLAIM", r.flags)
                self.assertNotIn("Not Found", r.outcomes[0].content.split("HTTP")[0])

    def test_empty_page_is_not_a_source(self):
        page = W.Page("https://e.org", "https://e.org", 200, "text/html", "   ", "d" * 64, False)
        r = self.run_session([call("web_read", {"url": "https://e.org"}), {"content": "Nada encontrado."}],
                             fetcher=Fetcher(page=page))
        self.assertEqual(r.outcomes[0].status, "EMPTY_CONTENT")
        self.assertEqual(r.sources, [])

    def test_sources_never_claim_factual_verification(self):
        r = self.run_session([call("web_read", {"url": "https://e.org/a"}),
                              {"content": "O valor é 42, segundo a página."}])
        self.assertEqual(r.completion, "ANSWERED_WITH_SOURCES")
        self.assertEqual(r.verification, {"http_response": True, "content_retrieved": True,
                                          "tool_verified": True, "provenance_recorded": True,
                                          "answer_factually_verified": False})
        self.assertIn("não confirma cada afirmação", r.text)

    def test_truncated_page_is_disclosed(self):
        page = W.Page("https://e.org", "https://e.org", 200, "text/html", "Texto.", "e" * 64, True)
        r = self.run_session([call("web_read", {"url": "https://e.org"}), {"content": "Resumo."}],
                             fetcher=Fetcher(page=page))
        self.assertIn("parcial", r.text)

    def test_refusal_and_failure_messages_reach_the_user(self):
        r = self.run_session([call("web_read", {"url": "http://10.0.0.1/"}), {"content": "Feito."}],
                             fetcher=Fetcher(exc=W.WebRefused("o servidor resolve para um endereço privado ou reservado")))
        self.assertEqual(r.completion, "TOOLS_FAILED")
        self.assertIn("não foi possível concluir", r.text)
        r2 = self.run_session([call("web_read", {"url": "https://e.org"}), {"content": "Feito."}],
                              fetcher=Fetcher(exc=TimeoutError("slow")))
        self.assertEqual(r2.outcomes[0].status, "FAILED")
        self.assertIn("não foi possível concluir", r2.text)

    def test_halted_and_error_replies_state_incompleteness(self):
        steps = [call("web_read", {"url": f"https://e.org/{i}"}, f"c{i}") for i in range(12)]
        r = self.run_session(steps)
        self.assertEqual(r.completion, "HALTED")
        self.assertIn("interrompido", r.text)
        self.assertFalse(r.verification["tool_verified"] and r.completion == "ANSWERED_WITH_SOURCES")


if __name__ == "__main__":
    unittest.main()
