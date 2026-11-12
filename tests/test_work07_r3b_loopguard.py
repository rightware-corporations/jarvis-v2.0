"""WORK-07 R3-B: approved tool calls without an outcome (real runs 43161108959 and 43189355873).

Cause (confirmed): the pinned OpenJarvis LoopGuard (Python backend; openjarvis_rust is not
installed) runs AFTER the RIGHTWARE before_tool_call hook approved a call and BEFORE the tool,
and detects cycles by tool NAME only. Fix: _RightwareOrchestrator removes that misplaced check;
AgentPolicy's argument-aware loop guard runs before approval; leftovers are closed explicitly.

Deterministic: FAKE model through the REAL OrchestratorAgent and the REAL PublicBrowser over the
local fixture site (no network, no model). Not evidence about Qwen.
"""
import json
from pathlib import Path
import re
import tempfile
import unittest

from rightware.agent import policy as P

try:
    import httpx  # noqa: F401
    from work07_site import HOST, START, Site
    from rightware.agent import session as S
    from openjarvis.agents.loop_guard import LoopGuard, LoopGuardConfig
except ImportError:              # system Python without the pinned venv: tests below are skipped
    S = None
    HOST, START = "docs.fixture.example", "https://docs.fixture.example/search/"

DOC1, DOC2 = f"https://{HOST}/doc/wsp1001.html", f"https://{HOST}/doc/wsp1002.html"


def call(name, **args):
    return {"content": "", "tool_calls": [{"id": f"c-{name}-{json.dumps(args, sort_keys=True)}", "name": name,
                                           "arguments": json.dumps(args)}]}


def link_to(messages, suffix):
    for line in reversed("\n".join(getattr(m, "content", "") or "" for m in messages).splitlines()):
        m = re.match(r"(L\d+): .* -> (\S+)$", line)
        if m and m.group(2).endswith(suffix):
            return m.group(1)
    return "L0"


class Replay:
    """FAKE model replaying a recorded tool-call SHAPE; keeps every tool message it receives."""
    engine_id = "fake"

    def __init__(self, steps, hook=None):
        self.steps, self.i, self.hook, self.tool_messages = list(steps), 0, hook, []

    def generate(self, messages, **kw):
        last = messages[-1]
        if str(getattr(last, "role", "")).lower().endswith("tool"):
            self.tool_messages.append(getattr(last, "content", ""))
        if self.hook:
            self.hook(self.i)
        if self.i >= len(self.steps):
            return {"content": "fim", "usage": {}}
        step = self.steps[self.i](messages)
        self.i += 1
        return {"usage": {}, **step}


# The exact shape of the real runs' proposals (same tools, order and argument kinds; fixture URLs).
RUN3 = [lambda m: call("web_open", url=START), lambda m: call("web_type", field="F1", text="WSP 1001"),
        lambda m: call("web_submit", field="F1"), lambda m: call("web_open", url=DOC1),
        lambda m: call("web_type", field="F1", text="WSP 1002"), lambda m: call("web_submit", field="F1"),
        lambda m: call("web_open", url=DOC2), lambda m: call("web_follow", link=link_to(m, "wsp1002.html")),
        lambda m: {"content": "Resposta final."}]
RUN1 = RUN3[:7] + [lambda m: call("web_open", url=DOC2)] + RUN3[7:]


def audit_pairs(path):
    """(approvals, outcomes) per tool from a JSONL audit."""
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]
    approvals = [r for r in rows if r["allowed"] and "outcome" not in r]
    outcomes = [r for r in rows if "outcome" in r]
    return rows, approvals, outcomes


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class UpstreamBehaviourIsDocumented(unittest.TestCase):
    """Pins the upstream facts the fix relies on. If the pin changes, these tell us."""

    def test_python_backend_is_what_the_pinned_venv_runs(self):
        self.assertIsNone(LoopGuard(LoopGuardConfig())._rust_impl)

    def test_name_only_ping_pong_blocks_the_seventh_call_of_a_second_search(self):
        g = LoopGuard(LoopGuardConfig())
        names = ["web_open", "web_type", "web_submit"] * 2 + ["web_open"]
        verdicts = [g.check_call(n, json.dumps({"different": i})) for i, n in enumerate(names)]
        self.assertTrue(verdicts[5].warned and not verdicts[5].blocked)
        self.assertTrue(verdicts[6].blocked)                       # different arguments, still blocked
        self.assertIn("ping-pong", verdicts[6].reason)

    def test_poll_budget_would_block_the_sixth_call_to_one_tool(self):
        g = LoopGuard(LoopGuardConfig(ping_pong_window=1000))
        verdicts = [g.check_call("web_follow", json.dumps({"link": f"L{i}"})) for i in range(6)]
        self.assertTrue(verdicts[5].warned or verdicts[5].blocked)  # product allows 6 web_follow


