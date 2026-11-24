"""WEB-01 W3.2 — OFFLINE with synthetic HTML, the fixture corpus and a SCRIPTED model (FAKE). Proves structured
extraction, hybrid retrieval, strict claim support (adversarial), host-composed answers, the adaptive loop (early
stop / rejected premature stop / continuation), injection filtering, budgets, cancellation and authorisation.
NOT evidence of model quality (see labs/web01/w32_eval.py with the real local Qwen)."""
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
    from rightware.web01 import evidence as EV
    from rightware.web01 import extract as X
    from rightware.web01 import fixture as FX
    from rightware.web01 import planner as PL
    from rightware.web01.egress import EgressPolicy
    from rightware.web01.free_research import FreeResearchMission
except ImportError:
    CP = None

PAGE = """<html><head><title>Rio Zambeze – Enciclopédia</title></head><body>
<h1>Rio Zambeze</h1><table class="infobox"><tr><th>Comprimento</th><td>2 574 km</td></tr>
<tr><th>Nascente</th><td>Mwinilunga<br/>Zâmbia</td></tr><tr><td>linha</td><td>sem cabeçalho</td></tr></table>
<p>O Zambeze é o quarto maior rio de África. Desagua no Oceano Índico, em Moçambique.</p>
<h2>Barragens</h2><ul><li>Cahora Bassa, inaugurada em 1974.</li><li>Kariba, concluída em 1959.</li></ul>
<script>var x = "não é texto";</script></body></html>"""


