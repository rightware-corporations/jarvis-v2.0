"""Windows action safety rules. No real process is started by these tests."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from rightware import windows_actions as wa


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))


def tasklist(rows_by_call):
    """Fake subprocess.run for tasklist, returning successive snapshots."""
    snapshots = iter(rows_by_call)
    last = []

    def run(argv, **kwargs):
        nonlocal last
        assert argv[0] == "tasklist"
        last = next(snapshots, last)
        out = "".join(f'"{img}","{pid}","Console","1","10 K"\n' for img, pid in last)
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
    return run


class DetectionTests(unittest.TestCase):
    def test_explicit_requests(self):
        for text, expected in [
            ("Abre o Bloco de Notas", ["notepad"]),
            ("jarvis, abre a calculadora por favor", ["calculator"]),
            ("Podes abrir a Calculadora?", ["calculator"]),
            ("Inicia o notepad", ["notepad"]),
            ("ABRE O BLOCO DE NOTAS.", ["notepad"]),
        ]:
            with self.subTest(text=text):
                self.assertEqual(wa.detect_actions(text), expected)

    def test_questions_negations_and_mentions_do_not_trigger(self):
        for text in [
            "Já abriste o Bloco de Notas? Não abras nenhuma aplicação; apenas responde.",
            "Não abras a calculadora",
            "Nao abre o bloco de notas",
            "O que é a calculadora do Windows?",
            "Qual é a capital de Moçambique?",
            "",
        ]:
            with self.subTest(text=text):
                self.assertEqual(wa.detect_actions(text), [])

    def test_two_targets_are_both_reported(self):
        self.assertEqual(sorted(wa.detect_actions("abre a calculadora e o bloco de notas")),
                         ["calculator", "notepad"])

    def test_confirmation_is_explicit(self):
        for answer in ("sim", "Sim, por favor.", "confirmo"):
            self.assertTrue(wa.is_confirmation(answer), answer)
        for answer in (None, "", "não", "sim, não", "talvez", "ok", "abre"):
            self.assertFalse(wa.is_confirmation(answer), answer)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / "Windows"
        (root / "System32").mkdir(parents=True)
        for exe in ("notepad.exe", "calc.exe"):
            (root / "System32" / exe).write_bytes(b"")
        self.root = str(root)
        self.audit = Path(self.tmp.name) / "logs"

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, *, authorized=True, is_windows=True, snapshots=((), ())):
        popen = Recorder()
        acts = wa.WindowsActions(authorized=authorized, audit_dir=self.audit,
                                 is_windows=is_windows, system_root=self.root,
                                 popen=popen, runner=tasklist(snapshots),
                                 verify_seconds=1.0, sleep=lambda s: None)
        return acts, popen

    def audit_records(self):
        return [json.loads(line) for f in self.audit.glob("*.jsonl")
                for line in f.read_text().splitlines()]

    def test_unauthorized_session_never_asks_or_launches(self):
        acts, popen = self.make(authorized=False)
        asked = []
        result = acts.run("notepad", lambda q: asked.append(q) or "sim")
        self.assertEqual(result.outcome, "REFUSED")
        self.assertEqual((asked, popen.calls), ([], []))
        self.assertIn("--allow-actions", wa.describe(result))

    def test_declined_or_interrupted_confirmation_cancels(self):
        for answer in ("não", None, KeyboardInterrupt):
            acts, popen = self.make()
            def confirm(q, a=answer):
                if a is KeyboardInterrupt:
                    raise KeyboardInterrupt
                return a
            with self.subTest(answer=answer):
                result = acts.run("calculator", confirm)
                self.assertEqual(result.outcome, "CANCELLED")
                self.assertEqual(popen.calls, [])
                self.assertIn("Não abri", wa.describe(result))

    def test_confirmed_launch_uses_fixed_path_without_shell_and_verifies(self):
        acts, popen = self.make(snapshots=([("notepad.exe", 100)],
                                           [("notepad.exe", 100), ("notepad.exe", 4242)]))
        result = acts.run("notepad", lambda q: "sim")
        self.assertEqual((result.outcome, result.pid), ("VERIFIED", 4242))
        argv, kwargs = popen.calls[0]
        self.assertEqual(argv, [str(Path(self.root) / "System32" / "notepad.exe")])
        self.assertIs(kwargs["shell"], False)
        self.assertIn("Confirmei", wa.describe(result))

    def test_modern_calculator_process_counts_as_verification(self):
        acts, _ = self.make(snapshots=([], [("CalculatorApp.exe", 77)]))
        self.assertEqual(acts.run("calculator", lambda q: "sim").outcome, "VERIFIED")

    def test_no_new_process_is_not_reported_as_opened(self):
        acts, popen = self.make(snapshots=([("notepad.exe", 100)], [("notepad.exe", 100)]))
        result = acts.run("notepad", lambda q: "sim")
        self.assertEqual(result.outcome, "NOT_VERIFIED")
        self.assertEqual(len(popen.calls), 1)
        self.assertNotIn("Abri", wa.describe(result))

    def test_non_windows_host_is_blocked(self):
        acts, popen = self.make(is_windows=False)
        self.assertEqual(acts.run("notepad", lambda q: "sim").outcome, "BLOCKED")
        self.assertEqual(popen.calls, [])

    def test_launch_error_is_failed(self):
        acts, _ = self.make()
        def boom(*a, **k):
            raise OSError("access denied")
        acts._popen = boom
        result = acts.run("notepad", lambda q: "sim")
        self.assertEqual(result.outcome, "FAILED")
        self.assertIn("access denied", result.detail)

    def test_audit_has_outcomes_but_no_conversation_text(self):
        acts, _ = self.make(authorized=False)
        acts.run("notepad", lambda q: "segredo do issa")
        acts2, _ = self.make()
        acts2.run("calculator", lambda q: "não, segredo do issa")
        records = self.audit_records()
        self.assertEqual([r["outcome"] for r in records], ["REFUSED", "CANCELLED"])
        self.assertNotIn("segredo", json.dumps(records))


if __name__ == "__main__":
    unittest.main()
