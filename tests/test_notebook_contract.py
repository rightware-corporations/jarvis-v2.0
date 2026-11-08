"""Static validation of the Kaggle handoff notebook without running it."""
import ast
import json
from pathlib import Path
import unittest


class KaggleNotebookContracts(unittest.TestCase):
    def test_notebook_is_parseable_and_has_fixed_evidence_flow(self):
        path = Path(__file__).resolve().parents[1] / "qa" / "JARVIS_ISSA_KAGGLE.ipynb"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["nbformat"], 4)
        cells = [c for c in data["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(cells), 3)
        code = "\n".join("".join(c["source"]) for c in cells)
        for i, cell in enumerate(cells, 1):
            with self.subTest(cell=i):
                ast.parse("".join(cell["source"]))
        self.assertIn('UserSecretsClient().get_secret("GITHUB_TOKEN")', code)
        self.assertIn("git", code)
        self.assertIn("qa.compare_models", code)
        self.assertIn("qwen3.5:2b", code)
        self.assertIn("qwen3.5:4b", code)
        self.assertIn("JARVIS_ISSA_QWEN_EVIDENCE_", code)
        self.assertIn("EXPECTED_SHA256", code)
        self.assertNotIn("git pull", code)
        self.assertNotIn("git reset", code)


if __name__ == "__main__":
    unittest.main()
