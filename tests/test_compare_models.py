"""No model download or network needed: focused benchmark preflight tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from qa import compare_models as bench


class CompareModelsTests(unittest.TestCase):
    def test_corpus_is_six_fixed_synthetic_turns(self):
        self.assertEqual(len(bench.QUESTIONS), 6)
        self.assertEqual(len({q["id"] for q in bench.QUESTIONS}), 6)
        self.assertIn("Issa", bench.QUESTIONS[0]["question"] + bench.runtime.ROOT.joinpath("configs/local.toml").read_text())
        self.assertIn("fictício", bench.QUESTIONS[1]["question"])
        self.assertIn("orçamento", bench.QUESTIONS[4]["question"])

    def test_atomic_evidence_creates_directory(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence" / "report.json"
            bench.atomic_json(path, {"result": "REVIEW", "name": "Issa"})
            self.assertEqual(json.loads(path.read_text())["name"], "Issa")
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_cloud_model_argument_fails_before_inference(self):
        with patch.object(sys, "argv", ["compare", "--models", "qwen:cloud"]):
            with self.assertRaises(SystemExit) as caught:
                bench.main()
            self.assertEqual(caught.exception.code, 2)

    def test_stale_profile_rejected_before_model_request(self):
        with (patch.object(sys, "argv", ["compare"]),
              patch.object(bench.runtime, "prepare_config",
                           return_value={"agent": {"default_system_prompt": "OpenJarvis"}}),
              patch.object(bench.runtime, "verify_source") as verify):
            with self.assertRaisesRegex(RuntimeError, "Stale local Jarvis identity"):
                bench.main()
            verify.assert_not_called()

    def test_missing_4b_fails_closed(self):
        config = {"agent": {"default_system_prompt": "Jarvis do Issa"}}
        with (patch.object(sys, "argv", ["compare"]),
              patch.object(bench.runtime, "prepare_config", return_value=config),
              patch.object(bench.runtime, "verify_source"),
              patch.object(bench, "installed_models", return_value={"qwen3.5:2b"})):
            with self.assertRaisesRegex(RuntimeError, "qwen3.5:4b"):
                bench.main()


if __name__ == "__main__":
    unittest.main()