def kept_and_receipts(pages):
    import hashlib
    rec, kept = [], {}
    for i, (url, html) in enumerate(pages, 1):
        raw = html.encode()
        rec.append({"seq": i, "tool": "web_open_public", "status": "OK", "final_url": url,
                    "sha256": hashlib.sha256(raw).hexdigest()})
        kept[i] = raw
    return rec, kept


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class Extraction(unittest.TestCase):
    def test_structure_and_integrity(self):
        entity, bs = X.blocks(PAGE.encode(), "https://x/wiki/Rio_Zambeze")
        self.assertEqual(entity, "Rio Zambeze")
        kinds = {(b["kind"], b["text"]) for b in bs}
        self.assertIn(("kv", "Comprimento: 2 574 km"), kinds)
        self.assertIn(("kv", "Nascente: Mwinilunga Zâmbia"), kinds)
        self.assertIn(("row", "linha | sem cabeçalho"), kinds)
        self.assertIn(("list", "Kariba, concluída em 1959."), kinds)
        self.assertEqual([b["section"] for b in bs if "Kariba" in b["text"]], ["Rio Zambeze › Barragens"])
        self.assertFalse(any("não é texto" in b["text"] for b in bs))           # scripts never become evidence
        self.assertTrue(all(X.in_document(b["text"], PAGE.encode()) for b in bs))
        self.assertFalse(X.in_document("Comprimento: 3 000 km", PAGE.encode()))


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class Retrieval(unittest.TestCase):
    def test_parts_and_answer_types(self):
        rec, kept = kept_and_receipts([("https://x/wiki/Rio_Zambeze", PAGE)])
        q = "Qual é o comprimento do Zambeze e em que ano foi inaugurada Cahora Bassa?"
        parts = list(PL.host_parts(q))
        self.assertEqual(len(parts), 2)
        c = EV.candidates(q, parts, EV.documents(rec, kept))
        texts = [x["text"] for x in c]
        self.assertIn("Comprimento: 2 574 km", texts)                          # infobox kv found
        self.assertIn("Cahora Bassa, inaugurada em 1974.", texts)             # list item with a year

    def test_cross_document_entity_context(self):
        book = "<html><head><title>O Livro – E</title></head><body><p>O Livro é um romance escrito por Ana Silva.</p></body></html>"
        person = ("<html><head><title>Ana Silva – E</title></head><body><table><tr><th>Nascimento</th>"
                  "<td>1950, Inhambane</td></tr></table></body></html>")
        rec, kept = kept_and_receipts([("https://x/wiki/O_Livro", book), ("https://x/wiki/Ana_Silva", person)])
        q = "Onde nasceu a autora de O Livro?"
        c = EV.candidates(q, list(PL.host_parts(q)), EV.documents(rec, kept))
        ids = {x["text"]: x["id"] for x in c}
        self.assertIn("Nascimento: 1950, Inhambane", ids)
        synth = json.dumps({"claims": [
            {"part": 0, "evidence_id": ids["O Livro é um romance escrito por Ana Silva."],
             "quote": "O Livro é um romance escrito por Ana Silva.", "text": "O Livro foi escrito por Ana Silva."},
            {"part": 0, "evidence_id": ids["Nascimento: 1950, Inhambane"], "quote": "Nascimento: 1950, Inhambane",
             "text": "Ana Silva nasceu em Inhambane."}]})
        rep = EV.validate(synth, q, list(PL.host_parts(q)), c, rec, kept)
        self.assertEqual(len(rep["accepted"]), 2, rep["rejected"])               # entity context from the page title
        self.assertEqual(rep["final"], "GROUNDED")


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class StrictSupport(unittest.TestCase):
    Q = "O ponto mais alto é a Montanha do Pico, com 2 351 metros de altitude, inaugurada em 1974 por ninguém."

    def test_adversarial_claims_rejected(self):
        S = EV.strict_support
        quote, ctx = "Nascimento: 6 de março de 1927 Aracataca, Colômbia", "Gabriel García Márquez"
        self.assertIsNone(S("García Márquez nasceu na Colômbia", quote, ctx))
        cases = {
            "negação": ("García Márquez não nasceu na Colômbia", quote, ctx),
            "data errada": ("García Márquez nasceu em 1928", quote, ctx),
            "entidade trocada": ("García Márquez nasceu no México", quote, ctx),
            "valor errado": ("A Montanha do Pico tem 2 352 metros", "A Montanha do Pico tem 2 351 metros.", ""),
            "unidade trocada": ("A Montanha do Pico tem 2351 km", "A Montanha do Pico tem 2 351 metros.", ""),
            "relação diferente": ("Nairóbi é vizinha do Quénia", "Nairóbi, capital do Quênia", ""),
            "mesmas palavras, sentido diferente": ("Fleming descobriu a penicilina em 1945",
                                                   "Em 1945, Fleming, Chain e Florey receberam o Nobel", ""),
            "citação verdadeira, conclusão falsa": ("A penicilina foi descoberta pelo Banco Mundial",
                                                    "A penicilina foi descoberta em 1928.", ""),
        }
        for name, (t, q, c) in cases.items():
            with self.subTest(name=name):
                self.assertIsNotNone(S(t, q, c), name)
        self.assertIsNone(S("A Montanha do Pico tem 2351 m", "A Montanha do Pico tem 2 351 metros.", ""))

    def test_evidence_id_and_quote_format_tolerance(self):
        rec, kept = kept_and_receipts([("https://x/wiki/Rio_Zambeze", PAGE)])
        q = "Qual é o comprimento do Zambeze?"
        c = EV.candidates(q, list(PL.host_parts(q)), EV.documents(rec, kept))
        eid = next(x["id"] for x in c if x["text"] == "Comprimento: 2 574 km")
        for given in (eid, f"({eid})", f"[{eid}]"):
            rep = EV.validate(json.dumps({"claims": [{"part": 0, "evidence_id": given,
                                                      "quote": f"[{eid}] (Rio Zambeze › kv) Comprimento: 2 574 km",
                                                      "text": "O Zambeze tem 2 574 km de comprimento"}]}),
                              q, list(PL.host_parts(q)), c, rec, kept)
            self.assertEqual(len(rep["accepted"]), 1, (given, rep["rejected"]))
        rep = EV.validate(json.dumps({"claims": [{"part": 0, "evidence_id": "E99", "quote": "Comprimento: 2 574 km",
                                                  "text": "O Zambeze tem 2 574 km"}]}), q, list(PL.host_parts(q)), c, rec, kept)
        self.assertIn("inventada", rep["rejected"][0]["why"])                  # tolerance never invents an id

    @unittest.expectedFailure
    def test_known_limitation_inverse_relation_with_identical_words(self):
        # KNOWN LIMITATION (documented): same words, inverted relation, no negation → lexical checks cannot tell.
        self.assertIsNotNone(EV.strict_support("O Quénia é a capital de Nairóbi", "Nairóbi é a capital do Quénia", ""))


GOOD = {"objective": "Responder", "answer_parts": ["capital de Moçambique"], "subquestions": [],
        "queries": ["capital de Moçambique"], "relevance_criteria": ["fala da capital"], "missing_info": []}


