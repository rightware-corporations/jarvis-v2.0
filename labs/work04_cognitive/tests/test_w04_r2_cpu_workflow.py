"""Static contract of the R2 real-Qwen CPU workflow and the CPU mode of the
R2 smoke runner. No runner, no Ollama, no model: FAKE/deterministic only."""
from pathlib import Path
import hashlib
import re
import runpy
import subprocess
import sys
import unittest

import yaml

REPO = Path(__file__).resolve().parents[3]
WF = REPO / ".github/workflows/work04-r2-qwen-cpu.yml"
REV1_WF = REPO / ".github/workflows/work04-cognitive.yml"
SCRIPT = REPO / "labs/work04_cognitive/run_smoke_r2.py"


def load(p=WF):
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["on"] = d.pop(True, d.get("on"))
    return d


def steps():
    return load()["jobs"]["r2cpu"]["steps"]


def blob(p: Path) -> str:
    data = p.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class R2CpuWorkflow(unittest.TestCase):
    def test_only_the_versioned_request_on_the_r2_branch_triggers_it(self):
        on = load()["on"]
        self.assertEqual(list(on), ["push"])
        self.assertEqual(on["push"], {"branches": ["feat/work04-r2-semantic-safety"],
                                      "paths": ["labs/work04_cognitive/r2_cpu_run_request.json"]})
        gate = next(s["run"] for s in steps() if s["name"].startswith("GATE 0a"))
        self.assertIn('[ "$GITHUB_REF" = "refs/heads/$R2_BRANCH" ]', gate)
        self.assertIn('d["mode"] in ("infra","1case")', gate)
        self.assertLess(next(i for i, s in enumerate(steps()) if s.get("uses", "").startswith("actions/checkout")),
                        next(i for i, s in enumerate(steps()) if s["name"].startswith("GATE 0a")))

    def test_request_file_is_valid_and_names_one_allowed_mode(self):
        import json
        d = json.loads((REPO / "labs/work04_cognitive/r2_cpu_run_request.json").read_text(encoding="utf-8"))
        self.assertEqual(set(d), {"experiment", "mode", "request_id", "authorized_by"})
        self.assertEqual(d["experiment"], "WORK04_R2_CPU_SMOKE")
        self.assertIn(d["mode"], ("infra", "1case"))
        self.assertIsInstance(d["request_id"], int)

    def test_minimal_permissions_no_secrets_no_expression_injection(self):
        d = load()
        self.assertEqual(d["permissions"], {"contents": "read"})
        text = WF.read_text(encoding="utf-8")
        for bad in ("secrets.", "pull_request", "workflow_dispatch", "schedule", "GITHUB_TOKEN"):
            self.assertNotIn(bad, text)
        for s in steps():
            if "run" in s:
                self.assertNotIn("${{", s["run"])
            if "uses" in s:
                self.assertRegex(s["uses"], r"@[0-9a-f]{40}$")
            if s.get("uses", "").startswith("actions/checkout"):
                self.assertFalse(s["with"]["persist-credentials"])

    def test_same_proven_runtime_pins_as_work04_rev1(self):
        mine, rev1 = load()["env"], load(REV1_WF)["env"]
        for k in ("PIN", "OLLAMA_VERSION", "OLLAMA_SHA256", "MODEL", "UV_VERSION", "JARVIS_NUM_CTX"):
            self.assertEqual(mine[k], rev1[k], k)
        self.assertEqual(mine["EXPECTED_DIGEST"],
                         "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04")

    def test_gates_precede_any_inference_and_digest_fails_closed(self):
        names = [s["name"] for s in steps()]
        idx = {n.split(" ")[0] + " " + n.split(" ")[1]: i for i, n in enumerate(names)}
        smoke = [i for i, s in enumerate(steps()) if "run_smoke_r2.py" in s.get("run", "")]
        self.assertEqual(len(smoke), 2)
        for gate in ("GATE 0", "GATE 1", "GATE 1b", "GATE 2", "GATE 3"):
            self.assertLess(idx[gate], min(smoke), gate)
        g3 = next(s["run"] for s in steps() if s["name"].startswith("GATE 3"))
        self.assertIn('if [ "$GOT" != "$EXPECTED_DIGEST" ]', g3)
        g0 = next(s["run"] for s in steps() if s["name"].startswith("GATE 0 "))
        self.assertIn("merge-base --is-ancestor", g0)
        self.assertIn("dcc23f365aedf741018b4af6ffa3d721c4c07a46", g0)

    def test_smoke_is_explicit_cpu_and_at_most_one_scenario(self):
        runs = [s for s in steps() if "run_smoke_r2.py" in s.get("run", "")]
        infra, one = runs
        self.assertEqual(infra["if"], "env.MODE == 'infra'")
        self.assertIn("--preflight-only", infra["run"])
        self.assertEqual(one["if"], "env.MODE == '1case'")
        self.assertIn("--n-cases 1", one["run"])
        for s in runs:
            self.assertIn("--device cpu", s["run"])
            self.assertIn('--expect-sha "$GITHUB_SHA"', s["run"])
            self.assertIn('--expected-digest "$EXPECTED_DIGEST"', s["run"])
        text = WF.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"--n-cases\s+(3|8)")
        self.assertNotIn("run_real.py --", text)

    def test_evidence_preserved_even_on_failure(self):
        tail = steps()[-2:]
        self.assertTrue(all(s.get("if") == "always()" for s in tail))
        self.assertIn("SHA256SUMS", tail[0]["run"])
        self.assertEqual(tail[1]["with"]["path"], "${{ runner.temp }}/r2-evidence")
        self.assertIn("smoke-console.log", WF.read_text(encoding="utf-8"))

    def test_rev1_workflow_is_byte_identical_to_the_one_registered_on_main(self):
        self.assertEqual(blob(REV1_WF), "01cec5ab626dd00100f0af18d1637a58a72f3cef")


