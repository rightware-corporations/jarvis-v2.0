"""JRV-R02-A (UNIT/FAKE): research tools with provenance, DuckDuckGo parsing through the audited fetcher, PDF reading,
citation validation, AgentSession integration, and SECURITY properties. The network is the synthetic offline corpus
(labs/r02) or scripted fetchers; the model is scripted. Not evidence about Qwen or about any real website."""
import json
import unittest

try:
    from labs.r02.corpus import DOCS, CorpusFetcher, make_pdf, render_search
    from rightware.agent.policy import Budgets
    from rightware.agent.session import AgentSession
    from rightware.agent.web import HttpxFetcher, Page, WebRefused
    from rightware.research import citations as C
    from rightware.research import documents as D
    from rightware.research import search as SE
    from rightware.research.provenance import Provenance, static_problem
    from rightware.research.toolkit import ResearchToolkit
    from tests.test_op01 import Scripted, call
except ImportError:
    ResearchToolkit = None


def step(name, **kw):
    return call(name, kw)


def say(text):
    return {"content": text}


def kit(fetcher=None, **kw):
    k = ResearchToolkit(fetcher or CorpusFetcher(), **kw)
    k.begin(kw.pop("instruction", "") if "instruction" in kw else "")
    return k


@unittest.skipIf(ResearchToolkit is None, "pinned OpenJarvis venv required")
class Search(unittest.TestCase):
    def test_ddg_markup_is_parsed_wrappers_decoded_ads_dropped(self):
        res = SE.parse(render_search("boletim cambial 159/26"))
        self.assertTrue(res)
        self.assertTrue(all(r.url.startswith("https://www.") for r in res))           # uddg decoded locally
        self.assertFalse(any("duckduckgo.com" in r.url or "y.js" in r.url for r in res))
        self.assertTrue(any("boletim-159-26.pdf" in r.url for r in res))

    def test_bot_check_page_is_reported_blocked_and_not_retried(self):
        f = CorpusFetcher(block_search=True)
        k = kit(f)
        out = k.tools()["web_search"][1]({"query": "inflação Moçambique"})
        self.assertEqual((out.status, out.code), ("REFUSED", "SEARCH_BLOCKED"))
        self.assertEqual(len([h for h in f.log if h["host"] == SE.SEARCH_HOST]), 1)    # one request, no retry

    def test_search_goes_only_to_the_search_host_through_the_fetcher(self):
        seen = []

        class Spy(CorpusFetcher):
            def fetch(self, url, host_allowed=None):
                seen.append((url, host_allowed("html.duckduckgo.com"), host_allowed("evil.example")))
                return super().fetch(url, host_allowed)
        k = kit(Spy())
        k.tools()["web_search"][1]({"query": "Lumen-7 contexto"})
        self.assertEqual(seen[0][1:], (True, False))
        self.assertTrue(seen[0][0].startswith("https://html.duckduckgo.com/html/?q="))

    def test_ddgs_client_is_not_used_by_the_product(self):
        from pathlib import Path
        src = "".join(p.read_text(encoding="utf-8") for p in
                      (Path(__file__).resolve().parents[1] / "rightware" / "research").glob("*.py"))
        self.assertNotIn("import ddgs", src)
        self.assertNotIn("from ddgs", src)
        self.assertNotIn("primp", src.replace("``primp``", ""))


