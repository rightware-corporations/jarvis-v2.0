"""WORK-04 R2 completion regressions — deterministic, no Ollama or GPU."""
from pathlib import Path
import sys
import unittest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
from w04lab.completion import evaluate_completion  # noqa: E402


def call(tool, name=None, *, ok=True, message=""):
    args = {"name": name} if name is not None else {}
    return {"tool": tool, "args": args, "success": ok, "result_preview": message}


def check(trace, name="relatorio_4001.md", report="# Relatorio\nDados reais",
          v2="PASS", oracle="PASS", expected="relatorio_4001.md"):
    return evaluate_completion(
        trace, final_name=name, report=report,
        v2_result=v2, oracle_result=oracle, expected_name=expected,
    )


class FinalReportCompletion(unittest.TestCase):
    def test_answer_only_is_not_completion(self):
        r = check([call("list_workspace")], name=None, report="")
        self.assertFalse(r["task_completed"])
        self.assertEqual(r["completion_status"], "FINAL_REPORT_NOT_PERSISTED")

    def test_written_without_verify_is_not_completion(self):
        r = check([call("write_report", "relatorio_4001.md")])
        self.assertEqual(r["completion_status"], "FINAL_REPORT_NOT_VERIFIED")

    def test_verify_before_write_not_accepted(self):
        r = check([call("verify_report", "relatorio_4001.md", message="Verificação: PASS"),
                   call("write_report", "relatorio_4001.md")])
        self.assertEqual(r["completion_status"], "FINAL_REPORT_NOT_VERIFIED")

    def test_verify_for_different_file_does_not_certify_final(self):
        r = check([call("write_report", "relatorio_4001.md"),
                   call("write_report", "relatorio_4001_v2.md"),
                   call("verify_report", "relatorio_4001.md", message="Verificação: PASS")],
                  name="relatorio_4001_v2.md")
        self.assertEqual(r["completion_status"], "FINAL_REPORT_NOT_VERIFIED")

    def test_explicit_verify_fail_is_not_completion(self):
        r = check([call("write_report", "relatorio_4001.md"),
                   call("verify_report", "relatorio_4001.md", message="Verificação: FAIL")])
        self.assertEqual(r["completion_status"], "FINAL_REPORT_VERIFICATION_FAILED")

    def test_tool_error_not_success_even_if_pass_word_present(self):
        r = check([call("write_report", "relatorio_4001.md"),
                   call("verify_report", "relatorio_4001.md", ok=False,
                        message="Verificação: PASS")])
        self.assertEqual(r["completion_status"], "FINAL_REPORT_VERIFICATION_FAILED")

    def test_pass_for_old_version_does_not_certify_rewritten_version(self):
        r = check([call("write_report", "relatorio_4001.md"),
                   call("verify_report", "relatorio_4001.md", message="Verificação: PASS"),
                   call("write_report", "relatorio_4001_v2.md")],
                  name="relatorio_4001_v2.md")
        self.assertFalse(r["task_completed"])

    def test_later_failed_verification_supersedes_old_pass(self):
        r = check([call("write_report", "relatorio_4001.md"),
                   call("verify_report", "relatorio_4001.md", message="Verificação: PASS"),
                   call("verify_report", "relatorio_4001.md", message="Verificação: FAIL")])
        self.assertEqual(r["completion_status"], "FINAL_REPORT_VERIFICATION_FAILED")

    def test_correct_final_tool_and_independent_evaluators_pass(self):
        r = check([call("write_report", "relatorio_4001.md"),
                   call("verify_report", "relatorio_4001.md", message="Verificação: PASS")])
        self.assertTrue(r["task_completed"])
        self.assertEqual(r["completion_status"], "TASK_COMPLETED")
        self.assertEqual(r["verification_count"], 1)

    def test_corrected_v2_can_pass_when_verified(self):
        r = check([call("write_report", "relatorio_4001.md"),
                   call("verify_report", "relatorio_4001.md", message="Verificação: FAIL"),
                   call("write_report", "relatorio_4001_v2.md"),
                   call("verify_report", "relatorio_4001_v2.md", message="Verificação: PASS")],
                  name="relatorio_4001_v2.md")
        self.assertTrue(r["task_completed"])

    def test_independent_evaluator_failure_blocks_completion(self):
        trace = [call("write_report", "relatorio_4001.md"),
                 call("verify_report", "relatorio_4001.md", message="Verificação: PASS")]
        for v2, oracle in (("FAIL", "PASS"), ("PASS", "FAIL")):
            with self.subTest(v2=v2, oracle=oracle):
                r = check(trace, v2=v2, oracle=oracle)
                self.assertEqual(r["completion_status"], "INDEPENDENT_EVALUATORS_FAILED")

    def test_unauthorized_report_name_rejected(self):
        trace = [call("write_report", "relatorio_4001_v1.md"),
                 call("verify_report", "relatorio_4001_v1.md", message="Verificação: PASS")]
        r = check(trace, name="relatorio_4001_v1.md")
        self.assertEqual(r["completion_status"], "REPORT_NAME_NOT_AUTHORIZED")

    def test_no_report_text_cannot_pass(self):
        trace = [call("write_report", "relatorio_4001.md"),
                 call("verify_report", "relatorio_4001.md", message="Verificação: PASS")]
        self.assertEqual(check(trace, report="")["completion_status"], "FINAL_REPORT_NOT_PERSISTED")


if __name__ == "__main__":
    unittest.main()
