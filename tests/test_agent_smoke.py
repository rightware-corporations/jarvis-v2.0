"""WORK-05 R1-F: real-Qwen smoke preparation (no model is called by these tests)."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from rightware import agent_smoke as SM

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/work05-qwen-smoke.yml"
DIGEST = "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04"
GOOD = dict(engine_id="ollama", model_digest=DIGEST, expected_digest=DIGEST,
            responses=[{"engine_id": "ollama", "tool_calls": [{"name": "web_read", "url": SM.URL,
                                                                 "arguments_sha256": "x"}], "content_chars": 0},
                       {"engine_id": "ollama", "tool_calls": [], "content_chars": 80}],
            completion="ANSWERED_WITH_SOURCES",
            outcomes=[{"tool": "web_read", "status": "OK", "evidence": {}}], flags=[],
            sources=[{"final_url": SM.URL, "status": 200}],
            answer="Segundo a página, este domínio serve para exemplos em documentação. Fonte: https://example.com/")


def classify(**changes):
    return SM.classify(**{**GOOD, **changes})


class Classification(unittest.TestCase):
    def test_pass_requires_everything(self):
        v = classify()
        self.assertEqual((v["verdict"], v["reasons"]), ("PASS", []))
        self.assertTrue(v["model_proposed_web_read"])
        self.assertFalse(v["answer_factually_verified"])

    def test_scripted_or_unpinned_runs_are_never_pass(self):
        self.assertEqual(classify(engine_id="fake")["verdict"], "INCOMPLETE")
        self.assertEqual(classify(model_digest="0" * 64)["verdict"], "INCOMPLETE")

    def test_model_must_have_proposed_the_tool_itself(self):
        v = classify(responses=[{"engine_id": "ollama", "tool_calls": [], "content_chars": 50}])
        self.assertEqual(v["verdict"], "FAIL")
        self.assertIn("the model never proposed web_read", v["reasons"])

    def test_fail_conditions(self):
        cases = {
            "web_read was proposed for a different URL": dict(responses=[{"engine_id": "ollama", "tool_calls": [
                {"name": "web_read", "url": "https://other.example/", "arguments_sha256": "x"}], "content_chars": 0}]),
            "the model proposed a tool other than web_read": dict(responses=GOOD["responses"] + [{"engine_id": "ollama",
                "tool_calls": [{"name": "windows_action", "url": None, "arguments_sha256": "y"}], "content_chars": 0}]),
            "completion HALTED": dict(completion="HALTED"),
            "the fixed page is not a recorded source": dict(sources=[]),
            "flag UNSUPPORTED_READ_CLAIM": dict(flags=["UNSUPPORTED_READ_CLAIM"]),
            "empty answer": dict(answer="  "),
        }
        for reason, change in cases.items():
            with self.subTest(reason=reason):
                v = classify(**change)
                self.assertEqual(v["verdict"], "FAIL")
                self.assertIn(reason, v["reasons"])

    def test_external_page_problems_are_incomplete_not_model_failures(self):
        for status in ("FAILED", "HTTP_ERROR"):
            with self.subTest(status=status):
                v = classify(outcomes=[{"tool": "web_read", "status": status, "evidence": {}}],
                             completion="TOOLS_FAILED", sources=[])
                self.assertEqual(v["verdict"], "INCOMPLETE")
        self.assertEqual(classify(completion="ERROR")["verdict"], "INCOMPLETE")

    def test_page_term_overlap_is_reported_not_required(self):
        v = classify(answer="Serve para outra coisa.")
        self.assertEqual(v["verdict"], "PASS")
        self.assertFalse(v["answer_mentions_page_terms"])


class Runner(unittest.TestCase):
    def test_plan_is_fixed_read_only_and_calls_no_model(self):
        out = subprocess.run([sys.executable, "-m", "rightware.agent_smoke", "--plan-only"], cwd=ROOT,
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        plan = json.loads(out.stdout)
        self.assertEqual((plan["url"], plan["capabilities"], plan["windows_actions"], plan["models_called"]),
                         ("https://example.com/", ["web"], False, False))
        self.assertEqual(plan["plan_sha256"], SM.plan_sha256())
        self.assertEqual((plan["model"], plan["model_digest"], plan["limits"]["max_tokens"],
                          plan["limits"]["deadline_seconds"]), ("qwen3.5:4b", DIGEST, 512, 300.0))
        self.assertLessEqual(plan["limits"]["tool_calls"], 3)
        self.assertLessEqual(plan["limits"]["max_turns"], 4)

    def test_session_is_built_with_web_only_and_no_actions(self):
        src = (ROOT / "rightware/agent_smoke.py").read_text(encoding="utf-8")
        self.assertIn('allow={"web"}', src)
        self.assertIn("actions=None", src)
        for forbidden in ("allow_actions", "WindowsActions(", "shell=True", "shell_exec", "file_write"):
            self.assertNotIn(forbidden, src)

    def test_recording_engine_sees_only_what_the_engine_returned(self):
        class Fake:
            engine_id = "fake"

            def generate(self, messages, **kw):
                return {"content": "", "tool_calls": [{"id": "1", "name": "web_read",
                                                       "arguments": json.dumps({"url": SM.URL})}]}
        rec = SM.RecordingEngine(Fake())
        rec.generate([])
        self.assertEqual(rec.responses[0]["tool_calls"][0]["url"], SM.URL)
        self.assertEqual(rec.responses[0]["engine_id"], "fake")

    def test_preflight_requires_full_sha_fixed_digest_and_approved_code(self):
        with self.assertRaises(RuntimeError):
            SM.preflight("abc")
        with self.assertRaisesRegex(RuntimeError, "fixed model digest"):
            SM.preflight(SM.EXPECTED_DIGEST[:40], "0" * 64)   # digest is fixed, never a parameter
        with self.assertRaises(Exception):
            SM.preflight("0" * 40)                  # unknown commit: refused before any model contact


class WorkflowContract(unittest.TestCase):
    def load(self):
        import yaml
        d = yaml.safe_load(WF.read_text(encoding="utf-8"))
        d["on"] = d.pop(True, d.get("on"))
        return d

    def setUp(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("pyyaml only in the pinned venv")

    def test_inert_until_an_authorised_request_file_exists(self):
        on = self.load()["on"]
        self.assertEqual(on, {"push": {"branches": ["develop"],
                                       "paths": ["ops/work05_smoke_request.json"]}})
        # Inertness comes from the path trigger + the authorisation gate, not from the file's absence:
        # on a request commit the file exists and this suite runs as GATE 2 (run 43113524962 defect).
        request = ROOT / "ops/work05_smoke_request.json"
        if request.exists():
            data = json.loads(request.read_text(encoding="utf-8"))
            self.assertEqual(set(data), SM.REQUEST_KEYS)
            self.assertEqual(data["experiment"], SM.EXPERIMENT)
        self.assertEqual(self.load()["env"]["BRANCH"], "develop")
        self.assertNotIn("feat/work05-product-agent", WF.read_text(encoding="utf-8"))

    def test_authorisation_gate_runs_before_any_install_or_model(self):
        steps = self.load()["jobs"]["smoke"]["steps"]
        names = [s.get("name", "") for s in steps]
        gate = next(i for i, n in enumerate(names) if n.startswith("GATE 0"))
        run = steps[gate]["run"]
        self.assertIn('--check-request --run-attempt "$GITHUB_RUN_ATTEMPT"', run)
        self.assertIn("APPROVED_SHA=", run)
        first_model = next(i for i, n in enumerate(names) if n.startswith("GATE 3"))
        self.assertLess(gate, first_model)
        smoke = next(s["run"] for s in steps if "rightware.agent_smoke --approved-code-sha" in s.get("run", ""))
        self.assertIn('--approved-code-sha "$APPROVED_SHA"', smoke)
        self.assertNotIn("GITHUB_SHA", smoke)

    def test_minimal_permissions_pinned_actions_no_secrets_evidence_always(self):
        d = self.load()
        self.assertEqual(d["permissions"], {"contents": "read"})
        text = WF.read_text(encoding="utf-8")
        for bad in ("secrets.", "workflow_dispatch", "pull_request", "--allow-actions", "schedule:"):
            self.assertNotIn(bad, text)
        steps = d["jobs"]["smoke"]["steps"]
        for s in steps:
            if "run" in s:
                self.assertNotIn("${{", s["run"])
            if "uses" in s:
                self.assertRegex(s["uses"], r"@[0-9a-f]{40}$")
        self.assertTrue(all(s.get("if") == "always()" for s in steps[-2:]))
        self.assertIn('! grep -q " skipped"', text)
        self.assertIn('[ "$GOT" = "$EXPECTED_DIGEST" ]', text)



def _req(**over):
    base = {"experiment": SM.EXPERIMENT, "request_id": 1, "approved_code_sha": "a" * 40,
            "plan_sha256": SM.plan_sha256(), "authorized_by": "operador RIGHTWARE, 2026-11-12"}
    base.update(over)
    return base


class SuiteOnARequestCommit(unittest.TestCase):
    """Regression for run 43113524962: GATE 2 runs this suite on the request commit itself."""

    def test_contract_tests_pass_when_a_request_file_is_present(self):
        import shutil
        import tempfile
        try:
            import yaml  # noqa: F401
        except ImportError:   # plain Python: WorkflowContract skips there; the venv job (no skips) runs this
            self.skipTest("pyyaml only in the pinned venv")
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(ROOT / "rightware", tmp / "rightware")
            (tmp / "tests").mkdir()
            shutil.copy(ROOT / "tests" / "test_agent_smoke.py", tmp / "tests")
            (tmp / ".github" / "workflows").mkdir(parents=True)
            shutil.copy(WF, tmp / ".github" / "workflows")
            (tmp / "ops").mkdir()
            (tmp / SM.REQUEST_PATH).write_text(json.dumps(_req()), encoding="utf-8")
            out = subprocess.run([sys.executable, "-m", "unittest", "tests.test_agent_smoke.WorkflowContract",
                                  "tests.test_agent_smoke.Classification"], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr[-2000:])
            self.assertNotIn("skipped", out.stderr.splitlines()[-1])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class AuthorisationPure(unittest.TestCase):
    OK = dict(trigger_sha="b" * 40, changed_files=[SM.REQUEST_PATH], previous_request_id=0,
              request_commits=1, run_attempt=1, approved_is_ancestor=True)

    def check(self, req, **over):
        return SM.validate_request(req, **{**self.OK, **over})

    def test_valid_request(self):
        self.assertEqual(self.check(_req()), [])

    def test_each_rule_refuses(self):
        cases = {
            "request keys must be exactly": (_req(extra=1), {}),
            "wrong experiment": (_req(experiment="OTHER"), {}),
            "request_id must be a positive integer": (_req(request_id=True), {}),
            "request_id must be exactly previous + 1 (replay or gap)": (_req(request_id=1), {"previous_request_id": 1}),
            "request_id must equal the number of request commits (single use)": (_req(request_id=2), {"previous_request_id": 1, "request_commits": 3}),
            "approved_code_sha must be a full lowercase 40-hex SHA": (_req(approved_code_sha="A" * 40), {}),
            "the request must be a separate commit after the approved code": (_req(approved_code_sha="b" * 40), {}),
            "plan_sha256 does not match the fixed plan": (_req(plan_sha256="0" * 64), {}),
            "authorized_by must be a short single-line text": (_req(authorized_by="a\nb"), {}),
            "the request commit may change only ops/work05_smoke_request.json": (_req(), {"changed_files": [SM.REQUEST_PATH, "rightware/agent/web.py"]}),
            "approved_code_sha is not an ancestor of the request commit": (_req(), {"approved_is_ancestor": False}),
            "re-runs are refused: push a new request instead": (_req(), {"run_attempt": 2}),
        }
        for reason, (req, over) in cases.items():
            with self.subTest(reason=reason):
                problems = self.check(req, **over)
                self.assertTrue(any(p.startswith(reason) for p in problems), problems)

    def test_empty_authorized_by_and_non_dict(self):
        self.assertIn("authorized_by must be a short single-line text", self.check(_req(authorized_by=" ")))
        self.assertTrue(self.check(["not", "a", "dict"]))


class AuthorisationGit(unittest.TestCase):
    """End to end on a throw-away git repository (no network, no model)."""

    def setUp(self):
        import tempfile
        self.dir = Path(tempfile.mkdtemp())
        self.git("init", "-q", "-b", "develop")
        self.git("config", "user.email", "ci@example.invalid")
        self.git("config", "user.name", "ci")
        (self.dir / "rightware").mkdir()
        (self.dir / "rightware" / "code.py").write_text("x = 1\n")
        self.commit("code")

    def git(self, *a):
        return subprocess.check_output(["git", *a], cwd=self.dir, text=True).strip()

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def request(self, rid, approved, extra_change=False):
        (self.dir / "ops").mkdir(exist_ok=True)
        (self.dir / SM.REQUEST_PATH).write_text(json.dumps(_req(request_id=rid, approved_code_sha=approved)))
        if extra_change:
            (self.dir / "rightware" / "code.py").write_text("x = 2  # sneaked in\n")
        return self.commit(f"request {rid}")

    def test_first_authorised_request_passes(self):
        approved = self.git("rev-parse", "HEAD")
        trigger = self.request(1, approved)
        r = SM.check_request(1, root=self.dir)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["approved_code_sha"], r["trigger_sha"], r["request_id"]), (approved, trigger, 1))

    def test_rerun_of_the_same_request_is_refused(self):
        self.request(1, self.git("rev-parse", "HEAD"))
        r = SM.check_request(2, root=self.dir)
        self.assertFalse(r["ok"])

    def test_replaying_an_old_request_id_is_refused(self):
        approved = self.git("rev-parse", "HEAD")
        self.request(1, approved)
        (self.dir / "rightware" / "code.py").write_text("x = 3\n")
        approved2 = self.commit("more code")
        self.request(1, approved2)                       # same id again
        self.assertFalse(SM.check_request(1, root=self.dir)["ok"])

    def test_second_request_with_next_id_passes(self):
        self.request(1, self.git("rev-parse", "HEAD"))
        (self.dir / "rightware" / "code.py").write_text("x = 3\n")
        approved2 = self.commit("fix")
        self.request(2, approved2)
        self.assertTrue(SM.check_request(1, root=self.dir)["ok"])

    def test_code_changed_in_the_request_commit_is_refused(self):
        self.request(1, self.git("rev-parse", "HEAD"), extra_change=True)
        r = SM.check_request(1, root=self.dir)
        self.assertFalse(r["ok"])
        self.assertTrue(any("may change only" in p for p in r["problems"]))

    def test_approved_sha_outside_history_is_refused(self):
        self.request(1, "c" * 40)
        self.assertFalse(SM.check_request(1, root=self.dir)["ok"])

    def test_preflight_refuses_running_code_that_differs_from_the_approved_code(self):
        approved = self.git("rev-parse", "HEAD")
        (self.dir / "rightware" / "code.py").write_text("x = 9  # not approved\n")
        self.commit("unapproved change")
        with self.assertRaisesRegex(RuntimeError, "differs from the approved code"):
            SM.preflight(approved, root=self.dir)

    def test_preflight_accepts_only_the_request_file_beyond_the_approved_code(self):
        approved = self.git("rev-parse", "HEAD")
        self.request(1, approved)
        with self.assertRaisesRegex(RuntimeError, "OpenJarvis pin mismatch"):   # diff gate passed; no submodule here
            SM.preflight(approved, root=self.dir)

    def test_missing_request_file_fails_closed(self):
        self.assertEqual(SM.check_request(1, root=self.dir)["problems"], ["request file missing or not JSON at HEAD"])


if __name__ == "__main__":
    unittest.main()