class _SessionCase(unittest.TestCase):
    def setUp(self):
        self.site = Site()
        self.audit = Path(tempfile.mkdtemp()) / "agent.jsonl"

    def session(self, model, **kw):
        return S.AgentSession(model, "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,),
                              start_url=START, browser_fetcher=self.site.fetcher(), audit_path=self.audit,
                              budgets=kw.pop("budgets", S.Budgets(max_calls=14, deadline_seconds=900)),
                              max_turns=14, **kw)


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class RealRunShapes(_SessionCase):
    def test_orchestrator_has_no_misplaced_upstream_loop_guard(self):
        p = P.AgentPolicy(S.TOOLS, allow={"browse"})
        agent = S._RightwareOrchestrator(Replay([]), "fake", policy=p, tools=[], max_turns=1,
                                         before_tool_call=p.before_tool_call)
        self.assertIsNone(agent._loop_guard)

    def test_run3_shape_every_approval_executes_including_the_seventh(self):
        model = Replay(RUN3)
        s = self.session(model)
        reply = s.run("x")
        self.assertEqual([(o.tool, o.status) for o in reply.outcomes],
                         [("web_open", "OK"), ("web_type", "OK"), ("web_submit", "OK"), ("web_open", "OK"),
                          ("web_type", "OK"), ("web_submit", "OK"), ("web_open", "OK"), ("web_follow", "OK")])
        rows, approvals, outcomes = audit_pairs(self.audit)
        self.assertEqual(len(approvals), 8)
        self.assertEqual(len(outcomes), 8)
        self.assertEqual(s._policy.pending(), [])
        self.assertNotIn("APPROVED_NOT_EXECUTED", reply.flags)
        self.assertFalse(any("Loop guard" in t for t in model.tool_messages))
        self.assertIn(DOC2, [x["final_url"] for x in reply.sources])

    def test_run1_shape_retry_is_refused_explicitly_without_orphans(self):
        model = Replay(RUN1)
        s = self.session(model)
        reply = s.run("x")
        rows, approvals, outcomes = audit_pairs(self.audit)
        self.assertEqual(len(approvals), len(outcomes))              # no approval without an outcome
        denied = [r for r in rows if not r["allowed"]]
        self.assertEqual([r["reason"] for r in denied], ["limite de chamadas desta ferramenta atingido"])
        refusal = [t for t in model.tool_messages if t.startswith("[RIGHTWARE]")]
        self.assertEqual(len(refusal), 1)
        self.assertIn("limite de chamadas desta ferramenta atingido", refusal[0])
        self.assertEqual(reply.outcomes[-1].status, "OK")            # the following web_follow still runs

    def test_reconciliation_catches_any_future_unexecuted_approval(self):
        """If something between the hook and the tool skips execution again (simulated by putting
        the upstream LoopGuard back), the run closes it as NOT_EXECUTED and flags it."""
        original = S._RightwareOrchestrator.__init__

        def with_upstream_guard(self, *a, **k):
            original(self, *a, **k)
            self._loop_guard = LoopGuard(LoopGuardConfig())
        S._RightwareOrchestrator.__init__ = with_upstream_guard
        try:
            reply = self.session(Replay(RUN3)).run("x")
        finally:
            S._RightwareOrchestrator.__init__ = original
        self.assertIn(("web_open", "NOT_EXECUTED"), [(o.tool, o.status) for o in reply.outcomes])
        self.assertIn("APPROVED_NOT_EXECUTED", reply.flags)
        rows, approvals, outcomes = audit_pairs(self.audit)
        self.assertEqual(len(approvals), len(outcomes))
        self.assertEqual(outcomes[-1]["outcome"], "NOT_EXECUTED")          # closed at the end of the run
        self.assertEqual(outcomes[-1]["reason"], "aprovado mas não executado")

    def test_legitimate_multiple_searches_are_not_cycles(self):
        steps = [lambda m: call("web_open", url=START)]
        for q in ("WSP 1001", "WSP 1002", "widget"):
            steps += [lambda m, q=q: call("web_type", field="F1", text=q), lambda m: call("web_submit", field="F1")]
        steps += [lambda m: call("web_follow", link=link_to(m, "wsp1001.html")),
                  lambda m: call("web_follow", link=link_to(m, "wsp1002.html")), lambda m: {"content": "fim"}]
        s = self.session(Replay(steps))
        reply = s.run("x")
        self.assertEqual([o.status for o in reply.outcomes], ["OK"] * 9)
        self.assertEqual([e["op"] for e in s.browser.events].count("submit"), 3)
        self.assertFalse(any(not e["allowed"] for e in s._policy.log))


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class DangerousLoopsStayBlocked(_SessionCase):
    def denials(self, s):
        return [e["reason"] for e in s._policy.log if not e["allowed"]]

    def test_identical_page_load_third_time_is_blocked_open_and_follow_count_together(self):
        steps = [lambda m: call("web_open", url=START), lambda m: call("web_open", url=DOC1),
                 lambda m: call("web_follow", link=link_to(m, "wsp1002.html")),
                 lambda m: call("web_open", url=DOC2), lambda m: call("web_follow", link=link_to(m, "wsp1002.html")),
                 lambda m: {"content": "fim"}]
        model = Replay(steps)
        s = self.session(model)
        s.run("x")
        self.assertEqual(len(self.denials(s)), 1)
        self.assertIn("acção idêntica já pedida 2 vez(es)", self.denials(s)[0])
        self.assertEqual([e["op"] for e in s.browser.events], ["open", "open", "follow", "open"])
        self.assertTrue(model.tool_messages[-1].startswith("[RIGHTWARE] A ferramenta 'web_follow' NÃO foi executada"))

    def test_same_search_submitted_again_and_again_is_blocked(self):
        steps = [lambda m: call("web_open", url=START), lambda m: call("web_type", field="F1", text="WSP 1001")]
        steps += [lambda m: call("web_submit", field="f1")] * 3 + [lambda m: {"content": "fim"}]
        s = self.session(Replay(steps))
        s.run("x")
        self.assertEqual([e["op"] for e in s.browser.events].count("submit"), 2)
        self.assertIn("acção idêntica", self.denials(s)[0])

    def test_a_b_a_b_and_a_b_c_cycles_with_identical_arguments_are_blocked(self):
        for texts, blocked_at in ((["a", "b", "a", "b"], 3), (["a", "b", "c", "a", "b", "c"], 5)):
            with self.subTest(texts=texts):
                p = P.AgentPolicy(S.TOOLS, allow={"browse"}, budgets=P.Budgets(max_calls=20))
                results = [p.before_tool_call("web_find", {"text": t}) for t in texts]
                self.assertEqual(results.index(False), blocked_at)
                self.assertIn("ciclo repetitivo", p.last_denial)

    def test_loop_denials_consume_no_tool_quota_and_other_actions_continue(self):
        p = P.AgentPolicy(S.TOOLS, allow={"browse"}, budgets=P.Budgets(max_calls=20))
        for _ in range(2):
            self.assertTrue(p.before_tool_call("web_find", {"text": "x"}))
        self.assertFalse(p.before_tool_call("web_find", {"text": "x"}))
        self.assertEqual(p.per_tool["web_find"], 2)
        self.assertEqual(p.calls, 3)                                  # the proposal budget still counts it
        self.assertTrue(p.before_tool_call("web_find", {"text": "y"}))
        self.assertEqual(p.per_tool["web_find"], 3)

    def test_signature_failure_fails_closed(self):
        def broken(name, args):
            raise RuntimeError("boom")
        p = P.AgentPolicy(S.TOOLS, allow={"browse"}, signature=broken)
        self.assertFalse(p.before_tool_call("web_find", {"text": "x"}))
        self.assertEqual(p.per_tool, {})

    def test_quota_refusal_is_explicit_and_not_an_orphan(self):
        steps = [lambda m, u=u: call("web_open", url=u) for u in
                 (START, DOC1, DOC2, f"https://{HOST}/about.html")] + [lambda m: {"content": "fim"}]
        model = Replay(steps)
        s = self.session(model)
        s.run("x")
        self.assertEqual(self.denials(s), ["limite de chamadas desta ferramenta atingido"])
        self.assertIn("limite de chamadas desta ferramenta atingido", model.tool_messages[-1])
        rows, approvals, outcomes = audit_pairs(self.audit)
        self.assertEqual(len(approvals), len(outcomes))

    def test_cancellation_mid_task_is_explicit_and_leaves_no_pending_approval(self):
        holder = {}
        model = Replay(RUN3, hook=lambda i: i == 4 and holder["s"].cancel())
        s = holder["s"] = self.session(model)
        reply = s.run("x")
        self.assertEqual(reply.completion, "HALTED")
        self.assertEqual(reply.halted, "tarefa cancelada")
        self.assertEqual(s._policy.pending(), [])
        rows, approvals, outcomes = audit_pairs(self.audit)
        self.assertEqual(len(approvals), len(outcomes))

    def test_deadline_is_explicit_and_leaves_no_pending_approval(self):
        t = [0.0]
        model = Replay(RUN3, hook=lambda i: t.__setitem__(0, 60.0 * i))
        s = self.session(model, budgets=S.Budgets(max_calls=14, deadline_seconds=200), clock=lambda: t[0])
        reply = s.run("x")
        self.assertEqual(reply.halted, "tempo esgotado")
        self.assertEqual(s._policy.pending(), [])
        rows, approvals, outcomes = audit_pairs(self.audit)
        self.assertEqual(len(approvals), len(outcomes))

    def test_policy_closes_unexecuted_approvals_in_the_audit(self):
        p = P.AgentPolicy(S.TOOLS, allow={"browse"}, audit_path=self.audit)
        self.assertTrue(p.before_tool_call("web_find", {"text": "x"}))
        self.assertEqual(p.pending(), [("web_find", {"text": "x"})])
        self.assertEqual(p.close_pending(), ["web_find"])
        self.assertEqual(p.pending(), [])
        last = json.loads(self.audit.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(last["outcome"], "NOT_EXECUTED")
        with self.assertRaises(PermissionError):
            p.authorize_execution("web_find", {"text": "x"})           # a closed approval cannot be used later


if __name__ == "__main__":
    unittest.main()