def fake(assess=None, synth=None, log=None):
    def call(system, user):
        if log is not None:
            log.append(system[:12])
        if system == PL.PLAN_SYSTEM:
            return json.dumps(GOOD), 0.0
        if system == EV.ASSESS_SYSTEM:
            return (assess(user) if assess else json.dumps({"covered": [{"part": 0, "evidence": ["E1", "E2"]}],
                                                              "missing": [], "sufficient": True, "next_query": None,
                                                              "reason": "f"})), 0.0
        ev = dict(re.findall(r"^\[(E\d+)\] \([^)]*\) ([^\n]+)", user, re.M))
        if synth:
            return synth(ev), 0.0
        hit = next(((i, t) for i, t in ev.items() if "Maputo" in t), None)
        if not hit:
            return json.dumps({"claims": []}), 0.0
        s = next(x for x in re.split(r"(?<=\.)\s+", hit[1]) if "Maputo" in x)
        return json.dumps({"claims": [{"part": 0, "evidence_id": hit[0], "quote": s, "text": s}]}), 0.0
    return call


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class AdaptiveLoop(unittest.TestCase):
    def run_m(self, call, policy=None, q="Qual é a capital de Moçambique?", plan=GOOD, **kw):
        m = FreeResearchMission(policy, model="fake", model_call=call, runtime=Path(tempfile.mkdtemp()), **kw)
        p = PL.validate_plan(json.dumps(plan), q, "fake")
        o = m.run(threading.Event(), params={"plan": p})
        return o, json.loads((m.last_run / "result.json").read_text()) if getattr(m, "last_run", None) else None

    def test_early_stop_when_host_confirms_coverage(self):
        o, r = self.run_m(fake(), plan=dict(GOOD, queries=["capital de Moçambique", "Maputo", "moeda"]))
        self.assertEqual(o.state, CP.State.RESPOSTA_FUNDAMENTADA)
        self.assertEqual(len(r["iterations"]), 1)
        self.assertIn("paragem antecipada", r["stop_reason"])
        self.assertGreater(r["requests_avoided"], 0)
        self.assertEqual(o.model_commentary_unverified, "")

    def test_model_stop_rejected_without_host_coverage(self):
        bad = lambda u: json.dumps({"covered": [{"part": 0, "evidence": ["E99"]}], "missing": [],  # noqa: E731
                                    "sufficient": True, "next_query": "Maputo capital", "reason": "já sei"})
        o, r = self.run_m(fake(assess=bad), plan=dict(GOOD, queries=["capital de Moçambique"]))
        self.assertGreaterEqual(len(r["iterations"]), 2)
        self.assertIn("REJEITADA", r["iterations"][0]["decision"])
        self.assertEqual(r["iterations"][1]["query"], "Maputo capital")         # model's next query used

    def test_rejected_claims_never_reach_the_answer(self):
        synth = lambda ev: json.dumps({"claims": [                                   # noqa: E731
            {"part": 0, "evidence_id": next(iter(ev)), "quote": "frase inventada", "text": "A capital é Lisboa"}]})
        o, r = self.run_m(fake(synth=synth))
        self.assertEqual(o.state, CP.State.RESULTADO_DESCONHECIDO)
        answer = [l for l in o.findings if l.startswith("•")]
        self.assertFalse(any("Lisboa" in l for l in answer))
        self.assertTrue(any("sem evidência suficiente" in l for l in answer))

    def test_conflicts_and_injection(self):
        synth = lambda ev: json.dumps({"claims": [], "conflicts": ["fórum diz Beira"]})  # noqa: E731
        o, r = self.run_m(fake(synth=synth), plan=dict(GOOD, queries=["fórum capital Beira"]))
        self.assertTrue(r["ignored_external_instructions"])                       # forum's injected order filtered
        self.assertFalse(any("IGNORA" in c["text"] for c in r["candidates"]))

    def test_budget_cancel_model_calls_and_authorisation(self):
        pol = EgressPolicy.from_dict({**json.loads(Path("configs/web01/egress.json").read_text()),
                                      "max_requests_per_mission": 3})
        never = lambda u: json.dumps({"covered": [], "missing": [0], "sufficient": False,  # noqa: E731
                                      "next_query": None, "reason": "x"})
        o, r = self.run_m(fake(assess=never), policy=pol, plan=dict(GOOD, queries=["a b c", "d e f", "g h i"]))
        self.assertLessEqual(r["requests"], 3)
        self.assertLessEqual(r["model_calls"], 5)
        m = FreeResearchMission(model="fake", model_call=fake(), runtime=Path(tempfile.mkdtemp()),
                                fetcher_factory=lambda stop: FX.fixture_fetcher(delay=1.0, cancel=stop))
        threading.Timer(0.3, m.cancel).start()
        t0 = time.monotonic()
        o = m.run(threading.Event(), params={"plan": PL.validate_plan(json.dumps(GOOD), "Qual é a capital?", "f")})
        self.assertEqual(o.state, CP.State.TAREFA_CANCELADA)
        self.assertLess(time.monotonic() - t0, 3)
        with self.assertRaises(PermissionError):
            m.run(threading.Event(), params={"plan": "não é um plano"})


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class PlanContract(unittest.TestCase):
    def test_answer_parts_must_describe_the_question(self):
        q = "Qual é a capital de Moçambique e que nome tinha antes de 1976?"
        notes = []
        p = PL.validate_plan(json.dumps(dict(GOOD, answer_parts=["Maputo", "Lourenço Marques"])), q, "t", notes=notes)
        self.assertEqual(p.answer_parts, ("Qual é a capital de Moçambique", "que nome tinha antes de 1976"))
        self.assertTrue(any("decomposição do anfitrião" in n for n in notes))
        self.assertEqual(PL.host_parts("Quem escreveu Romeu e Julieta?"), ("Quem escreveu Romeu e Julieta",))


if __name__ == "__main__":
    unittest.main()
