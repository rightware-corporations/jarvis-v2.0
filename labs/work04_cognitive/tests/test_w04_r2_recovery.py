"""R2 bounded one-continuation recovery, including real orchestrator with FAKE engine."""
from pathlib import Path
import sys
import unittest
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from w04lab import fake_engines, fake_reports, harness_r2, recovery_r2  # noqa: E402
from w02lab.policy import Budgets, Policy  # noqa: E402


class RecoveryContract(unittest.TestCase):
    def policy(self):
        return Policy(write_authorized=True, budgets=Budgets(deadline_seconds=1200))

    def test_no_read_is_not_eligible_for_retry(self):
        self.assertFalse(recovery_r2.should_retry_answer_only([], self.policy()))

    def test_read_then_answer_only_is_eligible(self):
        p = self.policy()
        self.assertTrue(recovery_r2.should_retry_answer_only(
            [{"tool": "read_document", "success": True}], p))

    def test_persisted_report_not_retried_even_when_failed_verification(self):
        p = self.policy()
        trace = [{"tool": "read_document", "success": True},
                 {"tool": "write_report", "success": True}]
        self.assertFalse(recovery_r2.should_retry_answer_only(trace, p))

    def test_cancelled_or_budget_exhausted_does_not_retry(self):
        p = self.policy()
        trace = [{"tool": "read_document", "success": True}]
        p.cancel()
        self.assertFalse(recovery_r2.should_retry_answer_only(trace, p))
        p2 = self.policy()
        p2.calls = 11
        self.assertFalse(recovery_r2.should_retry_answer_only(trace, p2))

    def test_no_new_authority_granted_in_continuation(self):
        prompt = recovery_r2.continuation_prompt("relatorio_4001.md")
        self.assertIn("nenhuma nova permissao", prompt)
        self.assertIn("write_report", prompt)
        self.assertIn("verify_report", prompt)
        self.assertNotIn("run_command", prompt)


class ScriptedOrchestratorRecovery(unittest.TestCase):
    def test_short_answer_then_persist_and_verify_in_second_run(self):
        def factory(scn):
            return fake_engines.Scripted([
                fake_engines._call("list_workspace"),
                *[fake_engines._call("read_document", {"name": name}, f"read_{i}")
                  for i, name in enumerate(scn.truth["sources"])],
                {"content": "Ainda falta escrever o relatório."},
                fake_engines._call("write_report", {
                    "name": scn.report_name,
                    "content": fake_reports.honest(scn)
                }),
                fake_engines._call("verify_report", {"name": scn.report_name}),
                {"content": "O relatório final foi guardado e verificado: PASS."},
            ])

        cfg = harness_r2.RunConfig(model="fake", timeout_seconds=120)
        with tempfile.TemporaryDirectory() as td:
            ev = harness_r2.run_task(
                factory, seed=4001, family="EVOL", cfg=cfg,
                keep_dir=Path(td), mode_label="FAKE R2"
            )
            self.assertTrue(ev["recovery_attempted"])
            self.assertEqual(ev["completion"]["completion_status"], "TASK_COMPLETED")
            self.assertEqual(ev["result"], "PASS")
            self.assertEqual(sum(t["tool"] == "write_report" and t["success"] for t in ev["trace"]), 1)
            self.assertEqual(sum(t["tool"] == "verify_report" and t["success"] for t in ev["trace"]), 1)
            self.assertFalse(ev["premature_completion_claim"])

    def test_no_write_after_bounded_retry_stays_incomplete(self):
        def factory(scn):
            return fake_engines.Scripted([
                fake_engines._call("list_workspace"),
                fake_engines._call("read_document", {"name": scn.truth["sources"][0]}),
                {"content": "Preciso de mais informação."},
                {"content": "Não consigo criar o relatório."},
            ])
        cfg = harness_r2.RunConfig(model="fake", timeout_seconds=120)
        ev = harness_r2.run_task(factory, seed=4001, family="EVOL", cfg=cfg, mode_label="FAKE R2")
        self.assertTrue(ev["recovery_attempted"])
        self.assertFalse(ev["completion"]["task_completed"])
        self.assertEqual(ev["completion"]["completion_status"], "FINAL_REPORT_NOT_PERSISTED")


if __name__ == "__main__":
    unittest.main()
