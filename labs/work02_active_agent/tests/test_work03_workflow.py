"""WORK-03 static/local checks of the manual CPU workflow (no runner, no model).
Results are FAKE / static: they say nothing about Qwen."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

import yaml

from _support import LAB, PIN, REPO

WF = REPO / ".github" / "workflows" / "work03-cpu-agent.yml"


def load():
    data = yaml.safe_load(WF.read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))      # YAML 1.1 parses 'on' as True
    return data


def steps():
    return load()["jobs"]["work03"]["steps"]


def step(prefix):
    return next(s for s in steps() if s["name"].startswith(prefix))


class WorkflowContract(unittest.TestCase):
    def test_manual_trigger_only(self):
        self.assertEqual(list(load()["on"]), ["workflow_dispatch"])

    def test_minimal_permissions_and_no_secrets(self):
        data = load()
        self.assertEqual(data["permissions"], {"contents": "read"})
        text = WF.read_text(encoding="utf-8")
        self.assertNotIn("secrets.", text)
        self.assertNotIn("pull_request", text)
        self.assertIs(step("Checkout")["with"]["persist-credentials"], False)

    def test_inputs_never_interpolated_inside_shell_scripts(self):
        for s in steps():
            if "run" in s:
                with self.subTest(step=s["name"]):
                    self.assertNotRegex(s["run"], r"\$\{\{\s*(inputs|github\.event)")

    def test_explicit_revision_and_pin(self):
        self.assertEqual(step("Checkout")["with"]["ref"], "${{ inputs.sha }}")
        self.assertEqual(load()["env"]["PIN"], PIN)
        self.assertIn('test "$(git rev-parse HEAD)" = "$SHA"', step("GATE 0 —")["run"])

    def test_ollama_archive_hash_matches_the_verified_one(self):
        nb = json.loads((REPO / "qa/JARVIS_ISSA_KAGGLE.ipynb").read_text(encoding="utf-8"))
        code = "".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
        self.assertIn(load()["env"]["OLLAMA_SHA256"], code)
        self.assertIn("sha256sum -c", step("GATE 2")["run"])
        self.assertNotRegex(WF.read_text(encoding="utf-8"), r"curl[^\n]*\|\s*(sh|bash)")

    def test_loopback_only_and_no_cloud(self):
        run = step("GATE 2")["run"]
        self.assertIn("OLLAMA_HOST=127.0.0.1:11434", run)
        self.assertIn("OLLAMA_NO_CLOUD=1", run)
        self.assertIn("then echo \"Ollama listens beyond loopback\"; exit 1", run)

    def test_gate5_needs_typed_authorization_and_keeps_criteria(self):
        g5 = step("GATE 5")
        self.assertIn("AUTORIZO-WORK03-GATE5", g5["if"])
        self.assertIn("AUTORIZO-WORK03-GATE5", step("GATE 0a")["run"])
        for flag in ("--n 10", "--security-n 3", "--allow-cpu", '--expect-sha "$SHA"'):
            self.assertIn(flag, g5["run"])

    def test_third_party_actions_pinned_by_full_sha(self):
        for s in steps():
            if "uses" in s:
                with self.subTest(uses=s["uses"]):
                    self.assertRegex(s["uses"], r"^actions/[a-z-]+@[0-9a-f]{40}$")

    def test_disk_budget_is_derived_and_fits_documented_runner(self):
        env = load()["env"]
        # steady peak ~5.8 GiB measured/bounded (+50 % margin) and <= 14 GB documented SSD
        self.assertEqual(int(env["MIN_FREE_DISK_GIB"]), 9)
        self.assertLessEqual(int(env["MIN_FREE_DISK_GIB"]), 14)
        self.assertIn("MODEL_DISK_BOUND_GIB", step("GATE 3")["run"])
        self.assertIn("ENVIRONMENT BLOCKED", step("GATE 3")["run"])
        self.assertIn("zstd absent", step("GATE 2")["run"])

    def test_capacity_probe_is_read_only(self):
        probe = yaml.safe_load((REPO / ".github/workflows/foundation.yml").read_text(encoding="utf-8"))["jobs"]["runner-capacity"]
        run = probe["steps"][0]["run"]
        self.assertEqual(probe["runs-on"], "ubuntu-24.04")
        for forbidden in ("curl", "wget", "apt", "pip", "ollama", "sudo"):
            self.assertNotIn(forbidden, run)

    def test_limits_and_evidence_always_uploaded(self):
        job = load()["jobs"]["work03"]
        self.assertLessEqual(job["timeout-minutes"], 350)
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        up = step("Upload evidence")
        self.assertEqual(up["if"], "always()")
        self.assertTrue(up["uses"].startswith("actions/upload-artifact@"))
        self.assertEqual(step("Classify")["if"], "always()")

    def test_foundation_ci_does_not_run_inference(self):
        text = (REPO / ".github/workflows/foundation.yml").read_text(encoding="utf-8")
        for command in ("ollama serve", "ollama pull", "run_real.py", "gate4_tool_smoke", "workflow_dispatch"):
            self.assertNotIn(command, text.lower())


class Classification(unittest.TestCase):
    def classify(self, lines, up_to="5"):
        script = step("Classify")["run"].split("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        script = textwrap.dedent(script)
        self.assertNotIn("pkill", script)
        with tempfile.TemporaryDirectory() as d:
            Path(d, "gates.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")
            summ = Path(d, "step_summary.md")
            env = dict(os.environ, EVID=d, RUNNER_TEMP=d, UP_TO=up_to, JOB_STATUS="x",
                       GITHUB_STEP_SUMMARY=str(summ))
            subprocess.run([sys.executable, "-c", script], env=env, check=True, capture_output=True)
            return json.loads(Path(d, "work03-summary.json").read_text(encoding="utf-8"))

    INFRA = [{"gate": g, "status": "PASS"} for g in ("0a", "0", "1", "2")]

    def test_full_pass_and_fail(self):
        ok = self.INFRA + [{"gate": "3", "status": "QWEN REAL PASS"}, {"gate": "4", "status": "QWEN REAL PASS"}]
        self.assertEqual(self.classify(ok + [{"gate": "5", "status": "QWEN REAL PASS"}])["overall"], "QWEN REAL PASS")
        self.assertEqual(self.classify(ok + [{"gate": "5", "status": "QWEN REAL FAIL"}])["overall"], "QWEN REAL FAIL")

    def test_model_failure_at_gate4_is_not_hidden(self):
        r = self.classify(self.INFRA + [{"gate": "3", "status": "QWEN REAL PASS"},
                                        {"gate": "4", "status": "QWEN REAL FAIL"}], up_to="5")
        self.assertEqual(r["overall"], "QWEN REAL FAIL (GATE 4)")
        self.assertEqual(r["gates"]["5"], "NOT RUN")

    def test_infrastructure_stop_is_environment_blocked(self):
        r = self.classify([{"gate": "0a", "status": "PASS"}, {"gate": "0", "status": "PASS"},
                           {"gate": "1", "status": "ENVIRONMENT BLOCKED"}], up_to="3")
        self.assertTrue(r["overall"].startswith("ENVIRONMENT BLOCKED"))
        r = self.classify(self.INFRA[:3], up_to="3")          # GATE 2 never recorded
        self.assertEqual(r["overall"], "ENVIRONMENT BLOCKED")

    def test_partial_run_says_work02_not_run(self):
        r = self.classify(self.INFRA + [{"gate": "3", "status": "QWEN REAL PASS"}], up_to="3")
        self.assertEqual(r["overall"], "STOPPED AFTER GATE 3 (WORK-02 NOT RUN)")


class Gate4AndRunner(unittest.TestCase):
    def test_gate4_script_fake(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d, "gate4.json")
            rc = subprocess.run([sys.executable, str(LAB / "gate4_tool_smoke.py"), "--fake", "--out", str(out)],
                                capture_output=True, text=True)
            self.assertEqual(rc.returncode, 0, rc.stderr[-400:])
            data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "FAKE PASS")
        self.assertTrue(data["model_called_list_workspace"])
        self.assertEqual([t["tool"] for t in data["trace"]], ["list_workspace"])

    def test_runner_exposes_environment_timeouts_without_touching_criteria(self):
        text = (LAB / "run_real.py").read_text(encoding="utf-8")
        self.assertIn('"--engine-timeout"', text)
        self.assertIn("OllamaEngine(host=HOST, timeout=args.engine_timeout)", text)
        from w02lab import assess
        self.assertEqual(assess.ACCEPT_RATIO, 0.8)
        self.assertRegex(text, r'if args\.n < 10 and not args\.fake')


if __name__ == "__main__":
    unittest.main()
