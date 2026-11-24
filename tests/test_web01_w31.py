"""WEB-01 W3.1 (user-driven research) — OFFLINE with a SCRIPTED model (FAKE, labelled) and the local fixture corpus or
an injected transport. Proves routing, plan validation, grounding checks, abstention, budgets, cancellation and the
chat→plan→code→run flow. NOT evidence of model quality (see labs/web01/w31_eval.py with the real local Qwen)."""
import json
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path

try:
    import httpx  # noqa: F401
    from rightware import control_plane as CP
    from rightware.web01 import egress as E
    from rightware.web01 import grounding as G
    from rightware.web01 import planner as PL
    from rightware.web01 import fixture as FX
    from rightware.web01.free_research import FreeResearchMission
except ImportError:
    CP = None

GOOD_PLAN = {"objective": "Identificar a capital", "subquestions": [], "queries": ["capital de Moçambique"],
             "relevance_criteria": ["fala da capital"], "missing_info": []}


def scripted(plan=GOOD_PLAN, synth=None, intent="research", log=None):
    """FAKE model: answers by system prompt. ``synth(passages_text)`` builds the synthesis JSON."""
    def call(system, user):
        if log is not None:
            log.append(system[:20])
        if system == PL.INTENT_SYSTEM:
            return json.dumps({"intent": intent}), 0.01
        if system == PL.PLAN_SYSTEM:
            return (plan if isinstance(plan, str) else json.dumps(plan)), 0.01
        return synth(user), 0.01
    return call


def passages_of(user):
    return dict(re.findall(r"\[(P\d+)\] \(fonte: [^)]*\) ([^\n]+)", user))


