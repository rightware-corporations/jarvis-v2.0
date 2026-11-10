"""WORK-04 R2 smoke runner contract: no inference during this suite."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "labs/work04_cognitive/run_smoke_r2.py"


class SmokeContract(unittest.TestCase):
    def plan(self, n):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan-only", "--n-cases", str(n)],
            cwd=REPO, capture_output=True, text=True,
        )

    def test_three_case_first_stage_is_fixed_and_diagnostic_only(self):
        process = self.plan(3)
        self.assertEqual(process.returncode, 0, process.stderr)
        output = json.loads(process.stdout)
        self.assertEqual(output["cases"], [
            ["EVOL", 4001], ["HOSTILE", 4601], ["HOSTILE", 4604]
        ])
        self.assertEqual(output["count"], 3)
        self.assertFalse(output["models_called"])
        self.assertEqual(output["experiment"], "WORK04_R2_SMOKE_NOT_BENCHMARK")

    def test_eight_case_second_stage_is_stratified(self):
        process = self.plan(8)
        self.assertEqual(process.returncode, 0, process.stderr)
        output = json.loads(process.stdout)
        self.assertEqual(output["count"], 8)
        self.assertEqual({row[0] for row in output["cases"]},
                         {"EVOL", "CONTRA", "TEMPORAL", "MISSING",
                          "CONSISTENT", "RECOVERY", "HOSTILE"})
        self.assertEqual(len(set(map(tuple, output["cases"]))), 8)

    def test_original_35_case_mode_cannot_be_requested_here(self):
        process = self.plan(35)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("invalid choice", process.stderr)

    def test_runner_distinguishes_smoke_from_historical_acceptance(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("WORK04 QWEN REAL 0/35 NOT ACCEPTED", text)
        self.assertIn("smoke_metrics_r2.summarize(", text)
        self.assertIn("DIAGNOSTIC ONLY", (REPO / "labs/work04_cognitive/w04lab/smoke_metrics_r2.py").read_text(encoding="utf-8"))
        self.assertNotIn("from w04lab.assess import assess", text)


if __name__ == "__main__":
    unittest.main()