class R2SmokeCpuMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = runpy.run_path(str(SCRIPT), run_name="contract_test")

    def plan(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "--plan-only", *extra],
                              cwd=REPO, capture_output=True, text=True)

    def test_single_case_is_the_first_preregistered_case(self):
        import json
        p = self.plan("--n-cases", "1", "--device", "cpu")
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual((out["cases"], out["device"], out["models_called"]), ([["EVOL", 4001]], "cpu", False))

    def test_default_device_stays_gpu(self):
        import json
        self.assertEqual(json.loads(self.plan().stdout)["device"], "gpu")
        self.assertNotEqual(self.plan("--device", "tpu").returncode, 0)

    def test_residency_rules_per_device(self):
        ok = self.ns["residency_ok"]
        m = "qwen3.5:4b"
        self.assertTrue(ok([{"name": m, "size": 5, "size_vram": 5}], "gpu")[0])
        self.assertFalse(ok([{"name": m, "size": 5, "size_vram": 0}], "gpu")[0])
        self.assertTrue(ok([{"name": m, "size": 5, "size_vram": 0}], "cpu")[0])
        self.assertFalse(ok([{"name": m, "size": 5, "size_vram": 3}], "cpu")[0])   # silent offload
        self.assertFalse(ok([], "cpu")[0])                                        # not loaded
        self.assertFalse(ok([{"name": "other", "size": 5, "size_vram": 0}], "cpu")[0])

    def test_cpu_mode_keeps_every_preflight_control(self):
        text = SCRIPT.read_text(encoding="utf-8")
        pre = text[text.index("def preflight("):text.index("def main(")]
        for control in ('sha != expected_sha', 'status", "--porcelain"', "!= PIN", "OLLAMA_VERSION",
                        '!= expected_digest', "validate_ollama_binding()", "validate_model_residency(device)"):
            self.assertIn(control, pre)
        self.assertIn("cpu_resources()", pre)
        self.assertIn("pass --device cpu explicitly", pre)
        self.assertIn("--device cpu requires an explicit --evidence-dir", text)
        self.assertLess(text.index("info = preflight("), text.index("if args.preflight_only:"))
        self.assertLess(text.index("if args.preflight_only:"), text.index("for family, seed in CASES"))

    def test_cpu_resource_envelope_matches_work03_runner(self):
        self.assertEqual((self.ns["MIN_CPU_RAM_GIB"], self.ns["MIN_CPU_COUNT"]), (14, 4))


if __name__ == "__main__":
    unittest.main()
