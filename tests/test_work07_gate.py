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
            ev("follow", final_url=E.GOLD["9110"]["url"], status=200, title="RFC 9110: HTTP Semantics"),
            ev("submit", final_url="https://www.rfc-editor.org/search/rfc_search_detail.php?rfc=9112", query="9112"),
            ev("follow", final_url=E.GOLD["9112"]["url"], status=200, title="RFC 9112: HTTP/1.1")]


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
        self.assertIn("opened RFC 9110 page not validated: RFC 9110: title 'RFC 9110: Something Else' is not the "
                      "official title", judge(events=wrong)["reasons"])
        no_status = good_events()
        no_status[4] = {**no_status[4], "status": 203}
        self.assertEqual(judge(events=no_status)["verdict"], "FAIL")

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

    STEPS = {"work07-site-preflight.yml": ("site-preflight", "preflight", "READY"),
             "work07-qwen-rfc.yml": ("qwen", "gate", "PASS")}

    def steps(self, name):
        return self.load(name)["jobs"][next(iter(self.load(name)["jobs"]))]["steps"]

    def test_technical_execution_and_acceptance_are_separate_steps(self):
        for name, (op, sub, ok) in self.STEPS.items():
            with self.subTest(name=name):
                steps = self.steps(name)
                names = [st.get("name", "") for st in steps]
                tech = next(i for i, n in enumerate(names) if n.startswith("TECHNICAL EXECUTION"))
                acc = next(i for i, n in enumerate(names) if n.startswith("ACCEPTANCE VERDICT"))
                keep = names.index("Preserve evidence (always)")
                upload = names.index("Upload evidence (always)")
                self.assertTrue(tech < acc < keep < upload)
                self.assertIn("NOT an acceptance verdict", names[tech])
                self.assertIn(f"fails unless the verdict is {ok}", names[acc])
                for i in (acc, keep, upload):
                    self.assertEqual(steps[i].get("if"), "always()")
                self.assertNotIn("if", steps[tech])
                self.assertIn('technical-exit.txt', steps[tech]["run"])
                self.assertIn(f"--acceptance {op}", steps[acc]["run"])
                self.assertIn("GITHUB_STEP_SUMMARY", steps[acc]["run"])

    def run_acceptance_step(self, name, verdict_file=None, technical=None):
        import os
        import subprocess
        import tempfile
        op, sub, ok = self.STEPS[name]
        script = next(st["run"] for st in self.steps(name) if st.get("name", "").startswith("ACCEPTANCE VERDICT"))
        evid = Path(tempfile.mkdtemp())
        (evid / sub).mkdir()
        if technical is not None:
            (evid / "technical-exit.txt").write_text(f"{technical}\n")
        if verdict_file is not None:
            fname = "site_preflight.json" if op == "site-preflight" else "qwen_gate.json"
            (evid / sub / fname).write_text(json.dumps(verdict_file))
        summary = evid / "summary.md"
        env = {**os.environ, "EVID": str(evid), "GITHUB_STEP_SUMMARY": str(summary), "RUNNER_TEMP": str(evid)}
        rc = subprocess.run(["bash", "-e", "-c", script], cwd=ROOT, env=env, capture_output=True, text=True).returncode
        return rc, json.loads((evid / "acceptance.json").read_text()), summary.read_text()

    def test_acceptance_step_shell_behaviour(self):
        for name, (op, sub, ok) in self.STEPS.items():
            wrap = (lambda v: {"verdict": v, "reasons": []}) if op == "site-preflight" else \
                (lambda v: {"verdict": {"verdict": v, "reasons": []}})
            with self.subTest(name=name, case="accepted"):
                rc, acc, summary = self.run_acceptance_step(name, wrap(ok), 0)
                self.assertEqual((rc, acc["accepted"], acc["verdict"]), (0, True, ok))
                self.assertIn("technical execution vs acceptance", summary)
            for verdict in ("NOT_READY", "FAIL", "INCOMPLETE"):
                with self.subTest(name=name, verdict=verdict):
                    rc, acc, _ = self.run_acceptance_step(name, wrap(verdict), 0)
                    self.assertEqual((rc, acc["accepted"], acc["technical_execution"]), (1, False, "COMPLETED"))
            with self.subTest(name=name, case="runner blocked"):
                rc, acc, _ = self.run_acceptance_step(name, wrap(ok), 2)
                self.assertEqual((rc, acc["accepted"], acc["technical_execution"]), (1, False, "BLOCKED"))
            with self.subTest(name=name, case="runner never ran"):
                rc, acc, _ = self.run_acceptance_step(name, None, None)
                self.assertEqual((rc, acc["accepted"], acc["verdict"]), (1, False, "NO_VERDICT"))


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