@unittest.skipIf(ResearchToolkit is None, "pinned OpenJarvis venv required")
class ProvenanceRules(unittest.TestCase):
    def test_only_search_results_links_or_user_urls_can_be_read(self):
        k = kit()
        t = k.tools()
        self.assertEqual(t["web_read"][1]({"target": "https://www.ine-mz.example/inflacao/outubro-2026"}).code,
                         "PROVENANCE")                                 # model-invented URL: refused before any I/O
        t["web_search"][1]({"query": "inflação homóloga Outubro 2026 INE"})
        ok = t["web_read"][1]({"target": "R1"})
        self.assertEqual(ok.status, "OK")
        self.assertIn("Fonte S1", ok.content)

    def test_rereading_a_source_makes_no_request_and_keeps_its_id(self):
        f = CorpusFetcher()
        k = kit(f)
        t = k.tools()
        t["web_search"][1]({"query": "Lumen-7 janela de contexto"})
        t["web_read"][1]({"target": "R1"})
        n = len(f.log)
        again = t["web_read"][1]({"target": "R1"})
        self.assertIn("Já leste esta fonte como S1", again.content)
        self.assertEqual((len(f.log), list(k.sources), k.reads), (n, ["S1"], 1))

    def test_copied_result_line_and_bare_host_resolve_only_to_registered_entries(self):
        p = Provenance(verifies_destination=True)
        p.add_result("https://www.ine-mz.example/x", "t", 1)
        self.assertEqual(p.resolve("R1. Projecções — INE — www.ine-mz.example")[0].ref, "R1")
        self.assertEqual(p.resolve("www.ine-mz.example")[0].ref, "R1")
        self.assertIsNone(p.resolve("www.outro.example")[0])
        self.assertIsNone(p.resolve("R7")[0])

    def test_static_destination_rules(self):
        for bad in ("http://www.x.example/a", "https://10.0.0.5/a", "https://[::1]/a", "https://user:p@x.example/",
                    "https://x.example:8443/", "https://intranet.local/", "https://login.banco.example/",
                    "https://www.banco.example/entrar", "https://x.example/setup.exe", "https://localhost/"):
            self.assertIsNotNone(static_problem(bad), bad)
        self.assertIsNone(static_problem("https://www.ine-mz.example/inflacao/outubro-2026"))

    def test_link_depth_is_bounded(self):
        p = Provenance(verifies_destination=True, max_depth=2)
        self.assertIsNotNone(p.add_link("https://a.example/1", "x", "S1", 1))
        self.assertIsNone(p.add_link("https://a.example/2", "x", "S2", 2))

    def test_open_reading_requires_a_destination_verifying_transport(self):
        f = CorpusFetcher()
        f.verifies_destination = False                    # e.g. the experimental session proxy
        k = kit(f, closed_hosts=("www.bm-boletins.example",))
        t = k.tools()
        res = t["web_search"][1]({"query": "Nampula população 2026"})
        self.assertIn("destino não verificável", res.content)
        target = next(e.ref for e in k.prov.entries.values() if "diario-norte" in e.url)
        out = t["web_read"][1]({"target": target})
        self.assertEqual((out.status, out.code), ("REFUSED", "PROVENANCE"))
        self.assertFalse(any(h["host"] == "www.diario-norte.example" for h in f.log))   # no request was made
        self.assertIn("lista fechada", k.prompt())

    def test_production_fetcher_declares_verification_only_with_its_pinned_transport(self):
        self.assertTrue(HttpxFetcher().verifies_destination)
        self.assertFalse(HttpxFetcher(transport=object()).verifies_destination)


