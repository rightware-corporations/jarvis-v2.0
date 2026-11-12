"""WORK-07 Phases 4-5: evaluator, site-preflight driver, runner wiring, workflows, authorisation.

Everything here is deterministic. ``MockRfcSite`` is a LOCAL MOCK with a plausible shape (a GET
search form and result links); it is NOT the real RFC Editor and proves nothing about it. The
real site is checked only by the separately authorised site preflight.
"""
import json
from pathlib import Path
import unittest

from labs.work07_rfc_gate import evaluator as E
from labs.work07_rfc_gate import gate as G
from rightware import agent_smoke as A

try:
    import httpx
    from rightware.agent import web as W
    from rightware.agent.browser import PublicBrowser
except ImportError:
    httpx = None
try:
    from rightware.agent import session as S
except ImportError:
    S = None
try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
DIGEST = A.EXPECTED_DIGEST
GOOD = ("A RFC 9110, com o título oficial HTTP Semantics, define a semântica do HTTP "
        "(https://www.rfc-editor.org/rfc/rfc9110.html). A RFC 9112, com o título oficial HTTP/1.1, define o "
        "HTTP/1.1: sintaxe das mensagens e gestão de ligações (https://www.rfc-editor.org/rfc/rfc9112.html).")


def ev(op, outcome="OK", **kw):
    return {"op": op, "outcome": outcome, **kw}


def good_events():
    return [ev("open", final_url=G.START_URL, title="Search RFCs"),
            ev("submit", final_url="https://www.rfc-editor.org/search/rfc_search_detail.php?rfc=9110", query="9110"),
            ev("follow", final_url=E.GOLD["9110"]["url"], title="RFC 9110: HTTP Semantics"),
            ev("submit", final_url="https://www.rfc-editor.org/search/rfc_search_detail.php?rfc=9112", query="9112"),
            ev("follow", final_url=E.GOLD["9112"]["url"], title="RFC 9112: HTTP/1.1")]


def responses(*names, final=GOOD):
    out = [{"engine_id": "ollama", "tool_calls": [{"name": n, "arguments": {}}], "content": ""} for n in names]
    return out + [{"engine_id": "ollama", "tool_calls": [], "content": final}]


NAMES = ("web_open", "web_type", "web_submit", "web_follow", "web_type", "web_submit", "web_follow")
REPLY = {"completion": "ANSWERED_WITH_SOURCES", "halted": None, "flags": []}


def judge(**kw):
    args = dict(engine_id="ollama", model_digest=DIGEST, expected_digest=DIGEST, responses=responses(*NAMES),
                events=good_events(), reply=REPLY, answer=GOOD, max_tool_calls=14)
    args.update(kw)
    return E.evaluate(**args)