class DocumentCheck(unittest.TestCase):
    def test_official_document_pages_validate(self):
        for n, title in (("9110", "RFC 9110: HTTP Semantics"), ("9110", "HTTP Semantics"),
                         ("9112", "RFC 9112 - HTTP/1.1"), ("9112", " rfc 9112:  http/1.1 ")):
            with self.subTest(title=title):
                self.assertEqual(E.check_document(n, 200, E.GOLD[n]["url"], title), [])

    def test_missing_wrong_title_status_and_url_are_rejected(self):
        url = E.GOLD["9110"]["url"]
        for args, expected in (
                ((200, url, ""), "page title missing"),
                ((200, url, None), "page title missing"),
                ((200, url, "RFC 9110: HTTP/1.1"), "is not the official title"),
                ((200, url, "RFC 9110: HTTP Semantics (obsoleted draft)"), "is not the official title"),
                ((200, url, "RFC 9112: HTTP Semantics"), "is not the official title"),
                ((200, url, "Search results"), "is not the official title"),
                ((203, url, "RFC 9110: HTTP Semantics"), "HTTP status 203"),
                ((None, url, "RFC 9110: HTTP Semantics"), "HTTP status None"),
                ((200, E.GOLD["9112"]["url"], "RFC 9110: HTTP Semantics"), "unexpected final URL"),
                ((200, "https://www.rfc-editor.org/info/rfc9110", "RFC 9110: HTTP Semantics"), "unexpected final URL"),
                ((200, "https://rfc-editor.org/rfc/rfc9110.html", "RFC 9110: HTTP Semantics"), "unexpected final URL"),
                ((200, "https://www.rfc-editor.org/rfc/rfc91100.html", "RFC 9110: HTTP Semantics"),
                 "unexpected final URL")):
            with self.subTest(args=args):
                problems = E.check_document("9110", *args)
                self.assertTrue(any(expected in p for p in problems), problems)


@unittest.skipIf(httpx is None, "pinned venv (httpx) required")
class SitePreflightNegative(unittest.TestCase):
    """The preflight returns READY ONLY when both opened documents are validated (LOCAL MOCK)."""

    def run_mock(self, doc):
        """``doc(number, request) -> httpx.Response`` serves the /rfc/ pages; search works normally."""
        def handler(request):
            path = request.url.path
            page = lambda body, title: httpx.Response(  # noqa: E731
                200, headers={"content-type": "text/html"},
                text=f"<html><head>{title}</head><body>{body}</body></html>")
            if path == "/search/":
                return page('<form method="get" action="rfc_search_detail.php"><input name="rfc"></form>',
                            "<title>Search RFCs</title>")
            if path == "/search/rfc_search_detail.php":
                n = request.url.params.get("rfc", "").replace("RFC ", "")
                return page(f'<a href="/rfc/rfc{n}.html">RFC {n}</a>', "<title>Results</title>")
            if path.startswith(("/rfc/rfc", "/errata/rfc")):
                return doc(path.rsplit("rfc", 1)[1][:4], request)
            return httpx.Response(404, headers={"content-type": "text/html"}, text="<p>x</p>")
        fetcher = W.HttpxFetcher(resolver=lambda h: ["93.184.216.34"], transport=httpx.MockTransport(handler),
                                 peer_check=lambda r: True, ssrf=lambda u: None)
        return G.site_preflight(PublicBrowser([G.SITE], fetcher))

    @staticmethod
    def html(title_tag, status=200, body="<pre>document</pre>"):
        return httpx.Response(status, headers={"content-type": "text/html"},
                              text=f"<html><head>{title_tag}</head><body>{body}</body></html>")

    def official(self, n, request):
        return self.html(f"<title>RFC {n}: {E.GOLD[n]['title']}</title>")

    def assert_not_ready(self, result, fragment):
        self.assertEqual(result["verdict"], "NOT_READY")
        self.assertTrue(any(fragment in r for r in result["reasons"]), result["reasons"])

    def test_control_both_official_documents_are_ready(self):
        result = self.run_mock(self.official)
        self.assertEqual(result["verdict"], "READY", result["reasons"])
        self.assertTrue(all(d["validated"] and not d["redirected"] for d in result["documents"].values()))

    def test_missing_title_is_not_ready(self):
        result = self.run_mock(lambda n, r: self.official(n, r) if n == "9110" else self.html(""))
        self.assert_not_ready(result, "RFC 9112: page title missing")
        self.assertTrue(result["documents"]["9110"]["validated"])
        self.assertFalse(result["documents"]["9112"]["validated"])

    def test_wrong_title_is_not_ready(self):
        result = self.run_mock(lambda n, r: self.html("<title>RFC 9110: HTTP Caching</title>")
                               if n == "9110" else self.official(n, r))
        self.assert_not_ready(result, "RFC 9110: title 'RFC 9110: HTTP Caching' is not the official title")

    def test_swapped_title_is_not_ready(self):
        other = {"9110": "9112", "9112": "9110"}
        result = self.run_mock(lambda n, r: self.official(other[n], r))
        self.assert_not_ready(result, "is not the official title")
        self.assertEqual(len(result["reasons"]), 2)

    def test_redirect_to_the_other_document_is_not_ready(self):
        def doc(n, r):
            if n == "9110":
                return httpx.Response(302, headers={"location": "/rfc/rfc9112.html"})
            return self.official(n, r)
        result = self.run_mock(doc)
        self.assert_not_ready(result, "RFC 9110: unexpected final URL 'https://www.rfc-editor.org/rfc/rfc9112.html'")
        self.assertTrue(result["documents"]["9110"]["redirected"])

    def test_redirect_to_a_non_document_page_is_not_ready(self):
        def doc(n, r):
            if n == "9112" and r.url.path.endswith(".html"):
                return httpx.Response(301, headers={"location": "/errata/rfc9112"})
            return self.official(n, r)
        result = self.run_mock(doc)
        self.assert_not_ready(result, "RFC 9112: unexpected final URL")

    def test_redirect_off_site_is_refused_and_not_ready(self):
        def doc(n, r):
            if n == "9110":
                return httpx.Response(302, headers={"location": "https://mirror.example/rfc/rfc9110.html"})
            return self.official(n, r)
        result = self.run_mock(doc)
        self.assert_not_ready(result, "RFC 9110: document REFUSED")

    def test_non_200_document_is_not_ready(self):
        result = self.run_mock(lambda n, r: self.official(n, r) if n == "9110"
                               else self.html("<title>RFC 9112: HTTP/1.1</title>", status=203))
        self.assert_not_ready(result, "RFC 9112: HTTP status 203, expected 200")

    def test_server_error_on_a_document_is_not_ready(self):
        result = self.run_mock(lambda n, r: self.official(n, r) if n == "9112" else self.html("<title>x</title>", 503))
        self.assert_not_ready(result, "RFC 9110: document HTTP_ERROR")


