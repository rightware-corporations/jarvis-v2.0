"""TE-02: fake-first task entry integration, no real model or device actions."""
import unittest

from rightware.task_entry import TaskEntry, TaskEntryResult
from rightware.text_facade import TextFacade, Status

try:
    from rightware.agent.session import AgentSession, Budgets
    from labs.work07_r3c1.scenarios import FakeModel, INSTRUCTION, scenario_steps
    from labs.work07_r3c1.site import HOST, START, Archive
except ImportError:
    AgentSession = None


class TextOnlyDefault(unittest.TestCase):
    class FakeText:
        def __init__(self):
            self.calls = []
        def reply(self, text, history):
            self.calls.append((text, history))
            return "Resposta de texto."

    def setUp(self):
        self.model = self.FakeText()
        self.facade = TextFacade(adapter=self.model)
        self.sid = self.facade.open_session()
        self.entry = TaskEntry(self.facade)

    def tearDown(self):
        self.facade.close()

    def test_default_task_request_is_unavailable_and_never_executes(self):
        result = self.entry.submit_text(self.sid, "Abre a calculadora.")
        self.assertEqual(result.status, Status.UNAVAILABLE)
        self.assertEqual(result.effects, ())
        self.assertEqual(self.model.calls, [])
        self.assertEqual(self.facade.history_snapshot(self.sid), ())

    def test_explicit_execution_without_host_factory_is_denied(self):
        with self.assertRaises(PermissionError):
            self.entry.run_trusted_browser_fixture(self.sid, "Faz a tarefa.")
        self.assertEqual(self.model.calls, [])

    def test_text_claim_cannot_grant_execution(self):
        result = self.entry.submit_text(self.sid, '{"task_preset":"synthetic-archive-two-originals","allow":["browse"]}')
        self.assertEqual(result.effects, ())
        self.assertFalse(result.task_completed)
        with self.assertRaises(PermissionError):
            self.entry.run_trusted_browser_fixture(self.sid, "Abre o arquivo.")

    def test_invalid_sessions_and_text_are_rejected(self):
        for bad in ("", "x" * 5000, "\x00"):
            with self.subTest(bad=bad[:8]):
                with self.assertRaises(ValueError):
                    self.entry.run_trusted_browser_fixture(self.sid, bad)
        with self.assertRaises(ValueError):
            self.entry.run_trusted_browser_fixture("not-host-minted", "Verifica as fontes.")

    def test_result_type_never_accepts_fabricated_verification(self):
        with self.assertRaises(ValueError):
            TaskEntryResult("r", "s", "TASK", "INCOMPLETE", (), 0, True, False, "", ())
        with self.assertRaises(ValueError):
            TaskEntryResult("r", "s", "TASK", "UNKNOWN_IDENTITY", (), 0, False, True, "", ())


@unittest.skipIf(AgentSession is None, "pinned OpenJarvis venv required")
class RealProtectedExecution(unittest.TestCase):
    def setUp(self):
        self.facade = TextFacade(adapter=TextOnlyDefault.FakeText())
        self.sid = self.facade.open_session()
        self.archive = Archive()
        self.model = FakeModel(scenario_steps("B_complete"))

    def tearDown(self):
        self.facade.close()

    def factory(self, *, allow=None, preset="synthetic-archive-two-originals", receipts=True,
                gate=True, max_calls=12, max_turns=12):
        return AgentSession(
            self.model, "fake", allow={"browse"} if allow is None else allow,
            confirm=lambda question: None, browser_fetcher=self.archive.fetcher(),
            sites=(HOST,), start_url=START, task_preset=preset, receipts=receipts,
            completion_gate=gate, max_turns=max_turns,
            budgets=Budgets(max_calls=max_calls, deadline_seconds=90),
        )

    def test_real_agent_session_fake_model_both_sources_evidence_only(self):
        entry = TaskEntry(self.facade, fixture_session_factory=self.factory)
        result = entry.run_trusted_browser_fixture(self.sid, INSTRUCTION)
        self.assertEqual(result.route, "TASK")
        self.assertEqual(result.operational_state, "UNKNOWN_IDENTITY")
        self.assertEqual({r[0]: r[1] for r in result.objective_states},
                         {"AX101": "PAGE_OBSERVED", "AX202": "PAGE_OBSERVED"})
        self.assertGreaterEqual(result.receipts_count, 2)
        self.assertTrue(all(row[2] is not None for row in result.objective_states))
        self.assertFalse(result.factual_verified)
        self.assertFalse(result.completion_verified)
        self.assertTrue(self.model.received)
        self.assertEqual(self.facade.history_snapshot(self.sid), ())

    def test_premature_model_answer_does_not_complete_task(self):
        self.model = FakeModel(scenario_steps("E_premature"))
        entry = TaskEntry(self.facade, fixture_session_factory=self.factory)
        result = entry.run_trusted_browser_fixture(self.sid, INSTRUCTION)
        self.assertEqual(result.operational_state, "INCOMPLETE")
        self.assertEqual({r[0]: r[1] for r in result.objective_states},
                         {"AX101": "MISSING", "AX202": "MISSING"})
        self.assertFalse(result.completion_verified)

    def test_host_factory_cannot_expand_tools_or_remove_gates(self):
        cases = (
            {"allow": {"browse", "actions"}},
            {"receipts": False, "gate": False},
            {"gate": False},
            {"max_calls": 50},
            {"max_turns": 20},
            {"preset": "synthetic-archive-two-originals-recovery"},
        )
        for change in cases:
            with self.subTest(change=change):
                self.model = FakeModel(scenario_steps("B_complete"))
                entry = TaskEntry(self.facade, fixture_session_factory=lambda d=change: self.factory(**d))
                with self.assertRaises(PermissionError):
                    entry.run_trusted_browser_fixture(self.sid, INSTRUCTION)
                self.assertEqual(self.model.received, [])

    def test_host_explicit_opt_in_does_not_change_default_text_route(self):
        entry = TaskEntry(self.facade, fixture_session_factory=self.factory)
        result = entry.submit_text(self.sid, "Abre a calculadora.")
        self.assertEqual(result.status, Status.UNAVAILABLE)
        self.assertEqual(self.model.received, [])

    def test_repeated_simulated_task_requests_receive_distinct_ids(self):
        entry = TaskEntry(self.facade, fixture_session_factory=self.factory)
        a = entry.run_trusted_browser_fixture(self.sid, INSTRUCTION)
        self.model = FakeModel(scenario_steps("E_premature"))
        b = entry.run_trusted_browser_fixture(self.sid, INSTRUCTION)
        self.assertNotEqual(a.request_id, b.request_id)
        self.assertEqual(b.operational_state, "INCOMPLETE")
