"""Contracts for the one-cell public OpenJarvis Kaggle notebook (no credentials)."""
import ast
import json
from pathlib import Path
import unittest


class NoTokenKaggleNotebookTests(unittest.TestCase):
    def test_single_cell_and_nested_evaluator_syntax(self):
        target = Path(__file__).resolve().parents[1] / "qa/JARVIS_ISSA_KAGGLE_NO_TOKEN.ipynb"
        notebook = json.loads(target.read_text(encoding="utf-8"))
        cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(cells), 1)
        source = "".join(cells[0]["source"])
        tree = ast.parse(source)
        nested = [
            n.value.value for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and
            any(isinstance(t, ast.Name) and t.id == "evaluator" for t in n.targets)
            and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
        ]
        self.assertEqual(len(nested), 1)
        ast.parse(nested[0])
        self.assertIn("Jarvis, assistente pessoal do Issa", source)
        self.assertIn("f21d902f4d3bd7f0f3f138f1a4613019a394b549", source)
        self.assertIn("https://github.com/open-jarvis/OpenJarvis.git", source)
        self.assertIn("qwen3.5:2b", source)
        self.assertIn("qwen3.5:4b", source)
        self.assertIn("JARVIS_ISSA_NO_TOKEN_", source)
        self.assertIn("OLLAMA_ARCHIVE_SHA256", source)
        self.assertNotIn("GITHUB_TOKEN", source)
        self.assertNotIn("kaggle_secrets", source)
        self.assertNotIn("https://github.com/rightware-corporations", source)
        self.assertNotIn("git pull", source)
        self.assertNotIn("git reset", source)


if __name__ == "__main__":
    unittest.main()
