"""WORK-07 Milestone A2 (PRODUCT): execution receipts, opt-in and observational.

REAL AgentSession + pinned OrchestratorAgent + ToolExecutor + AgentPolicy + PublicBrowser over the
local synthetic archive; FAKE model. Receipts prove OPERATIONAL facts only (never document
authenticity or factual correctness). No Qwen, no network.
"""
import dataclasses
import json
from pathlib import Path
import tempfile
import threading
import unittest

from rightware.agent import receipts as R

try:
    import httpx  # noqa: F401
    from openjarvis.core.types import ToolResult
    from openjarvis.tools import _stubs as upstream_tools
    from rightware.agent import session as S
    from rightware.agent.browser import PublicBrowser
    from labs.work07_r3c1.scenarios import FakeModel, INSTRUCTION, call, scenario_steps
    from labs.work07_r3c1.site import HOST, START, Archive
except ImportError:              # system Python without the pinned venv
    S = None


def make(model, *, receipts=True, **kw):
    archive = Archive()
    kw.setdefault("budgets", S.Budgets(max_calls=14, deadline_seconds=900))
    s = S.AgentSession(model, "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,), start_url=START,
                       browser_fetcher=archive.fetcher(), max_turns=kw.pop("max_turns", 14), receipts=receipts, **kw)
    return s, archive


def run(steps, **kw):
    model = FakeModel(steps)
    s, archive = make(model, **kw)
    reply = s.run(INSTRUCTION)
    return s, reply, model, archive


