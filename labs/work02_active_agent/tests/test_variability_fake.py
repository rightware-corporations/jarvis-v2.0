"""Criterion (b) revised: varied inputs per run detect pre-programmed answers.
All results here are FAKE (scripted engines)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from _support import LAB, fake, fixtures, report_name
from w02lab import assess
from w02lab.fake import ScriptedEngine, call
from w02lab.harness import RunConfig, run_task

MAIN = [1000 + i for i in range(10)]
SEC = [2000 + i for i in range(3)]


def truth(seed):
    with tempfile.TemporaryDirectory() as d:
        return fixtures.generate(Path(d), seed).truth


def report_for(t: dict) -> str:
    return (f"# Relatório {t['project']}\n\nResponsável técnico: {t['responsible']}. Fornecedor: "
            f"{t['supplier']}. Entrega: {t['delivery'][8:10]}/{t['delivery'][5:7]}/{t['delivery'][:4]}.\n\n"
            f"## Contradições\nO orçamento diverge: {fixtures.fmt_mzn(t['budget_a'])} na acta e "
            f"{fixtures.fmt_mzn(t['budget_b'])} no relatório financeiro.\n\n"
            f"## Fontes\nacta_reuniao.md, relatorio_financeiro.md\n")


def canned_script(seed, fixed_report):
    name = report_name(seed)
    return [{"tool_calls": [call("read_document", {"name": "acta_reuniao.md"})]},
            {"tool_calls": [call("read_document", {"name": "relatorio_financeiro.md"})]},
            {"tool_calls": [call("write_report", {"name": name, "content": fixed_report})]},
            {"tool_calls": [call("verify_report", {"name": name})]},
            {"content": "Feito."}]


def batch(script_for):
    return [run_task(ScriptedEngine(script_for(s)), seed=s, cfg=RunConfig(), keep_dir=Path(tempfile.mkdtemp()))
            for s in MAIN]


class VariedInputs(unittest.TestCase):
    def test_every_run_uses_distinct_documents(self):
        """INPUT seeds 1000-1009 and 2000-2002 | EXPECTED pairwise distinct input hashes."""
        self.assertTrue(assess.distinct_inputs(MAIN)["distinct"])
        self.assertTrue(assess.distinct_inputs(SEC, with_trap=True)["distinct"])
        budgets = {(truth(s)["budget_a"], truth(s)["budget_b"]) for s in MAIN}
        self.assertEqual(len(budgets), len(MAIN))

    def test_fingerprint_matches_harness_evidence(self):
        ev = run_task(ScriptedEngine(fake.happy_script(report_name(1003))), seed=1003, cfg=RunConfig())
        self.assertEqual(ev["input_sha256"], assess.input_fingerprint(1003))
        self.assertEqual(ev["truth"]["budget_b"], truth(1003)["budget_b"])

    def test_threshold_constant_is_shared(self):
        spec = importlib.util.spec_from_file_location("run_real", LAB / "run_real.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.ACCEPT_RATIO, assess.ACCEPT_RATIO)


class PreProgrammedDetection(unittest.TestCase):
    def test_canned_report_fails_on_varied_inputs(self):
        """INPUT a FAKE 'model' that always writes the report correct for seed 1000
        | EXPECTED only seed 1000 passes; batch NOT accepted."""
        fixed = report_for(truth(1000))
        runs = batch(lambda s: canned_script(s, fixed))
        self.assertEqual([r["seed"] for r in runs if r["result"] == "PASS"], [1000])
        verdict = assess.assess(runs, [], len(MAIN), inputs_distinct=True)
        self.assertFalse(verdict["accepted"])
        self.assertEqual(verdict["k"], 1)

    def test_report_covering_two_runs_fails_both(self):
        """A 'universal' answer listing the facts of two runs invents facts for each."""
        t1, t2 = truth(1001), truth(1002)
        merged = report_for(t1) + "\n" + report_for(t2)
        from w02lab import verifier
        self.assertEqual(verifier.verify(merged, t1)["result"], "FAIL")
        self.assertEqual(verifier.verify(merged, t2)["result"], "FAIL")

    def test_honest_fake_passes_and_each_report_is_rejected_for_other_runs(self):
        runs = batch(lambda s: fake.happy_script(report_name(s)))
        verdict = assess.assess(runs, [], len(MAIN), inputs_distinct=True)
        self.assertEqual(verdict["k"], 10)
        self.assertEqual(verdict["cross_run"], {"checked": 10, "rejected": 10, "ok": True})
        self.assertTrue(verdict["accepted"])          # FAKE: validates the criterion only

    def test_not_accepted_without_distinct_inputs(self):
        runs = batch(lambda s: fake.happy_script(report_name(s)))
        self.assertFalse(assess.assess(runs, [], len(MAIN), inputs_distinct=False)["accepted"])


if __name__ == "__main__":
    unittest.main()