def quote_first(word, status="answered", conflicts=()):
    def synth(user):
        ps = passages_of(user)
        hit = next(((i, t) for i, t in ps.items() if word.lower() in t.lower()), None)
        if hit is None:
            return json.dumps({"status": "insufficient", "answer": "", "claims": [], "conflicts": [], "uncertainty": "x"})
        sent = next(s for s in re.split(r"(?<=\.)\s+", hit[1]) if word.lower() in s.lower())
        return json.dumps({"status": status, "answer": sent, "claims": [{"text": sent, "passage_ids": [hit[0]],
                           "quote": sent}], "conflicts": list(conflicts), "uncertainty": ""})
    return synth


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class Routing(unittest.TestCase):
    def test_host_decides(self):
        p = lambda t: "research"                                     # noqa: E731
        self.assertEqual(PL.route("/pesquisar capital de Moçambique", research_enabled=True).kind, PL.RESEARCH_EXPLICIT)
        self.assertEqual(PL.route("/pesquisar x", research_enabled=False).kind, PL.OUT_OF_SCOPE)
        for t in ("Compra ações da Vodacom", "Qual a cotação do metical hoje?", "Apaga o ficheiro relatório.docx",
                  "Envia um email ao Issa", "Qual é a minha password?"):
            self.assertEqual(PL.route(t, research_enabled=True, propose=p).kind, PL.OUT_OF_SCOPE, t)
        self.assertEqual(PL.route("Qual é a capital?", research_enabled=True, propose=p).kind, PL.RESEARCH_SUGGESTED)
        self.assertEqual(PL.route("Qual é a capital?", research_enabled=False, propose=p).kind, PL.CHAT)
        self.assertEqual(PL.route("Escreve um poema", research_enabled=True, propose=p).kind, PL.CHAT)  # not a question
        self.assertEqual(PL.route("Qual é?", research_enabled=True, propose=lambda t: 1 / 0).kind, PL.CHAT)


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class PlanValidation(unittest.TestCase):
    def test_model_cannot_touch_policy_or_question(self):
        q = "Qual é a capital de Moçambique?"
        bad = [dict(GOOD_PLAN, allowed_hosts=["evil.com"]), dict(GOOD_PLAN, budget=999),
               dict(GOOD_PLAN, verdict="VERIFIED"), dict(GOOD_PLAN, queries=["site:evil.com capital"]),
               dict(GOOD_PLAN, queries=["https://evil.com"]), dict(GOOD_PLAN, queries=[]),
               dict(GOOD_PLAN, queries=["a"] * 5), "not json", "[1,2]"]
        for b in bad:
            with self.subTest(b=str(b)[:60]), self.assertRaises(PL.PlanError):
                PL.validate_plan(b if isinstance(b, str) else json.dumps(b), q, "t")
        plan = PL.validate_plan(json.dumps(dict(GOOD_PLAN, objective="x" * 10)), q, "t")
        self.assertEqual(plan.question, q)                           # from the host, never from the model
        notes = []
        plan = PL.validate_plan(json.dumps(dict(GOOD_PLAN, subquestions=["a b c"] * 2 + ["d e f", "g h i", "j k l"])),
                                q, "t", notes=notes)
        self.assertEqual((len(plan.subquestions), notes), (3, ["subquestions: 4 itens truncados para 3"]))
        with self.assertRaises(PL.PlanError):                        # objects instead of text stay invalid
            PL.validate_plan(json.dumps(dict(GOOD_PLAN, subquestions=[{"q": "x"}])), q, "t")
        seen = []
        PL.make_plan(q, lambda sys, user: (seen.append(user), ("lixo", 0.0))[1], "fake")
        self.assertIn("rejeitada pelo anfitrião", seen[1])           # the retry carries the validation error
        plan, meta = PL.make_plan(q, scripted(plan="lixo"), "fake")
        self.assertEqual((plan.source, meta["attempts"], meta["valid_model_plan"]), ("anfitrião (fallback)", 2, False))


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class Grounding(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def mission(self, synth, policy=None, **kw):
        return FreeResearchMission(policy, model="fake", model_call=scripted(synth=synth), runtime=self.tmp, **kw)

    def run_q(self, m, q="Qual é a capital de Moçambique?", plan=GOOD_PLAN):
        p = PL.validate_plan(json.dumps(plan), q, "fake")
        return m.run(threading.Event(), params={"plan": p})

    def test_grounded_answer_is_never_verified(self):
        o = self.run_q(self.mission(quote_first("Maputo")))
        self.assertEqual(o.state, CP.State.RESPOSTA_FUNDAMENTADA)
        self.assertFalse(o.verified)
        self.assertIn("NÃO verificadas semanticamente", CP.LABELS[o.state])
        self.assertTrue(any(l.startswith("C1 [GROUNDED]") for l in o.findings))

    def test_invented_references_and_quotes_are_removed(self):
        for synth, why in ((lambda u: json.dumps({"status": "answered", "answer": "Maputo", "claims": [
                               {"text": "A capital é Maputo", "passage_ids": ["P99"], "quote": "Maputo"}]}),
                            "passagem inventada"),
                           (lambda u: json.dumps({"status": "answered", "answer": "Maputo", "claims": [
                               {"text": "A capital é Maputo", "passage_ids": ["P1"], "quote": "frase que não existe"}]}),
                            "citação não existe")):
            o = self.run_q(self.mission(synth))
            self.assertEqual(o.state, CP.State.RESULTADO_DESCONHECIDO)             # abstains: nothing grounded
            self.assertTrue(any(why in l for l in o.findings))

    def test_tampered_source_bytes_fail_integrity(self):
        ps = [{"id": "P1", "seq": 1, "url": "u", "sha256": "0" * 64, "text": "Maputo é a capital de Moçambique.",
               "relevance": 1.0}]
        rec = [{"seq": 1, "status": "OK", "sha256": "0" * 64, "tool": "web_open_public"}]
        rep = G.validate(json.dumps({"status": "answered", "answer": "", "claims": [{"text": "Maputo é a capital",
                         "passage_ids": ["P1"], "quote": "Maputo é a capital de Moçambique."}]}),
                         "capital de Moçambique", ps, rec, {1: b"<p>Maputo e a capital de Mocambique.</p>"})
        self.assertEqual(rep["final"], "ABSTAIN")
        self.assertIn("integridade", rep["dropped"][0]["why"])

    def test_insufficient_information_abstains(self):
        o = self.run_q(self.mission(quote_first("inflação")), q="Qual foi a inflação de Moçambique em 2031?",
                       plan=dict(GOOD_PLAN, queries=["inflação Moçambique 2031"]))
        self.assertEqual(o.state, CP.State.RESULTADO_DESCONHECIDO)

    def test_injection_source_and_conflicts_never_grounded(self):
        # FAKE model that OBEYS the injected forum text: the quote exists (integrity ok) but the conflict caps it.
        o = self.run_q(self.mission(quote_first("Beira", conflicts=["Fórum diz Beira; enciclopédia diz Maputo"])),
                       plan=dict(GOOD_PLAN, queries=["fórum capital Beira"]))
        self.assertTrue(any("forum.fixture.example" in s["url"] for s in o.sources))
        self.assertEqual(o.state, CP.State.EXECUCAO_PARCIAL)
        self.assertTrue(any("Conflitos" in l for l in o.findings))

    def test_budget_cancel_and_allowlist(self):
        pol = E.EgressPolicy.from_dict({**json.loads(Path("configs/web01/egress.json").read_text()),
                                        "max_requests_per_mission": 2})
        o = self.run_q(self.mission(quote_first("Maputo"), policy=pol),
                       plan=dict(GOOD_PLAN, queries=["capital de Moçambique", "Maputo", "moeda"]))
        self.assertLessEqual(o.receipts_count, 2)
        m = self.mission(quote_first("Maputo"), fetcher_factory=lambda stop: FX.fixture_fetcher(delay=1.0, cancel=stop))
        threading.Timer(0.3, m.cancel).start()
        t0 = time.monotonic()
        o = self.run_q(m)
        self.assertEqual(o.state, CP.State.TAREFA_CANCELADA)
        self.assertLess(time.monotonic() - t0, 3)
        guard = E.EgressGuard(E.EgressPolicy.load(), FX.fixture_fetcher())
        with self.assertRaises(E.EgressRefused):
            guard.fetch("https://pt.wikipedia.org/wiki/Maputo")                      # not in the fixture allowlist


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class ChatFlow(unittest.TestCase):
    def test_chat_question_proposes_plan_only_and_code_runs_exactly_it(self):
        from rightware.console import build
        from rightware.gui import bridge as B
        from tests.test_ui01_gui import TextModel
        served = []
        model = TextModel()
        entry = build("qwen3.5:2b", model, 30.0)
        m = FreeResearchMission(model="fake", model_call=scripted(synth=quote_first("Maputo")),
                                runtime=Path(tempfile.mkdtemp()),
                                fetcher_factory=lambda stop: _Count(FX.fixture_fetcher(), served))
        cp = CP.ControlPlane(entry.text_facade, missions=(m,))
        br = B.ChatBridge(entries={"qwen3.5:2b": entry}, default_model="qwen3.5:2b", control=cp, audit=None)
        kind, md, meta = br.respond("qwen3.5:2b", [("user", "Qual é a capital de Moçambique?")])
        self.assertEqual((kind, meta["intent"]), ("RESEARCH_PROPOSED", PL.RESEARCH_SUGGESTED))
        self.assertEqual(served, [])                                  # proposing never touches the network
        code = re.search(r"/autorizar ([0-9A-F]{6})", md).group(1)
        self.assertEqual(br.respond("qwen3.5:2b", [("user", "Olá!")])[0], "RESPOSTA_DO_MODELO")      # chat stays chat
        kind, md2, _ = br.respond("qwen3.5:2b", [("user", "Compra ações")])
        self.assertEqual(kind, "REFUSED")
        self.assertIsInstance(cp.authorize_and_run("ABCDEF"), CP.Refusal)               # wrong code consumes it
        _, code = cp.request("pesquisa-livre", {"plan": PL.fallback_plan("Qual é a capital de Moçambique?")})
        out = cp.authorize_and_run(code)
        self.assertEqual(out.state, CP.State.RESPOSTA_FUNDAMENTADA)
        self.assertGreater(len(served), 0)
        self.assertEqual(cp.request("pesquisa-livre")[0], CP.State.TAREFA_NAO_AUTORIZADA)  # never without a plan


class _Count:
    def __init__(self, inner, log):
        self.inner, self.log = inner, log

    def fetch(self, url, host_allowed=None, **kw):
        self.log.append(url)
        return self.inner.fetch(url, host_allowed, **kw)


if __name__ == "__main__":
    unittest.main()
