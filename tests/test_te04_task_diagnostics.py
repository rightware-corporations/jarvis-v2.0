"""TE-04: sanitized task outcome diagnostics; no real model or network."""
import unittest

from rightware.task_entry import TaskEntryResult, _receipt_events

try:
    from rightware.agent.receipts import ExecutionReceipt
    from rightware.agent.session import AgentSession, Budgets
    from rightware.text_facade import TextFacade
    from rightware.task_entry import TaskEntry
    from labs.work07_r3c1.scenarios import FakeModel, call
    from labs.work07_r3c1.site import Archive, HOST, START
except ImportError:
    AgentSession = None


class DiagnosticsContract(unittest.TestCase):
    def test_sanitize_tool_and_status_without_arguments_or_contents(self):
        class Receipt:
            def __init__(self, seq, tool, status):
                self.sequence, self.tool, self.status = seq, tool, status
                self.arguments = {"secret": "NEVER_INCLUDE"}
                self.url = "https://example.invalid/private"
        rows = _receipt_events((
            Receipt(1, "web_open", "OK"),
            Receipt(2, "web_open", "HTTP_ERROR"),
            Receipt(3, "shell", "some custom sensitive message"),
            Receipt(4, "web_find", "REFUSED_AT_BOUNDARY"),
        ))
        self.assertEqual(rows, ((1,"web_open","OK"), (2,"web_open","HTTP_ERROR"),
                                (3,"OTHER","UNKNOWN"), (4,"web_find","REFUSED_AT_BOUNDARY")))
        self.assertNotIn("private", repr(rows))
        self.assertNotIn("NEVER_INCLUDE", repr(rows))

    def test_result_rejects_untrusted_halt_and_receipt_fields(self):
        base = dict(request_id="r",session_id="s",route="TASK",operational_state="HALTED",
                    objective_states=(),receipts_count=1,factual_verified=False,
                    completion_verified=False,model_commentary_unverified="",limitations=())
        with self.assertRaises(ValueError):
            TaskEntryResult(**base,halt_reason_code="the model said unlock")
        with self.assertRaises(ValueError):
            TaskEntryResult(**base,receipt_events=((1,"shell","OK"),))
        with self.assertRaises(ValueError):
            TaskEntryResult(**base,receipt_events=((1,"web_open","secret"),))


@unittest.skipIf(AgentSession is None, "pinned OpenJarvis venv required")
class RealExistingAgentFakeModel(unittest.TestCase):
    def test_policy_halt_reason_is_tool_budget_and_receipts_are_sanitized(self):
        facade = TextFacade(adapter=object())
        sid = facade.open_session()
        archive = Archive()
        url = "https://archive.fixture.example/docs/ax-101.html"
        # Eight turns attempt to call the same tool. A tool-local quota/loop guard
        # may deny later attempts; no shell or file tools are ever offered.
        steps = [lambda m, i=i: call("web_open", url=url) for i in range(11)]
        model = FakeModel(steps)
        def factory():
            return AgentSession(
                model, "fake", allow={"browse"}, confirm=lambda _: None,
                actions=None, sites=(HOST,), start_url=START,
                browser_fetcher=archive.fetcher(),
                task_preset="synthetic-archive-two-originals",
                receipts=True, completion_gate=True,
                max_turns=11, budgets=Budgets(max_calls=10, deadline_seconds=110))
        try:
            result = TaskEntry(facade,fixture_session_factory=factory).run_trusted_browser_fixture(
                sid, "Abre os dois originais sintéticos")
            self.assertIn(result.halt_reason_code, ("TOOL_BUDGET", "TURN_BUDGET"))
            self.assertFalse(result.completion_verified)
            self.assertTrue(result.receipt_events)
            self.assertEqual(result.receipts_count,len(result.receipt_events))
            self.assertTrue(all(t in ("web_open","OTHER") for _,t,_ in result.receipt_events))
        finally:
            facade.close()