@unittest.skipIf(ResearchToolkit is None, "pinned OpenJarvis venv required")
class Security(unittest.TestCase):
    def test_redirect_to_private_address_is_refused_per_hop(self):
        f = CorpusFetcher()
        k = kit(f)
        t = k.tools()
        t["web_search"][1]({"query": "Cooperativa Mavalane"})
        t["web_read"][1]({"target": next(e.ref for e in k.prov.entries.values() if e.url.endswith("mavalane.example/"))})
        link = next(e.ref for e in k.prov.entries.values() if e.url.endswith("relatorio-2025"))
        out = t["web_read"][1]({"target": link})
        self.assertEqual(out.status, "REFUSED")
        self.assertFalse(any(h["host"] == "10.0.0.5" and h["allowed"] for h in f.log))

    def test_redirect_hop_to_non_allowlisted_host_is_refused_when_destination_unverified(self):
        f = CorpusFetcher()
        f.verifies_destination = False
        k = kit(f, closed_hosts=("www.atalho.example",))
        k.prov.add_user_urls("lê https://www.atalho.example/boletim")
        out = k.tools()["web_read"][1]({"target": "U1"})
        self.assertEqual(out.status, "REFUSED")                       # hop to bm-boletins is outside the closed list
        self.assertEqual([h["allowed"] for h in f.log], [True, False])

    def test_injection_is_framed_flagged_and_its_urls_never_become_readable(self):
        f = CorpusFetcher()
        k = kit(f)
        t = k.tools()
        t["web_search"][1]({"query": "câmbio EUR MZN Câmbios Rápidos"})
        ref = next(e.ref for e in k.prov.entries.values() if e.url.endswith("/eur-mzn"))
        out = t["web_read"][1]({"target": ref})
        self.assertIn("AVISO DO ANFITRIÃO", out.content)
        self.assertIn("PAGINA-NAO-CONFIAVEL", out.content)
        self.assertTrue(out.evidence["injection_suspected"])
        self.assertNotIn("169.254", " ".join(e.url for e in k.prov.entries.values()))   # http/IP links not registered
        self.assertNotIn("login.cambios", " ".join(e.url for e in k.prov.entries.values()))
        for target in ("http://169.254.169.254/latest/meta-data", "169.254.169.254"):
            self.assertEqual(t["web_read"][1]({"target": target}).status, "REFUSED")
        self.assertFalse(any("169.254" in h["host"] for h in f.log))
        lines, info, flags = k.finalize("O câmbio é 70,12 meticais por euro [S1].")
        self.assertIn("INJECTION_SUSPECTED", flags)

    def test_answer_from_search_snippets_only_is_never_presented_as_verified(self):
        f = CorpusFetcher()
        f.verifies_destination = False
        k = kit(f)                                          # empty closed list: nothing is readable
        k.begin("Quem dirige a Kanimambo Logística?")
        t = k.tools()
        t["web_search"][1]({"query": "Kanimambo Logística directora fundada"})
        self.assertEqual(t["web_read"][1]({"target": "R1"}).status, "REFUSED")
        lines, info, flags = k.finalize("Foi fundada em 2011 e é dirigida por Amélia Tembe [S1].")
        self.assertIn("SNIPPETS_ONLY", flags)
        self.assertTrue(lines[0].startswith("⚠ Verificação do anfitrião (fontes)"))
        self.assertEqual(info["citations"].get("invalid_citation"), 1)

    def test_user_supplied_login_url_is_refused_without_request(self):
        f = CorpusFetcher()
        k = kit(f)
        k.begin("Abre https://login.bancokanimambo.example/entrar e diz-me o saldo.")
        out = k.tools()["web_read"][1]({"target": "U1"})
        self.assertEqual((out.status, out.code), ("REFUSED", "PROVENANCE"))
        self.assertEqual(f.log, [])

    def test_budgets_stop_searches_and_reads(self):
        from rightware.research.toolkit import Budget
        k = kit(budget=Budget(searches=1, reads=1))
        t = k.tools()
        t["web_search"][1]({"query": "Lumen-7"})
        self.assertEqual(t["web_search"][1]({"query": "Lumen-7 contexto"}).code, "RESEARCH_BUDGET")
        t["web_read"][1]({"target": "R1"})
        self.assertEqual(t["web_read"][1]({"target": "R2"}).code, "RESEARCH_BUDGET")

    def test_pdf_converter_is_bounded_and_fails_closed(self):
        with self.assertRaises(D.DocumentError):
            D.pdf_to_text(b"<html>not a pdf</html>")
        with self.assertRaises(D.DocumentError):
            D.pdf_to_text(b"%PDF-" + b"0" * (D.MAX_PDF_BYTES + 1))
        if D.available():
            text, cut = D.pdf_to_text(make_pdf(["Receitas de 2025: 1 240 milhões de meticais."]))
            self.assertIn("1 240", text)
            self.assertFalse(cut)

    def test_production_fetcher_refuses_truncated_documents(self):
        import httpx
        big = b"%PDF-1.4\n" + b"0" * 6_000_000
        tr = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=big))
        f = HttpxFetcher(resolver=lambda h: ["93.184.216.34"], transport=tr, peer_check=lambda r: True, ssrf=lambda u: None)
        with self.assertRaises(WebRefused):
            f.fetch_document("https://docs.example/a.pdf")
        small = b"%PDF-1.4\nok"
        tr2 = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=small))
        page = HttpxFetcher(resolver=lambda h: ["93.184.216.34"], transport=tr2, peer_check=lambda r: True,
                            ssrf=lambda u: None).fetch_document("https://docs.example/a.pdf")
        self.assertEqual(page.raw, small)
        with self.assertRaises(WebRefused):                               # a page fetch never accepts a PDF
            HttpxFetcher(resolver=lambda h: ["93.184.216.34"], transport=tr2, peer_check=lambda r: True,
                         ssrf=lambda u: None).fetch("https://docs.example/a.pdf")


