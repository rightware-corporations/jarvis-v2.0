"""Issue #9: the refusal message sent to the model must describe the CURRENT call.

Before the fix, a call rejected by the pinned upstream orchestrator before the policy hook
(malformed JSON / non-object arguments) got ``AgentPolicy.last_denial``, which could be the
reason of an EARLIER refusal. REAL AgentSession + pinned OrchestratorAgent + FAKE model; no Qwen.
"""
import json
import unittest

try:
    import httpx  # noqa: F401
    from openjarvis.core.types import ToolResult
    from openjarvis.tools import _stubs as upstream_tools
    from rightware.agent import session as S
    from labs.work07_r3c1.scenarios import FakeModel, INSTRUCTION, call, scenario_steps
    from labs.work07_r3c1.site import HOST, START, Archive
except ImportError:
    S = None

ANTI_LOOP = "acção idêntica já pedida 2 vez(es)"
BAD_JSON = "os argumentos não são JSON válido (recusada antes da política)"
NOT_OBJECT = "os argumentos não são um objecto JSON (recusada antes da política)"


def raw(name, arguments, cid):
    return {"content": "", "tool_calls": [{"id": cid, "name": name, "arguments": arguments}]}


def run(steps, **kw):
    model = FakeModel(steps)
    archive = Archive()
    kw.setdefault("budgets", S.Budgets(max_calls=14, deadline_seconds=900))
    s = S.AgentSession(model, "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,), start_url=START,
                       browser_fetcher=archive.fetcher(), max_turns=14, **kw)
    reply = s.run(INSTRUCTION)
    msgs = [m["content"] for m in model.received[-1] if m["role"].lower().endswith("tool")]
    return s, reply, msgs, archive


THREE_OPENS = [lambda m: call("web_open", url=START)] * 3       # 3rd one is denied by the anti-loop rule


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class StaleReasonFixed(unittest.TestCase):
    def test_earlier_refusal_then_malformed_json_gets_its_own_reason(self):
        for kw in ({}, {"trace": True}, {"receipts": True}, {"trace": True, "receipts": True}):
            with self.subTest(kw=kw):
                s, _, msgs, _ = run(THREE_OPENS + [lambda m: raw("web_find", "{not json", "bad1"),
                                                   lambda m: {"content": "fim"}], **kw)
                self.assertIn(ANTI_LOOP, msgs[2])                 # the earlier refusal, correctly explained
                self.assertIn(BAD_JSON, msgs[3])
                self.assertNotIn(ANTI_LOOP, msgs[3])              # issue #9: no stale reason
                if kw.get("trace"):
                    denied = [p for t in s.trace.turns for p in t["proposals"] if p["decision"] == "DENIED"]
                    self.assertEqual([d["reason"][:30] for d in denied], [ANTI_LOOP[:30], BAD_JSON[:30]])
                if kw.get("receipts"):
                    self.assertEqual(s.receipts[-1].policy_reason, BAD_JSON)

    def test_non_object_arguments_and_first_call_malformed(self):
        _, _, msgs, _ = run([lambda m: raw("web_find", "[1, 2]", "arr"), lambda m: raw("web_open", "", "empty"),
                             lambda m: raw("web_open", "{", "trunc"), lambda m: {"content": "fim"}])
        self.assertIn(NOT_OBJECT, msgs[0])
        self.assertIn("NÃO foi executada", msgs[1])               # empty args reach the policy (schema reason)
        self.assertIn("argumentos em falta", msgs[1])
        self.assertIn(BAD_JSON, msgs[2])

    def test_policy_refusals_keep_their_exact_reasons(self):
        quota = [lambda m, u=u: call("web_open", url=u) for u in
                 (START, f"https://{HOST}/info/ax-101/", f"https://{HOST}/info/ax-202/", f"https://{HOST}/about")]
        _, _, msgs, _ = run(quota + [lambda m: call("web_read", url=START), lambda m: {"content": "fim"}])
        self.assertIn("limite de chamadas desta ferramenta atingido", msgs[3])
        self.assertIn("capacidade 'web' não autorizada nesta sessão", msgs[4])   # current policy reason

    def test_cancellation_reason_is_current(self):
        holder = {}
        steps = [lambda m: call("web_open", url=START), lambda m: (holder["s"].cancel() or call("web_find", text="x"))]
        model = FakeModel(steps + [lambda m: {"content": "fim"}])
        s = S.AgentSession(model, "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,), start_url=START,
                           browser_fetcher=Archive().fetcher(), budgets=S.Budgets(max_calls=14), max_turns=14)
        holder["s"] = s
        s.run(INSTRUCTION)
        msgs = [m["content"] for m in model.received[-1] if m["role"].lower().endswith("tool")] if len(model.received) > 2 else []
        denied = [e for e in s._policy.log if not e["allowed"]]
        self.assertEqual(denied[-1]["reason"], "tarefa cancelada")
        if msgs:
            self.assertIn("tarefa cancelada", msgs[-1])

    def test_batch_denial_reason_is_reported_for_each_call(self):
        batch = {"content": "", "tool_calls": [
            {"id": "b1", "name": "web_find", "arguments": json.dumps({"text": "a"})},
            {"id": "b2", "name": "shell_exec", "arguments": "{}"}]}
        s, _, msgs, _ = run([lambda m: call("web_open", url=START), lambda m: batch, lambda m: {"content": "fim"}])
        self.assertIn("lote fail-closed", msgs[1])
        self.assertIn("lote fail-closed", msgs[2])

    def test_executor_early_return_message_is_upstream_current_text(self):
        original = upstream_tools.ToolExecutor.execute

        def early(self, tool_call):
            if tool_call.name == "web_find":
                return ToolResult(tool_name=tool_call.name, content="Rate limit exceeded for tool 'web_find'.",
                                  success=False)
            return original(self, tool_call)
        upstream_tools.ToolExecutor.execute = early
        try:
            s, _, msgs, _ = run(THREE_OPENS + [lambda m: call("web_find", text="x"), lambda m: {"content": "fim"}],
                                receipts=True)
        finally:
            upstream_tools.ToolExecutor.execute = original
        self.assertEqual(msgs[3], "Rate limit exceeded for tool 'web_find'.")   # approved call: no refusal text
        self.assertNotIn(ANTI_LOOP, msgs[3])
        self.assertEqual(s.receipts[-1].status, "NOT_EXECUTED")

    def test_fix_changes_nothing_for_valid_runs_and_grants_nothing(self):
        for name in ("A_incomplete", "B_complete", "D_refused", "E_premature"):
            with self.subTest(name=name):
                model = FakeModel(scenario_steps(name))
                s = S.AgentSession(model, "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,),
                                   start_url=START, browser_fetcher=Archive().fetcher(),
                                   budgets=S.Budgets(max_calls=14, deadline_seconds=900), max_turns=14)
                reply = s.run(INSTRUCTION)
                self.assertNotIn("recusada antes da política", reply.text)
        _, reply, _, archive = run(THREE_OPENS + [lambda m: raw("web_find", "{not json", "bad1"),
                                                  lambda m: {"content": "fim"}])
        self.assertEqual([o.tool for o in reply.outcomes], ["web_open", "web_open"])   # malformed never executed
        self.assertEqual(len(archive.requests), 2)


if __name__ == "__main__":
    unittest.main()