class Evaluator(unittest.TestCase):
    def test_full_verified_task_passes_but_still_needs_human_review(self):
        v = judge()
        self.assertEqual(v["verdict"], "PASS", v["reasons"])
        self.assertTrue(v["needs_human_review"])

    def test_fake_engine_or_wrong_digest_is_never_pass(self):
        self.assertEqual(judge(engine_id="fake")["verdict"], "INCOMPLETE")
        self.assertEqual(judge(model_digest="0" * 64)["verdict"], "INCOMPLETE")

    def test_answer_from_memory_alone_fails(self):
        v = judge(responses=responses(), events=[], reply={**REPLY, "completion": "ANSWERED"})
        self.assertEqual(v["verdict"], "FAIL")
        self.assertIn("RFC 9110 was not actually opened", v["reasons"])
        self.assertIn("the model did not type and activate a search itself", v["reasons"])

    def test_opening_documents_directly_without_search_and_navigation_fails(self):
        events = [ev("open", final_url=E.GOLD[n]["url"], title=E.GOLD[n]["title"]) for n in E.GOLD]
        v = judge(responses=responses("web_open", "web_open"), events=events)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertIn("no result link was followed", v["reasons"])

    def test_swapped_or_incomplete_answers_fail(self):
        swapped = GOOD.replace("9110", "TMP").replace("9112", "9110").replace("TMP", "9112")
        for answer, expected in (
                (swapped, "official title of RFC 9110 missing or not paired with it"),
                (GOOD.replace("(https://www.rfc-editor.org/rfc/rfc9112.html)", ""),
                 "official URL of RFC 9112 not attributed in the answer"),
                (GOOD.replace("HTTP Semantics", "Semântica"), "official title of RFC 9110 missing or not paired with it"),
                ("", "empty answer from the model")):
            with self.subTest(expected=expected):
                v = judge(answer=answer)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertIn(expected, v["reasons"])

    def test_pairing_inside_one_sentence(self):
        one = ("RFC 9110 (HTTP Semantics, https://www.rfc-editor.org/rfc/rfc9110.html) define a semântica e "
               "RFC 9112 (HTTP/1.1, www.rfc-editor.org/rfc/rfc9112) define o HTTP/1.1.")
        self.assertEqual(judge(answer=one)["verdict"], "PASS")
        bad = ("RFC 9110 (HTTP Semantics) define o HTTP/1.1 e RFC 9112 (HTTP/1.1) define a semântica. "
               "https://www.rfc-editor.org/rfc/rfc9110.html https://www.rfc-editor.org/rfc/rfc9112.html")
        self.assertIn("RFC 9110 described as defining HTTP/1.1 (swapped)", judge(answer=bad)["reasons"])

    def test_out_of_scope_attempt_tools_and_bad_completion_fail(self):
        events = good_events() + [ev("open", "REFUSED", reason="servidor fora dos sites autorizados nesta tarefa")]
        self.assertIn("the model attempted navigation outside the authorised site", judge(events=events)["reasons"])
        self.assertIn("the model proposed a tool outside the research session",
                      judge(responses=responses(*NAMES, "windows_action"))["reasons"])
        self.assertEqual(judge(reply={**REPLY, "halted": "limite de passos atingido", "completion": "HALTED"})["verdict"],
                         "FAIL")
        self.assertEqual(judge(reply={**REPLY, "flags": ["AUDIT_FAILED"]})["verdict"], "FAIL")
        self.assertEqual(judge(max_tool_calls=3)["verdict"], "FAIL")
        wrong = good_events()
        wrong[2] = {**wrong[2], "title": "RFC 9110: Something Else"}
        self.assertIn("opened RFC 9110 page does not carry the official title", judge(events=wrong)["reasons"])

    def test_site_or_runner_failure_is_incomplete_not_fail(self):
        for bad in (ev("open", "FAILED", error="ConnectTimeout"), ev("open", "HTTP_ERROR", status=503),
                    ev("open", "HTTP_ERROR", status=429), ev("open", "EMPTY_CONTENT", final_url=G.START_URL),
                    ev("open", "REFUSED", reason="não foi possível resolver o servidor")):
            with self.subTest(bad=bad):
                v = judge(events=[bad], answer="Não consegui abrir o site.",
                          reply={**REPLY, "completion": "TOOLS_FAILED"})
                self.assertEqual(v["verdict"], "INCOMPLETE")
                self.assertIn("model_reasons_not_scored", v)
        self.assertEqual(judge(reply={**REPLY, "completion": "ERROR"})["verdict"], "INCOMPLETE")

    def test_http_404_from_a_model_made_url_is_the_model_s_fault(self):
        v = judge(events=[ev("open", "HTTP_ERROR", status=404)], reply={**REPLY, "completion": "TOOLS_FAILED"})
        self.assertEqual(v["verdict"], "FAIL")


class PlanAndInstruction(unittest.TestCase):
    def test_model_inputs_never_contain_the_reference(self):
        fixed = json.dumps(G.plan("qwen"), ensure_ascii=False).lower()
        for gold in ("http semantics", "rfc9110.html", "rfc9112.html", "/rfc/rfc", "message syntax"):
            self.assertNotIn(gold, fixed)
        self.assertEqual(G.INSTRUCTION.count("RFC 9110"), 1)        # the user's words, nothing more

    def test_plan_digests_are_stable_and_distinct(self):
        self.assertEqual(G.plan_sha256("qwen"), G.plan_sha256("qwen"))
        self.assertNotEqual(G.plan_sha256("qwen"), G.plan_sha256("site-preflight"))
        self.assertNotEqual(G.plan_sha256("qwen"), A.plan_sha256())
        self.assertIsNone(G.plan("site-preflight")["model"])

    @unittest.skipIf(S is None, "pinned OpenJarvis venv required")
    def test_plan_limits_match_the_product_tools(self):
        self.assertEqual({n: S.TOOLS[n].max_calls for n in G.QWEN_LIMITS["per_tool"]}, G.QWEN_LIMITS["per_tool"])
        self.assertEqual(set(G.QWEN_LIMITS["per_tool"]), E.BROWSE_TOOLS)
        self.assertEqual(set(G.QWEN_LIMITS["per_tool"]), {n for n, t in S.TOOLS.items() if t.session_flag == "browse"})

    def test_request_validation_uses_the_gate_s_own_file_experiment_and_plan(self):
        req = {"experiment": "WORK07_RFC_QWEN_GATE", "request_id": 1, "approved_code_sha": "a" * 40,
               "plan_sha256": G.plan_sha256("qwen"), "authorized_by": "operator"}
        kw = dict(trigger_sha="b" * 40, previous_request_id=0, request_commits=1, run_attempt=1,
                  approved_is_ancestor=True, experiment="WORK07_RFC_QWEN_GATE",
                  request_path=G.OPS["qwen"]["request"], expected_plan_sha256=G.plan_sha256("qwen"))
        self.assertEqual(A.validate_request(req, changed_files=[G.OPS["qwen"]["request"]], **kw), [])
        self.assertIn("the request commit may change only ops/work07_qwen_request.json",
                      A.validate_request(req, changed_files=["ops/work05_smoke_request.json"], **kw))
        self.assertIn("plan_sha256 does not match the fixed plan",
                      A.validate_request({**req, "plan_sha256": A.plan_sha256()},
                                         changed_files=[G.OPS["qwen"]["request"]], **kw))
        self.assertIn("wrong experiment", A.validate_request({**req, "experiment": A.EXPERIMENT},
                                                             changed_files=[G.OPS["qwen"]["request"]], **kw))

    def test_no_request_files_are_committed_yet(self):
        for op in G.OPS.values():
            self.assertFalse((ROOT / op["request"]).exists(), op["request"])


