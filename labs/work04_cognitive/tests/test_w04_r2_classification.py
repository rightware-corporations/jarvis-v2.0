"""WORK-04 R2 classification and non-vacuous metric tests. No model calls."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from w04lab import assess_r2 as assess, failures  # noqa: E402


class Failures(unittest.TestCase):
    def classify(self, error=None, timed_out=False, security_ok=True, trace=None):
        return failures.classify_failure(error=error, timed_out=timed_out,
                                        security_ok=security_ok, trace=trace or [])

    def test_ollama_http_500_is_engine_error_not_harness(self):
        exc = RuntimeError('Ollama returned 500: {"error":"XML syntax error on line 6: unexpected EOF"}')
        self.assertEqual(self.classify(error=exc), "ENGINE")

    def test_timeout_and_connection_are_environment(self):
        self.assertEqual(self.classify(timed_out=True), "AMBIENTE")
        self.assertEqual(self.classify(error=ConnectionError("Connection refused")), "AMBIENTE")

    def test_unrelated_runtime_errors_remain_harness(self):
        self.assertEqual(self.classify(error=RuntimeError("Unexpected data type")), "HARNESS")

    def test_security_violation_and_tool_failure_are_distinct(self):
        self.assertEqual(self.classify(security_ok=False), "PERMISSÃO")
        trace = [{"tool": "read_document", "success": False,
                  "result_preview": "Erro da ferramenta (ValueError)."}]
        self.assertEqual(self.classify(trace=trace), "FERRAMENTA")
        self.assertEqual(self.classify(trace=[]), "MODELO")


class NonVacuousCrossRun(unittest.TestCase):
    def test_no_accepted_reports_cannot_validate_cross_run_quality(self):
        verdict = assess.assess([], inputs_distinct=True)
        self.assertFalse(verdict["accepted"])
        self.assertEqual(verdict["cross_run"]["pairs_checked"], 0)
        self.assertEqual(verdict["cross_run_factual"]["pairs_checked"], 0)
        self.assertFalse(verdict["gates"]["cross_run_all_pairs"]["ok"])
        self.assertFalse(verdict["gates"]["cross_run_factual"]["ok"])


if __name__ == "__main__":
    unittest.main()
