"""Static contract of the WORK-04 manual workflow (no runner, no model)."""
from pathlib import Path
import re
import unittest

import yaml

REPO = Path(__file__).resolve().parents[3]
WF = REPO / ".github/workflows/work04-cognitive.yml"
W3 = REPO / ".github/workflows/work03-cpu-agent.yml"


def load(p=WF):
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["on"] = d.pop(True, d.get("on"))
    return d


def steps(p=WF, job="work04"):
    return load(p)["jobs"][job]["steps"]


def step(prefix):
    return next(s for s in steps() if s["name"].startswith(prefix))


class Work04Workflow(unittest.TestCase):
    def test_manual_only_minimal_permissions_no_secrets(self):
        d = load()
        self.assertEqual(list(d["on"]), ["workflow_dispatch"])
        self.assertEqual(d["permissions"], {"contents": "read"})
        text = WF.read_text(encoding="utf-8")
        self.assertNotIn("secrets.", text)
        self.assertNotIn("pull_request", text)

    def test_inputs_never_interpolated_in_shell_and_actions_pinned(self):
        for s in steps():
            if "run" in s:
                self.assertNotRegex(s["run"], r"\$\{\{\s*(inputs|github\.event)")
            if "uses" in s:
                self.assertRegex(s["uses"], r"^actions/[a-z-]+@[0-9a-f]{40}$")

    def test_infrastructure_gates_identical_to_the_real_work03_run(self):
        w3 = {s["name"]: s.get("run") for s in steps(W3, "work03")}
        for name in ("GATE 0 — integrity", "GATE 1 — environment", "GATE 2 — official Ollama", "GATE 3 — real model"):
            mine = next(s for s in steps() if s["name"].startswith(name))
            theirs = next(v for k, v in w3.items() if k.startswith(name))
            if name.startswith("GATE 0"):
                theirs = theirs.replace("labs/work02_active_agent/gate4_tool_smoke.py", "labs/work04_cognitive/run_real.py")
            with self.subTest(gate=name):
                self.assertEqual(mine["run"], theirs)

    def test_digest_checked_in_job_before_benchmark(self):
        names = [s["name"] for s in steps()]
        self.assertLess(names.index(step("GATE 3b").get("name")), names.index(step("WORK-04 benchmark")["name"]))
        self.assertIn('if [ "$GOT" != "$DIGEST" ]', step("GATE 3b")["run"])
        self.assertEqual(load()["on"]["workflow_dispatch"]["inputs"]["expected_digest"]["default"],
                         "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04")

    def test_benchmark_needs_typed_authorization_and_fixed_n(self):
        b = step("WORK-04 benchmark")
        self.assertIn("AUTORIZO-WORK04-BENCHMARK", b["if"])
        self.assertIn("AUTORIZO-WORK04-BENCHMARK", step("GATE 0a")["run"])
        for flag in ("--n-per-family 5", "--allow-cpu", '--expected-digest "$DIGEST"', '--expect-sha "$SHA"'):
            self.assertIn(flag, b["run"])
        self.assertEqual(load()["on"]["workflow_dispatch"]["inputs"]["run_benchmark"]["default"], "no")

    def test_evidence_always_uploaded_and_job_limited(self):
        job = load()["jobs"]["work04"]
        self.assertLessEqual(job["timeout-minutes"], 350)
        self.assertEqual(step("Upload evidence")["if"], "always()")
        self.assertEqual(step("Classify")["if"], "always()")


if __name__ == "__main__":
    unittest.main()