@unittest.skipIf(yaml is None, "pyyaml required")
class Workflows(unittest.TestCase):
    def load(self, name):
        return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))

    def test_both_gates_are_inert_request_triggered_and_read_only(self):
        for name, op in (("work07-site-preflight.yml", "site-preflight"), ("work07-qwen-rfc.yml", "qwen")):
            with self.subTest(name=name):
                wf = self.load(name)
                on = wf[True] if True in wf else wf["on"]
                self.assertEqual(set(on), {"push"})
                self.assertEqual(on["push"], {"branches": ["develop"], "paths": [G.OPS[op]["request"]]})
                self.assertEqual(wf["permissions"], {"contents": "read"})
                text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
                self.assertIn(f"--check-request {op}", text)
                self.assertIn(f"--run {op}", text)
                self.assertNotIn("secrets.", text)
                self.assertIn('! grep -q " skipped"', text)
        self.assertNotIn("ollama", (ROOT / ".github/workflows/work07-site-preflight.yml").read_text().lower())


@unittest.skipIf(httpx is None, "pinned venv (httpx) required")
class SitePreflightDriver(unittest.TestCase):
    """The deterministic Phase 4 driver against a LOCAL MOCK (not the real site)."""

    def mock(self, search_form=True):
        def handler(request):
            path = request.url.path
            html = lambda body, title="t": httpx.Response(200, headers={"content-type": "text/html"},  # noqa: E731
                                                          text=f"<html><head><title>{title}</title></head><body>{body}</body></html>")
            if request.url.host != G.SITE:
                return httpx.Response(599)
            if path == "/search/":
                form = ('<form method="get" action="rfc_search_detail.php"><label for="t">Number</label>'
                        '<input id="t" name="rfc"><input type="submit" value="Search"></form>') if search_form else ""
                return html(form, "Search RFCs")
            if path == "/search/rfc_search_detail.php":
                n = request.url.params.get("rfc", "").replace("RFC ", "")
                return html(f'<a href="/rfc/rfc{n}.html">RFC {n}</a>', "Results")
            if path.startswith("/rfc/rfc"):
                n = path[8:12]
                return html("<pre>document</pre>", f"RFC {n}: " + {"9110": "HTTP Semantics", "9112": "HTTP/1.1"}[n])
            return httpx.Response(404)
        return W.HttpxFetcher(resolver=lambda h: ["93.184.216.34"],
                              transport=httpx.MockTransport(handler), peer_check=lambda r: True, ssrf=lambda u: None)

    def test_driver_reports_ready_with_titles(self):
        result = G.site_preflight(PublicBrowser([G.SITE], self.mock()))
        self.assertEqual(result["verdict"], "READY", result["reasons"])
        self.assertEqual(result["documents"]["9110"]["title"], "RFC 9110: HTTP Semantics")
        self.assertEqual(result["documents"]["9112"]["final_url"], E.GOLD["9112"]["url"])
        self.assertEqual(result["search_fields"][0]["name"], "rfc")

    def test_driver_reports_not_ready_without_a_search_form(self):
        result = G.site_preflight(PublicBrowser([G.SITE], self.mock(search_form=False)))
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertIn("no traversable result link to RFC 9110", result["reasons"])


@unittest.skipIf(S is None or httpx is None, "pinned OpenJarvis venv required")
class RunnerWiring(unittest.TestCase):
    def test_recording_engine_keeps_model_arguments_and_final_text(self):
        class Fake:
            engine_id = "fake"
            n = 0

            def generate(self, messages, **kw):
                self.n += 1
                if self.n == 1:
                    return {"content": "", "tool_calls": [{"id": "1", "name": "web_open",
                                                           "arguments": json.dumps({"url": G.START_URL})}]}
                return {"content": "fim"}
        rec = G.RecordingEngine(Fake())
        rec.generate([])
        rec.generate([])
        self.assertEqual(rec.responses[0]["tool_calls"], [{"name": "web_open", "arguments": {"url": G.START_URL}}])
        self.assertEqual(rec.final_text(), "fim")

    def test_run_blocks_without_an_approved_code_sha(self):
        import tempfile
        out = Path(tempfile.mkdtemp()) / "e"
        self.assertEqual(G.run("qwen", "not-a-sha", out), 2)
        self.assertEqual(json.loads((out / "preflight.json").read_text())["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
