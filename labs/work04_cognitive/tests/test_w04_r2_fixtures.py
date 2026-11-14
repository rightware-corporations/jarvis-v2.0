"""WORK-04 R2: offline fixture coverage and legitimate-fact preservation."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from w04lab import assess, scenarios, source_guard  # noqa: E402


class Work04SourcePreservation(unittest.TestCase):
    def test_35_primary_documents_are_byte_identical_after_guard(self):
        # The read boundary must NOT destroy facts, dates or amounts in
        # primary sources merely because the wording varies across layouts.
        for family, seed in assess.plan():
            with self.subTest(family=family, seed=seed):
                with tempfile.TemporaryDirectory() as td:
                    scn = scenarios.generate(Path(td), seed, family)
                    for name, original in scn.sources_text().items():
                        guarded, audit = source_guard.isolate_instructions(original)
                        self.assertEqual(guarded, original, name)
                        self.assertEqual(audit["quarantined_lines"], 0, name)

    def test_all_five_original_hostile_notes_are_quarantined(self):
        # Diagnostic property of the guard only; not evidence of resisting
        # Qwen or arbitrary data-poisoning attacks.
        for seed in range(4600, 4605):
            with self.subTest(seed=seed):
                with tempfile.TemporaryDirectory() as td:
                    scn = scenarios.generate(Path(td), seed, "HOSTILE")
                    original = (scn.input_dir / scenarios.TRAP_NAME).read_text(encoding="utf-8")
                    sanitized, audit = source_guard.isolate_instructions(original)
                    injected = scenarios.INJECTIONS[seed % len(scenarios.INJECTIONS)]
                    self.assertIn(injected, original)
                    self.assertNotIn(injected, sanitized)
                    self.assertGreater(audit["quarantined_lines"], 0)
                    self.assertEqual((scn.input_dir / scenarios.TRAP_NAME).read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
