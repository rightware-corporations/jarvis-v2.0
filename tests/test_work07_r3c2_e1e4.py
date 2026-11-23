"""WORK-07 R3-C2-012: E1 (final-answer interception) + E4 (recovery budget). TEST-ONLY experiment.

REAL AgentSession + pinned OrchestratorAgent + AgentPolicy + PublicBrowser over the local R3-C1
archive; FAKE deterministic model; test-only InterceptingEngine (labs/work07_r3c2). Production
run()/_compose() are unchanged (asserted). FAKE-model evidence only, never about Qwen.
"""
import json
from pathlib import Path
import unittest

try:
    import httpx  # noqa: F401
    from rightware.agent import session as S
    from labs.work07_r3c2.scenarios import (FEEDBACK_TAG, INFO_ONLY, OBJECTIVES, OFFSITE, ORIGINALS, START,
                                            call, follow_originals, premature, run_experiment, shown_link)
except ImportError:              # system Python without the pinned venv
    S = None


def audit_rows(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]


def opened(r):
    return [e["final_url"] for e in r["session"].browser.events if e.get("outcome") == "OK"]


class Accounting:
    def assert_accounted(self, r, budget):
        st, calls = r["state"], r["counting"].calls
        self.assertEqual(calls, len(r["model"].received))                    # counter = model's own view
        short = st.orchestrator_generations + st.continuations - calls        # halt short-circuits
        self.assertGreaterEqual(short, 0)
        if short:
            self.assertIsNotNone(r["reply"].halted)
        self.assertLessEqual(st.continuations, budget)
        self.assertLessEqual(calls, r["session"].max_turns + budget)          # bounded, incl. outside max_turns
        rows = audit_rows(r["audit"])
        approvals = [x for x in rows if x["allowed"] and "outcome" not in x]
        outcomes = [x for x in rows if "outcome" in x]
        self.assertEqual(len(approvals), len(outcomes))                       # nothing approved without outcome
        self.assertEqual(r["session"]._policy.pending(), [])


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class E1_Interception(unittest.TestCase, Accounting):
    def test_premature_answer_is_intercepted_and_continuation_reaches_the_originals(self):
        r = run_experiment(INFO_ONLY + [premature] + follow_originals())
        st = r["state"]
        self.assertEqual((st.verdict, st.continuations), ("COMPLETE_VERIFIED", 1))
        for ref in ORIGINALS.values():
            self.assertIn(ref["original"], opened(r))
        last_turn = r["model"].received[len(INFO_ONLY) + 1]                   # what the model got after feedback
        self.assertEqual(last_turn[-2]["content"], premature(None)["content"])  # its candidate answer kept
        self.assertTrue(last_turn[-1]["content"].startswith(FEEDBACK_TAG))
        self.assert_accounted(r, 1)

    def test_continuation_tools_go_through_policy_audit_and_outcomes(self):
        r = run_experiment(INFO_ONLY + [premature] + follow_originals())
        policy, reply = r["session"]._policy, r["reply"]
        self.assertEqual(policy.per_tool, {"web_open": 1, "web_type": 2, "web_submit": 2, "web_follow": 4,
                                           "web_find": 1})                    # one budget across the whole run
        tail = [(o.tool, o.status) for o in reply.outcomes][-3:]
        self.assertEqual(tail, [("web_follow", "OK"), ("web_find", "OK"), ("web_follow", "OK")])
        props = [p for t in r["session"].trace.turns for p in t["proposals"]]
        self.assertTrue(all(p["decision"] == "APPROVED" and p["status"] == "OK" for p in props))
        self.assertEqual(len(r["session"].trace.turns), r["counting"].calls)

    def test_feedback_is_code_generated_without_page_text_or_urls(self):
        r = run_experiment(INFO_ONLY + [premature] + follow_originals())
        fb = r["state"].feedback_sent[0]
        self.assertIn("O1: abrir o documento original de AX-101", fb)
        self.assertIn("O2: abrir o documento original de AX-202", fb)
        for forbidden in ("http", "Summary", "Status history", "PAGINA-NAO-CONFIAVEL", ".html"):
            self.assertNotIn(forbidden, fb)

    def test_terminal_incomplete_when_continuation_cannot_satisfy(self):
        steps = INFO_ONLY + [premature, lambda m: call("web_open", url=f"{OFFSITE}/ax-101.html"),
                             lambda m: {"content": "Não consegui abrir os originais."}]
        r = run_experiment(steps)
        st = r["state"]
        self.assertEqual((st.verdict, st.missing, st.continuations), ("INCOMPLETE_BUDGET_EXHAUSTED", ["O1", "O2"], 1))
        self.assertEqual([o.status for o in r["reply"].outcomes][-1], "REFUSED")
        self.assertFalse(any("mirror" in u for u in opened(r)))
        self.assert_accounted(r, 1)

    def test_a_failed_load_of_the_required_url_is_not_evidence(self):
        from labs.work07_r3c2.interception import Objective
        missing_doc = ORIGINALS["AX-101"]["original"].replace("ax-101", "ax-303")      # 404 on the allowed host
        objective = (Objective("O9", "abrir o documento original de AX-303", missing_doc),)
        steps = INFO_ONLY + [premature, lambda m: call("web_open", url=missing_doc),
                             lambda m: {"content": "O documento não existe."}]
        r = run_experiment(steps, objectives=objective)
        events = [e for e in r["session"].browser.events if e.get("final_url") == missing_doc]
        self.assertEqual([e["outcome"] for e in events], ["HTTP_ERROR"])
        self.assertEqual((r["state"].verdict, r["state"].missing), ("INCOMPLETE_BUDGET_EXHAUSTED", ["O9"]))
        self.assert_accounted(r, 1)

    def test_production_path_is_unchanged_and_restored(self):
        original = S._GuardedEngine
        run_experiment(INFO_ONLY + [premature] + follow_originals())
        self.assertIs(S._GuardedEngine, original)
        from labs.work07_r3c1.scenarios import run_scenario
        s, reply, model, _ = run_scenario("A_incomplete")                    # no interception installed
        self.assertEqual(reply.completion, "ANSWERED_WITH_SOURCES")           # R3-C1 finding still holds
        self.assertFalse(any(FEEDBACK_TAG in m["content"] for turn in model.received for m in turn))


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class E4_RecoveryBudget(unittest.TestCase, Accounting):
    def test_budget_zero_gives_no_continuation(self):
        r = run_experiment(INFO_ONLY + [premature], budget=0)
        self.assertEqual((r["state"].verdict, r["state"].continuations), ("INCOMPLETE_BUDGET_EXHAUSTED", 0))
        self.assert_accounted(r, 0)

    def test_repeated_premature_answers_exhaust_the_budget(self):
        for budget in (1, 2):
            with self.subTest(budget=budget):
                r = run_experiment(INFO_ONLY + [premature] * 4, budget=budget)
                st = r["state"]
                self.assertEqual((st.verdict, st.continuations), ("INCOMPLETE_BUDGET_EXHAUSTED", budget))
                self.assertEqual(r["counting"].calls, len(INFO_ONLY) + 1 + budget)
                self.assertEqual(len(st.feedback_sent), budget)
                self.assert_accounted(r, budget)

    def test_deadline_reached_before_continuation_stops_without_reprompt(self):
        t = [0.0]
        hook = lambda n: t.__setitem__(0, 1000.0 if n >= len(INFO_ONLY) else 0.0)  # noqa: E731
        r = run_experiment(INFO_ONLY + [premature] + follow_originals(), clock=lambda: t[0], hook=hook,
                           budgets=S.Budgets(max_calls=14, deadline_seconds=900))
        st = r["state"]
        self.assertEqual((st.verdict, st.continuations), ("HALTED", 0))
        self.assertIn(("halted_before_continuation", "tempo esgotado"), st.events)
        self.assertEqual(r["counting"].calls, len(INFO_ONLY) + 1)
        self.assert_accounted(r, 1)

    def test_cancellation_before_continuation_stops_without_reprompt(self):
        holder = {}
        hook = lambda n: n == len(INFO_ONLY) and holder["s"].cancel()          # noqa: E731
        steps = INFO_ONLY + [premature] + follow_originals()
        orig_init = S.AgentSession.__init__              # capture the session run_experiment creates

        def init(self, *a, **k):
            orig_init(self, *a, **k)
            holder["s"] = self
        S.AgentSession.__init__ = init
        try:
            r = run_experiment(steps, hook=hook)
        finally:
            S.AgentSession.__init__ = orig_init
        st = r["state"]
        self.assertEqual((st.verdict, st.continuations), ("HALTED", 0))
        self.assertIn(("halted_before_continuation", "tarefa cancelada"), st.events)
        self.assert_accounted(r, 1)

    def test_tool_quota_exhausted_during_continuation_is_denied_and_not_evidence(self):
        steps = (INFO_ONLY[:4] + [lambda m: call("web_open", url=ORIGINALS["AX-101"]["info"]),
                                  lambda m: call("web_open", url=ORIGINALS["AX-202"]["info"]), premature,
                                  lambda m: call("web_open", url=ORIGINALS["AX-101"]["original"]),
                                  lambda m: {"content": "Sem quota para abrir o original."}])
        r = run_experiment(steps)
        st, policy = r["state"], r["session"]._policy
        self.assertEqual(st.verdict, "INCOMPLETE_BUDGET_EXHAUSTED")
        self.assertEqual(policy.per_tool["web_open"], 3)                       # quota NOT reset by continuation
        self.assertEqual([e["reason"] for e in policy.log if not e["allowed"]],
                         ["limite de chamadas desta ferramenta atingido"])
        self.assertNotIn(ORIGINALS["AX-101"]["original"], opened(r))
        self.assert_accounted(r, 1)

    def test_anti_loop_denial_during_continuation(self):
        steps = (INFO_ONLY[:4] + [lambda m: call("web_open", url=ORIGINALS["AX-101"]["info"]), premature,
                                  lambda m: call("web_follow", link=shown_link(m, "/info/ax-101/")),
                                  lambda m: {"content": "Fim."}])
        r = run_experiment(steps)
        denied = [e for e in r["session"]._policy.log if not e["allowed"]]
        self.assertEqual(len(denied), 1)
        self.assertIn("acção idêntica", denied[0]["reason"])
        self.assertEqual(r["state"].verdict, "INCOMPLETE_BUDGET_EXHAUSTED")
        self.assert_accounted(r, 1)

    def test_approved_but_not_executed_during_continuation_is_not_evidence(self):
        from openjarvis.agents.loop_guard import LoopGuard, LoopGuardConfig
        guard = lambda: LoopGuard(LoopGuardConfig(poll_tool_budget=2, warn_before_block=False))  # noqa: E731
        r = run_experiment(INFO_ONLY + [premature] + follow_originals(), upstream_guard=guard)
        reply, st = r["reply"], r["state"]
        self.assertIn("APPROVED_NOT_EXECUTED", reply.flags)
        self.assertIn(("web_follow", "NOT_EXECUTED"), [(o.tool, o.status) for o in reply.outcomes])
        self.assertNotEqual(st.verdict, "COMPLETE_VERIFIED")
        self.assertNotIn(ORIGINALS["AX-101"]["original"], opened(r))
        self.assert_accounted(r, 1)

    def test_no_inference_after_terminal_halt(self):
        r = run_experiment(INFO_ONLY + [premature] + follow_originals(),
                           budgets=S.Budgets(max_calls=len(INFO_ONLY), deadline_seconds=900))
        st = r["state"]
        self.assertEqual(st.verdict, "HALTED")
        self.assertEqual(r["reply"].halted, "limite de passos atingido")
        self.assertEqual(r["counting"].calls, len(INFO_ONLY))                  # the model never got another turn
        self.assertEqual(st.continuations, 0)
        self.assert_accounted(r, 1)

    def test_generations_outside_max_turns_are_counted_and_bounded(self):
        max_turns = len(INFO_ONLY) + 1                                         # premature answer on the last turn
        r = run_experiment(INFO_ONLY + [premature] + follow_originals(), max_turns=max_turns)
        st = r["state"]
        self.assertEqual(st.continuations, 1)
        self.assertEqual(r["counting"].calls, max_turns + 1)                  # one generation beyond max_turns
        self.assertEqual(st.orchestrator_generations, max_turns)
        self.assertEqual(r["reply"].halted, "limite de turnos atingido")
        self.assert_accounted(r, 1)


if __name__ == "__main__":
    unittest.main()