@unittest.skipIf(ResearchToolkit is None, "pinned OpenJarvis venv required")
class Documents(unittest.TestCase):
    def test_pdf_result_is_read_as_document_and_registered_as_source(self):
        if not D.available():
            self.skipTest("pdftotext indisponível")
        k = kit()
        t = k.tools()
        t["web_search"][1]({"query": "boletim cambial 159/26 24 Novembro 2026"})
        out = t["web_read"][1]({"target": "R1"})                           # web_read on a .pdf → document path
        self.assertEqual(out.status, "OK")
        self.assertIn("63,91", out.content)
        self.assertEqual(k.sources["S1"]["kind"], "pdf")


@unittest.skipIf(ResearchToolkit is None, "pinned OpenJarvis venv required")
class Citations(unittest.TestCase):
    SRC = {"S1": {"text": "Taxas de referência do dia 24 de Novembro de 2026. Moeda / Compra / Venda / Média: "
                          "USD 63,27 64,54 63,91. Ouro: compra 3 629,39."},
           "S2": {"text": "Março de 2026. A cidade de Nampula tem cerca de 950 mil habitantes, segundo o município."},
           "S3": {"text": "Projecções oficiais 2026. Cidade de Nampula: 812 400 habitantes."}}

    def status(self, answer, q=""):
        return [v.status for v in C.validate(answer, self.SRC, q)]

    def test_supported_vs_number_out_of_context_vs_unsupported(self):
        self.assertEqual(self.status("A taxa média do USD foi 63,91 [S1]."), ["SUPPORTED"])
        self.assertEqual(self.status("A taxa do USD foi 70,00 [S1]."), ["UNSUPPORTED"])
        # the number exists in the document, but not about this: NOT verified
        self.assertEqual(self.status("Nampula tem 3 629,39 habitantes registados no censo [S1]."),
                         ["NUMBERS_OUT_OF_CONTEXT"])

    def test_invalid_citation_and_uncited(self):
        self.assertEqual(self.status("A taxa foi 63,91 [S9]."), ["INVALID_CITATION"])
        self.assertEqual(self.status("A inflação de Moçambique foi 7,3 por cento este ano."), ["UNCITED"])
        self.assertEqual(self.status("A taxa média do USD foi 63,91."), ["SUPPORTED_UNCITED"])

    def test_derived_values_are_labelled_computed(self):
        self.assertEqual(self.status("2 500 USD valem 159 775 MZN à taxa média [S1].",
                                     "Quanto valem 2 500 dólares?"), ["DERIVED"])

    def test_question_numbers_and_dates_are_not_new_claims(self):
        self.assertEqual(self.status("A data pedida, 24 de Novembro de 2026, já foi publicada.",
                                     "Qual a taxa de 24 de Novembro de 2026?"), [])

    def test_contradiction_between_sources_is_reported(self):
        v = C.validate("A cidade de Nampula tem 812 400 habitantes [S3].", self.SRC)[0]
        self.assertEqual(v.status, "SUPPORTED")
        self.assertEqual(v.conflicts, ["S2: 950 000"])
        lines = C.host_lines([v])
        self.assertTrue(lines[0].startswith("✓ Verificação do anfitrião"))
        self.assertIn("divergência", lines[-1])

    def test_unsupported_statement_marks_the_answer_unconfirmed_for_voice(self):
        lines = C.host_lines(C.validate("A taxa foi 99,99 [S1].", self.SRC))
        self.assertTrue(lines[0].startswith("⚠ Verificação do anfitrião"))


