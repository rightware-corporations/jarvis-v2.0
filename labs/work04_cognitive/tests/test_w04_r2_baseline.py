"""R2 regression: historical WORK-04 rev.1 files remain byte-identical.

Works from source archives WITHOUT .git; GitHub blob SHA1 includes the git
'blob <byte-length>\\0' prefix. It therefore protects the historical runtime
semantics against accidental reuse of new R2 logic or evaluator changes.
"""
from pathlib import Path
import hashlib
import unittest


LAB = Path(__file__).resolve().parents[1]


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\\0" + data).hexdigest()


class HistoricalRev1Immutability(unittest.TestCase):
    EXPECTED = {
        "w04lab/harness.py": "d6e7a8b33c79ea96f0a66175d7366573230eda08",
        "w04lab/oracle.py": "c84d3820eb4f2b90602947f1907cb5f0c062458f",
        "w04lab/assess.py": "1acabfec27ac85d220bf19e6909359f186618b0d",
        "run_real.py": "7885cce49bf2d02448635d85967e153a63f23f2e",
    }

    def test_original_benchmark_modules_match_frozen_revision(self):
        for relative, blob in self.EXPECTED.items():
            with self.subTest(file=relative):
                self.assertEqual(git_blob_sha(LAB / relative), blob)

    def test_r2_does_not_import_orchestrator_from_rev1(self):
        text = (LAB / "run_smoke_r2.py").read_text(encoding="utf-8")
        self.assertIn("from w04lab import harness_r2 as harness", text)
        self.assertNotIn("from w04lab import harness, scenarios", text)
        r2 = (LAB / "w04lab/harness_r2.py").read_text(encoding="utf-8")
        self.assertIn("oracle_r2 as oracle", r2)

    def test_rev1_run_real_remains_untouched(self):
        original = (LAB / "run_real.py").read_text(encoding="utf-8")
        self.assertIn("from w04lab import assess, fake_engines, harness", original)
        self.assertNotIn("harness_r2", original)


if __name__ == "__main__":
    unittest.main()
