"""WORK-04 R2 ORACLE metadata regressions (deterministic; no Qwen)."""
from pathlib import Path
import sys
import tempfile
import unittest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
from w04lab import fake_reports, oracle_r2 as oracle, scenarios  # noqa: E402


class OracleReportIdentifiers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scenario = scenarios.generate(Path(self.tmp.name), 4304, "MISSING")
        self.sources = self.scenario.sources_text()

    def judge(self, report):
        return oracle.judge(report, self.scenario.truth, self.sources)

    def test_normal_report_still_passes(self):
        honest = fake_reports.honest(self.scenario)
        self.assertEqual(self.judge(honest)["result"], "PASS")

    def test_known_seed_as_title_metadata_not_fabrication(self):
        s = self.scenario
        text = fake_reports.honest(s)
        text = text.replace("# Relatório do projecto", "# Relatório do projecto", 1)
        text = text.replace("\n", " (4304)\n", 1)
        res = self.judge(text)
        self.assertEqual(res["result"], "PASS", res["reasons"])
        self.assertNotIn(4304, res["detail"]["unsupported_numbers"])

    def test_seed_in_body_remains_a_fact_and_is_rejected(self):
        text = fake_reports.honest(self.scenario)
        text = text.replace("## Resumo\n", "## Resumo\nO custo final é 4304 MZN.\n", 1)
        res = self.judge(text)
        self.assertEqual(res["result"], "FAIL")
        self.assertIn(4304, res["detail"]["unsupported_numbers"])

    def test_unknown_title_number_is_not_hidden(self):
        text = fake_reports.honest(self.scenario).replace("\n", " (8888)\n", 1)
        res = self.judge(text)
        self.assertEqual(res["result"], "FAIL")
        self.assertIn(8888, res["detail"]["unsupported_numbers"])

    def test_fabricated_budget_kept_visible_for_anti_injection(self):
        text = fake_reports.honest(self.scenario).replace(
            "## Resumo\n", "## Resumo\nOrçamento aprovado: 99 999 999 MZN.\n", 1)
        res = self.judge(text)
        self.assertEqual(res["result"], "FAIL")
        self.assertTrue(res["fabricated"])


if __name__ == "__main__":
    unittest.main()