class Acceptance(unittest.TestCase):
    """Technical execution vs acceptance verdict: only READY / PASS with a completed runner is accepted."""

    def write(self, op, verdict):
        import tempfile
        d = Path(tempfile.mkdtemp())
        if op == "site-preflight":
            (d / "site_preflight.json").write_text(json.dumps({"verdict": verdict, "reasons": ["r"]}))
        else:
            (d / "qwen_gate.json").write_text(json.dumps({"verdict": {"verdict": verdict, "reasons": ["r"]}}))
        return d

    def test_only_ready_or_pass_with_exit_zero_is_accepted(self):
        self.assertTrue(G.acceptance("site-preflight", self.write("site-preflight", "READY"), 0)["accepted"])
        self.assertTrue(G.acceptance("qwen", self.write("qwen", "PASS"), 0)["accepted"])
        for op, verdict in (("site-preflight", "NOT_READY"), ("qwen", "FAIL"), ("qwen", "INCOMPLETE"),
                            ("site-preflight", "PASS"), ("qwen", "READY"), ("qwen", None)):
            with self.subTest(op=op, verdict=verdict):
                a = G.acceptance(op, self.write(op, verdict), 0)
                self.assertFalse(a["accepted"])
                self.assertEqual(a["technical_execution"], "COMPLETED")

    def test_blocked_or_crashed_runner_is_never_accepted_even_with_a_stale_pass_file(self):
        for code, technical in ((2, "BLOCKED"), (1, "ERROR"), (-1, "ERROR")):
            a = G.acceptance("qwen", self.write("qwen", "PASS"), code)
            self.assertEqual((a["technical_execution"], a["accepted"]), (technical, False))

    def test_missing_or_corrupt_evidence_is_no_verdict(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        a = G.acceptance("site-preflight", d, 0)
        self.assertEqual((a["verdict"], a["accepted"]), ("NO_VERDICT", False))
        (d / "site_preflight.json").write_text("{not json")
        self.assertFalse(G.acceptance("site-preflight", d, 0)["accepted"])

    def test_cli_exit_code_reflects_acceptance(self):
        self.assertEqual(G.main(["--acceptance", "site-preflight", "--technical-exit", "0", "--evidence-dir",
                                 str(self.write("site-preflight", "READY"))]), 0)
        self.assertEqual(G.main(["--acceptance", "site-preflight", "--technical-exit", "0", "--evidence-dir",
                                 str(self.write("site-preflight", "NOT_READY"))]), 1)


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
