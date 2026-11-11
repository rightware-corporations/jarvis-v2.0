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

    def test_preflight_requires_full_sha_and_digest(self):
        with self.assertRaises(RuntimeError):
            SM.preflight("abc", DIGEST)
        with self.assertRaises(RuntimeError):
            SM.preflight("0" * 40, DIGEST)          # not HEAD


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
        self.assertEqual(on, {"push": {"branches": ["feat/work05-product-agent"],
                                       "paths": ["ops/work05_smoke_request.json"]}})
        self.assertFalse((ROOT / "ops/work05_smoke_request.json").exists())

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


if __name__ == "__main__":
    unittest.main()