class LedgerUnit(unittest.TestCase):
    """Binding rules of the ledger itself, without the agent."""

    def test_claim_requires_the_current_dispatch_and_identical_arguments(self):
        led = R.ReceiptLedger("run1")
        rec = led.decide("c1", "web_find", json.dumps({"text": "a"}), True, None)
        orphan = led.claim("web_find", {"text": "a"})                    # no dispatch published
        self.assertEqual(orphan.binding, "ORPHAN")
        led.dispatch(rec)
        cross = led.claim("web_find", {"text": "OTHER"})                 # different arguments
        self.assertEqual(cross.binding, "ORPHAN")
        other_tool = led.claim("web_open", {"text": "a"})                # different tool
        self.assertEqual(other_tool.binding, "ORPHAN")
        good = led.claim("web_find", {"text": "a"})
        self.assertIs(good, rec)
        again = led.claim("web_find", {"text": "a"})                     # one claim per dispatch
        self.assertEqual(again.binding, "ORPHAN")
        led.started(good)
        led.finish(good, "OK", {}, True)
        led.end_dispatch(rec)
        got = {r.sequence: r for r in led.receipts()}
        self.assertEqual((got[1].status, got[1].binding, got[1].call_id), ("OK", "BOUND", "c1"))
        orphans = [r for r in led.receipts() if r.binding == "ORPHAN"]
        self.assertEqual(len(orphans), 4)
        self.assertTrue(all(o.sequence == 0 and o.call_id is None and not o.authorized for o in orphans))

    def test_unclaimed_dispatch_is_not_executed_and_abandoned_run_is_timed_out_then_late(self):
        led = R.ReceiptLedger("run2")
        a = led.decide("a", "web_find", '{"text":"x"}', True, None)
        led.dispatch(a)
        led.end_dispatch(a)                                              # executor returned early
        b = led.decide("b", "web_find", '{"text":"y"}', True, None)
        led.dispatch(b)
        claimed = led.claim("web_find", {"text": "y"})
        led.started(claimed)
        led.end_dispatch(b)                                              # executor gave up while running
        mid = {r.call_id: r.status for r in led.receipts()}
        self.assertEqual(mid, {"a": "NOT_EXECUTED", "b": "TIMED_OUT"})
        led.finish(claimed, "OK", {}, True)
        late = [r for r in led.receipts() if r.call_id == "b"][0]
        self.assertEqual((late.status, late.late, late.executed), ("OK", True, True))

    def test_decisions_flag_duplicate_missing_and_unparseable(self):
        led = R.ReceiptLedger("run3")
        led.decide("x", "web_find", '{"text":"a"}', True, None)
        led.decide("x", "web_find", '{"text":"b"}', True, None)
        led.decide(None, "web_find", '{"text":"c"}', False, "recusada")
        led.decide("y", "web_find", "{not json", False, None)
        led.close()
        got = led.receipts()
        self.assertEqual([r.call_id_status for r in got], ["SUPPLIED", "DUPLICATE", "MISSING", "SUPPLIED"])
        self.assertIsNone(got[3].args_sha256)
        self.assertEqual([r.status for r in got], ["NOT_EXECUTED", "NOT_EXECUTED", "DENIED", "DENIED"])
        self.assertEqual(got[2].policy_reason, "recusada")

    def test_receipts_are_immutable(self):
        led = R.ReceiptLedger()
        led.decide("x", "web_find", '{"text":"a"}', False, "r")
        rec = led.receipts()[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            rec.status = "OK"


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class SessionReceipts(unittest.TestCase):
    def test_default_off_has_no_receipts_and_no_wrapped_executor(self):
        s, reply, model, _ = run(scenario_steps("A_incomplete"), receipts=False)
        self.assertEqual(s.receipts, ())
        self.assertIsNone(s.ledger)
        p = S.AgentPolicy(S.TOOLS, allow={"browse"})
        agent = S._RightwareOrchestrator(FakeModel([]), "fake", policy=p, tools=[], max_turns=1,
                                         parallel_tools=False, before_tool_call=p.before_tool_call)
        self.assertEqual(type(agent._executor.execute).__name__, "method")   # upstream bound method, untouched

    def test_parallel_tools_is_refused_with_receipts(self):
        p = S.AgentPolicy(S.TOOLS, allow={"browse"})
        with self.assertRaises(ValueError):
            S._RightwareOrchestrator(FakeModel([]), "fake", policy=p, tools=[], max_turns=1, parallel_tools=True,
                                     ledger=R.ReceiptLedger(), before_tool_call=p.before_tool_call)
        import inspect
        self.assertIn("parallel_tools=False", inspect.getsource(S.AgentSession.run))

    def test_receipts_change_nothing_observable(self):
        for name in ("A_incomplete", "B_complete", "C_hidden_link", "D_refused", "E_premature"):
            with self.subTest(name=name):
                off = run(scenario_steps(name), receipts=False)
                on = run(scenario_steps(name), receipts=True)
                self.assertEqual(S.reply_json(off[1]), S.reply_json(on[1]))
                self.assertEqual(off[1].text, on[1].text)
                self.assertEqual(len(off[2].received), len(on[2].received))
                self.assertEqual(off[3].requests, on[3].requests)
                self.assertEqual((off[0]._policy.per_tool, off[0]._policy.calls),
                                 (on[0]._policy.per_tool, on[0]._policy.calls))
                self.assertTrue(on[0].receipts)

    def test_one_bound_receipt_per_decision_matching_outcomes(self):
        for name in ("A_incomplete", "B_complete", "D_refused"):
            with self.subTest(name=name):
                s, reply, _, _ = run(scenario_steps(name))
                rec = s.receipts
                self.assertEqual([r.sequence for r in rec], list(range(1, len(rec) + 1)))
                self.assertFalse(any(r.binding == "ORPHAN" for r in rec))
                decisions = [e for e in s._policy.log if "outcome" not in e]
                self.assertEqual(len(rec), len(decisions))
                self.assertEqual([r.authorized for r in rec], [e["allowed"] for e in decisions])
                executed = [r for r in rec if r.authorized]
                self.assertEqual([r.status for r in executed], [o.status for o in reply.outcomes])
                self.assertEqual(len({r.run_id for r in rec}), 1)

    def test_denials_quota_and_anti_loop_are_explicit_never_executed(self):
        s, _, _, _ = run(scenario_steps("D_refused"))
        denied = [r for r in s.receipts if not r.authorized]
        self.assertEqual([(r.status, r.executed, r.audit) for r in denied], [("DENIED", False, "NOT_APPLICABLE")] * 2)
        self.assertIn("acção idêntica", denied[0].policy_reason)
        self.assertEqual(denied[1].policy_reason, "limite de chamadas desta ferramenta atingido")
        refused = [r for r in s.receipts if r.status == "REFUSED"]
        self.assertEqual(len(refused), 1)                                   # browser refused the off-site mirror
        self.assertTrue(refused[0].executed and refused[0].raw_sha256 is None)

    def test_raw_hash_scope_differs_from_model_view_hash(self):
        s, _, _, _ = run(scenario_steps("B_complete"), trace=True)
        loads = [r for r in s.receipts if r.raw_sha256]
        events = [e for e in s.browser.events if e.get("outcome") == "OK"]
        self.assertEqual([r.raw_sha256 for r in loads], [e["sha256"] for e in events])
        self.assertTrue(all(len(r.raw_sha256) == 64 and r.hash_scope == "raw_response_bytes" for r in loads))
        views = {p.get("view", {}).get("view_sha256") for t in s.trace.turns for p in t["proposals"]}
        self.assertFalse({r.raw_sha256[:16] for r in loads} & views)

    def test_trace_off_still_produces_receipts(self):
        s, _, _, _ = run(scenario_steps("A_incomplete"), trace=False)
        self.assertIsNone(s.trace)
        self.assertEqual(len(s.receipts), 7)

    def test_repeated_runs_get_fresh_run_ids_and_sequences(self):
        model = FakeModel(scenario_steps("E_premature") + scenario_steps("E_premature"))
        s, _ = make(model)
        s.run(INSTRUCTION)
        first = s.receipts
        s.run(INSTRUCTION)
        second = s.receipts
        self.assertNotEqual(first[0].run_id, second[0].run_id)
        self.assertEqual(second[0].sequence, 1)
        self.assertEqual(len({r.run_id for r in second}), 1)

    def test_approved_but_never_executed_is_not_executed(self):
        from openjarvis.agents.loop_guard import LoopGuard, LoopGuardConfig
        original = S._RightwareOrchestrator.__init__

        def with_guard(self, *a, **k):
            original(self, *a, **k)
            self._loop_guard = LoopGuard(LoopGuardConfig(poll_tool_budget=1, warn_before_block=False))
        S._RightwareOrchestrator.__init__ = with_guard
        try:
            s, reply, _, _ = run(scenario_steps("A_incomplete"))
        finally:
            S._RightwareOrchestrator.__init__ = original
        ne = [r for r in s.receipts if r.status == "NOT_EXECUTED"]
        self.assertEqual(len(ne), len([o for o in reply.outcomes if o.status == "NOT_EXECUTED"]))
        self.assertEqual(len(ne), 3)                      # 2nd web_type, web_submit, web_follow: guard budget 1
        self.assertTrue(all(r.authorized and not r.executed and r.binding == "BOUND" for r in ne))
        self.assertIn("APPROVED_NOT_EXECUTED", reply.flags)

    def test_executor_early_return_without_calling_the_tool_is_not_executed(self):
        original = upstream_tools.ToolExecutor.execute

        def early(self, tool_call):
            if tool_call.name == "web_submit":
                return ToolResult(tool_name=tool_call.name, content="Rate limit exceeded", success=False)
            return original(self, tool_call)
        upstream_tools.ToolExecutor.execute = early
        try:
            s, reply, _, _ = run(scenario_steps("E_premature"))
        finally:
            upstream_tools.ToolExecutor.execute = original
        sub = [r for r in s.receipts if r.tool == "web_submit"][0]
        self.assertEqual((sub.authorized, sub.executed, sub.status), (True, False, "NOT_EXECUTED"))

    def test_boundary_refusal_after_approval(self):
        t = [0.0]
        original = upstream_tools.ToolExecutor.execute

        def expire_then_run(self, tool_call):
            if tool_call.name == "web_submit":
                t[0] = 10_000.0                                         # deadline passes between hook and tool
            return original(self, tool_call)
        upstream_tools.ToolExecutor.execute = expire_then_run
        try:
            s, reply, _, _ = run(scenario_steps("E_premature"), clock=lambda: t[0])
        finally:
            upstream_tools.ToolExecutor.execute = original
        sub = [r for r in s.receipts if r.tool == "web_submit"][0]
        self.assertEqual((sub.authorized, sub.executed, sub.status), (True, False, "REFUSED_AT_BOUNDARY"))
        self.assertIsNone(sub.final_url)

    def test_runner_error_is_failed_and_executed(self):
        original = PublicBrowser.submit

        def boom(self, field):
            raise RuntimeError("boom")
        PublicBrowser.submit = boom
        try:
            s, reply, _, _ = run(scenario_steps("E_premature"))
        finally:
            PublicBrowser.submit = original
        sub = [r for r in s.receipts if r.tool == "web_submit"][0]
        self.assertEqual((sub.executed, sub.status, sub.audit), (True, "FAILED", "OK"))

    def test_audit_failure_after_execution_is_recorded(self):
        broken = Path(tempfile.mkdtemp()) / "blocker"
        broken.write_text("x")
        original = upstream_tools.ToolExecutor.execute
        state = {}

        def break_audit(self, tool_call):
            if tool_call.name == "web_submit":
                state["s"]._policy.audit_path = broken / "audit.jsonl"     # decision persisted, outcome cannot be
            return original(self, tool_call)
        upstream_tools.ToolExecutor.execute = break_audit
        model = FakeModel(scenario_steps("E_premature"))
        s, _ = make(model, audit_path=Path(tempfile.mkdtemp()) / "audit.jsonl")
        state["s"] = s
        try:
            reply = s.run(INSTRUCTION)
        finally:
            upstream_tools.ToolExecutor.execute = original
        sub = [r for r in s.receipts if r.tool == "web_submit"][0]
        self.assertEqual((sub.executed, sub.audit), (True, "FAILED"))
        self.assertIn("AUDIT_FAILED", reply.flags)

    def test_cancel_and_deadline_leave_no_open_or_unknown_receipt(self):
        holder = {}
        steps = scenario_steps("A_incomplete")
        model = FakeModel(steps)
        inner = model.generate

        def gen(messages, **kw):
            if len(model.received) == 4:
                holder["s"].cancel()
            return inner(messages, **kw)
        model.generate = gen
        s, _ = make(model)
        holder["s"] = s
        reply = s.run(INSTRUCTION)
        self.assertEqual(reply.halted, "tarefa cancelada")
        self.assertFalse(any(r.status == "UNKNOWN" for r in s.receipts))
        t = [0.0]
        model2 = FakeModel(steps)
        inner2 = model2.generate
        model2.generate = lambda m, **k: (t.__setitem__(0, 1e6) if len(model2.received) == 3 else None) or inner2(m, **k)
        s2, _ = make(model2, clock=lambda: t[0])
        reply2 = s2.run(INSTRUCTION)
        self.assertEqual(reply2.halted, "tempo esgotado")
        self.assertFalse(any(r.status == "UNKNOWN" for r in s2.receipts))

    def test_timeout_then_late_completion_is_marked_and_bound(self):
        release, started = threading.Event(), threading.Event()
        original_find = PublicBrowser.find

        def slow_find(self, text):
            started.set()
            release.wait(5)
            return original_find(self, text)
        original_exec = upstream_tools.ToolExecutor.execute
        workers = []

        def timeout_exec(self, tool_call):
            if tool_call.name != "web_find":
                return original_exec(self, tool_call)
            tool = self._tools[tool_call.name]
            th = threading.Thread(target=tool.execute, kwargs=json.loads(tool_call.arguments))
            th.start()
            workers.append(th)
            started.wait(5)                                            # the tool has claimed and started
            return ToolResult(tool_name=tool_call.name, content="timed out", success=False)
        PublicBrowser.find, upstream_tools.ToolExecutor.execute = slow_find, timeout_exec
        try:
            steps = [lambda m: call("web_open", url=START), lambda m: call("web_find", text="x"),
                     lambda m: {"content": "fim"}]
            s, reply, _, _ = run(steps)
            find = [r for r in s.receipts if r.tool == "web_find"][0]
            self.assertEqual((find.status, find.executed, find.late), ("TIMED_OUT", True, False))
            release.set()
            for th in workers:
                th.join(5)
            find = [r for r in s.receipts if r.tool == "web_find"][0]
            self.assertEqual((find.status, find.late, find.binding), ("OK", True, "BOUND"))
        finally:
            PublicBrowser.find, upstream_tools.ToolExecutor.execute = original_find, original_exec
            release.set()

    def test_malformed_arguments_never_inherit_a_stale_policy_reason(self):
        bad = {"content": "", "tool_calls": [{"id": "bad1", "name": "web_find", "arguments": "{not json"}]}
        steps = [lambda m: call("web_open", url=START), lambda m: call("web_open", url=START),
                 lambda m: call("web_open", url=START),                         # 3rd identical: denied (anti-loop)
                 lambda m: bad, lambda m: {"content": "fim"}]
        s, _, _, _ = run(steps)
        last = s.receipts[-1]
        self.assertEqual((last.call_id, last.status, last.args_sha256), ("bad1", "DENIED", None))
        self.assertEqual(last.policy_reason, "os argumentos não são JSON válido (recusada antes da política)")
        self.assertIn("acção idêntica", s.receipts[-2].policy_reason)

    def test_receipts_hold_no_page_text_typed_text_or_secrets(self):
        steps = [lambda m: call("web_open", url=START), lambda m: call("web_type", field="F1", text="SEGREDO-QUERY"),
                 lambda m: call("web_open", url=f"https://{HOST}/missing?api_key=TOPSECRET123"),
                 lambda m: {"content": "fim"}]
        s, _, _, _ = run(steps)
        blob = json.dumps([dataclasses.asdict(r) for r in s.receipts], ensure_ascii=False)
        for forbidden in ("SEGREDO-QUERY", "TOPSECRET123", "Search the Archive", "PAGINA-NAO-CONFIAVEL"):
            self.assertNotIn(forbidden, blob)
        self.assertIn("api_key=REDACTED", blob)


if __name__ == "__main__":
    unittest.main()
