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
        self.assertIn("rightware-corporations/jarvis-v2.0.git", code)
        self.assertIn("--recurse-submodules", code)
        # RIGHTWARE decision 08/11: no GitHub token in Kaggle; public clone only.
        for forbidden in ("GITHUB_TOKEN", "kaggle_secrets", "UserSecretsClient",
                          "x-access-token", "GIT_ASKPASS"):
            self.assertNotIn(forbidden, code)
        self.assertIn('GIT_TERMINAL_PROMPT="0"', code)
        self.assertIn("git", code)
        self.assertIn("qa.compare_models", code)
        self.assertIn("qwen3.5:2b", code)
        self.assertIn("qwen3.5:4b", code)
        self.assertIn("JARVIS_ISSA_QWEN_EVIDENCE_", code)
        self.assertIn("EXPECTED_SHA256", code)
        self.assertNotIn("git pull", code)
        self.assertNotIn("git reset", code)
        self.assertIn("nvidia-smi", "".join(cells[0]["source"]))
        # Each cell survives a kernel restart (no NameError on ROOT/REPO).
        for i, cell in enumerate(cells, 1):
            with self.subTest(cell=i):
                self.assertIn('ROOT = Path("/kaggle/working")', "".join(cell["source"]))
        # The evidence ZIP is written in a finally block, even if the run fails.
        last = ast.parse("".join(cells[2]["source"]))
        tries = [n for n in ast.walk(last) if isinstance(n, ast.Try) and n.finalbody]
        self.assertTrue(any("ZipFile" in ast.unparse(t.finalbody[-1]) or
                            any("ZipFile" in ast.unparse(x) for x in t.finalbody)
                            for t in tries))
        self.assertNotIn("check=True, env=os.environ)", "".join(cells[2]["source"]))


if __name__ == "__main__":
    unittest.main()