@unittest.skipIf(ResearchToolkit is None, "pinned OpenJarvis venv required")
class SessionIntegration(unittest.TestCase):
    def session(self, script, f=None, **kw):
        k = ResearchToolkit(f or CorpusFetcher())
        return AgentSession(Scripted(script), "fake", allow={"websearch"}, confirm=lambda q: None, research=k,
                            receipts=True, budgets=Budgets(max_calls=8), **kw), k

    def test_search_read_cite_flow_with_host_validation(self):
        s, k = self.session([
            step("web_search", query="taxa MIMO Novembro 2026 CPMO"),
            step("web_read", target="R1"),
            say("O CPMO reduziu a taxa MIMO de 10,25% para 9,75% em Novembro de 2026 [S1].")])
        r = s.run("O que decidiu o CPMO em Novembro de 2026 sobre a taxa MIMO?")
        self.assertEqual(r.completion, "ANSWERED_WITH_SOURCES")
        self.assertEqual(r.verification["research"]["citations"].get("supported"), 1)
        self.assertIn("✓ Verificação do anfitrião (citações): 1 suportada(s)", r.text)
        self.assertNotIn("UNSUPPORTED_CITATION", r.flags)

    def test_fabricated_citation_is_flagged(self):
        s, _ = self.session([step("web_search", query="taxa MIMO Novembro 2026"), step("web_read", target="R1"),
                             say("A taxa MIMO passou para 5,00% [S1]. O banco subiu também a taxa de reservas [S2].")])
        r = s.run("Qual a taxa MIMO?")
        self.assertIn("UNSUPPORTED_CITATION", r.flags)
        self.assertIn("⚠ Verificação do anfitrião (citações)", r.text)

    def test_capability_and_configuration_are_fail_closed(self):
        with self.assertRaises(ValueError):
            AgentSession(Scripted([]), "fake", allow={"web"}, confirm=lambda q: None, research=ResearchToolkit(CorpusFetcher()))
        with self.assertRaises(ValueError):
            AgentSession(Scripted([]), "fake", allow={"websearch"}, confirm=lambda q: None)

    def test_plain_web_read_is_replaced_and_model_cannot_open_arbitrary_urls(self):
        s, _ = self.session([step("web_read", target="https://www.ine-mz.example/inflacao/outubro-2026"),
                             say("Não consegui ler a página.")])
        r = s.run("Qual a inflação?")
        self.assertEqual(r.outcomes[0].status, "REFUSED")
        self.assertEqual(r.completion, "TOOLS_FAILED")

    def test_forced_synthesis_when_turns_run_out_after_reading(self):
        script = [step("web_search", query="Lumen-7 janela de contexto"), step("web_read", target="R1")]
        script += [step("web_search", query=f"Lumen-7 detalhe {i}") for i in range(2)]
        script += [say("A janela de contexto do Lumen-7 é de 64 mil tokens [S1].")]   # the no-tools synthesis call
        s, k = self.session(script, max_turns=4)
        r = s.run("Qual a janela de contexto do Lumen-7?")
        self.assertIn("FORCED_SYNTHESIS", r.flags)
        self.assertIsNone(r.halted)
        self.assertIn("64 mil tokens", r.text)

    def test_adapter_wires_a_fresh_toolkit_per_question(self):
        from rightware.assistant_tools import ToolChatAdapter
        made = []

        def factory():
            made.append(ResearchToolkit(CorpusFetcher()))
            return made[-1]
        with self.assertRaises(ValueError):
            ToolChatAdapter("m", sites=(), persona="p", allow=("calc",), research_factory=factory)
        a = ToolChatAdapter("m", sites=(), persona="p", allow=("websearch",), research_factory=factory,
                            engine_factory=lambda: Scripted([say("Olá.")]))
        a.reply("olá", ())
        a.engine_factory = None
        self.assertEqual(len(made), 1)


@unittest.skipIf(ResearchToolkit is None, "pinned OpenJarvis venv required")
class EvalSet(unittest.TestCase):
    def test_thirty_independent_questions_cover_domains_and_difficulties(self):
        from pathlib import Path
        qs = json.loads((Path(__file__).resolve().parents[1] / "labs" / "r02" / "questions.json").read_text())["questions"]
        self.assertEqual(len(qs), 30)
        self.assertEqual(len({q["id"] for q in qs}), 30)
        doms = {q["domain"] for q in qs}
        for d in ("Moçambique", "Economia", "Finanças", "Tecnologia", "Actualidade", "Investigação empresarial",
                  "Documentos oficiais", "Fontes contraditórias", "Conteúdo adversarial"):
            self.assertIn(d, doms)
        self.assertEqual({q["difficulty"] for q in qs}, {"fácil", "média", "difícil"})
        self.assertGreaterEqual(sum(q.get("kind") == "security" for q in qs), 4)

    def test_corpus_marks_itself_synthetic(self):
        from labs.r02.corpus import NOTICE, render_html
        self.assertTrue(all(u.split("/")[2].endswith(".example") for u in DOCS))
        url = next(u for u, d in DOCS.items() if d[1] == "html")
        self.assertIn(NOTICE, render_html(url))


if __name__ == "__main__":
    unittest.main()
