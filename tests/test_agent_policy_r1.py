"""WORK-05 R1-C: policy and execution correctness (findings F2, F3, F4). No model, no network."""
import json
from pathlib import Path
import tempfile
import unittest

from rightware.agent import policy as P

TOOLS = {
    "web_read": P.ToolDef("web_read", "d", {"url": {"type": "string", "maxLength": 2048}}, ("url",),
                          session_flag="web", consequential=False, max_calls=3),
    "windows_action": P.ToolDef("windows_action", "d", {"action_id": {"type": "string", "enum": ["notepad"]}},
                                ("action_id",), session_flag="actions", consequential=True, max_calls=1),
}


def raw(name, args):
    return {"name": name, "arguments": json.dumps(args)}


def drive(p, batch):
    """What the orchestrator does: batch_guard, then the hook for each call in order."""
    p.batch_guard(batch)
    return [p.before_tool_call(c["name"], json.loads(c["arguments"])) for c in batch]


class BatchAtomicity(unittest.TestCase):                                   # F2
    def test_capability_failure_anywhere_denies_the_whole_batch(self):
        p = P.AgentPolicy(TOOLS, allow={"web"})
        self.assertEqual(drive(p, [raw("web_read", {"url": "https://e.org"}),
                                   raw("windows_action", {"action_id": "notepad"})]), [False, False])
        self.assertEqual(p.per_tool, {})

    def test_per_tool_quota_counted_across_the_batch(self):
        p = P.AgentPolicy(TOOLS, allow={"web"})
        batch = [raw("web_read", {"url": f"https://e.org/{i}"}) for i in range(4)]
        self.assertEqual(drive(p, batch), [False] * 4)

    def test_quota_already_used_plus_batch(self):
        p = P.AgentPolicy(TOOLS, allow={"web"})
        self.assertTrue(p.before_tool_call("web_read", {"url": "https://e.org/0"}))
        batch = [raw("web_read", {"url": f"https://e.org/{i}"}) for i in (1, 2, 3)]
        self.assertEqual(drive(p, batch), [False] * 3)

    def test_global_budget_counted_across_the_batch(self):
        p = P.AgentPolicy(TOOLS, allow={"web"}, budgets=P.Budgets(max_calls=2))
        batch = [raw("web_read", {"url": f"https://e.org/{i}"}) for i in range(3)]
        self.assertEqual(drive(p, batch), [False] * 3)

    def test_cancelled_or_expired_session_denies_the_batch(self):
        p = P.AgentPolicy(TOOLS, allow={"web"})
        p.cancel()
        self.assertEqual(drive(p, [raw("web_read", {"url": "https://e.org/a"}),
                                   raw("web_read", {"url": "https://e.org/b"})]), [False, False])
        t = [0.0]
        q = P.AgentPolicy(TOOLS, allow={"web"}, budgets=P.Budgets(deadline_seconds=5), clock=lambda: t[0])
        t[0] = 6
        self.assertEqual(drive(q, [raw("web_read", {"url": "https://e.org/a"}),
                                   raw("web_read", {"url": "https://e.org/b"})]), [False, False])

    def test_valid_batch_still_executes(self):
        p = P.AgentPolicy(TOOLS, allow={"web"})
        batch = [raw("web_read", {"url": f"https://e.org/{i}"}) for i in range(3)]
        self.assertEqual(drive(p, batch), [True] * 3)

    def test_malformed_arguments_deny_the_batch(self):
        p = P.AgentPolicy(TOOLS, allow={"web"})
        batch = [raw("web_read", {"url": "https://e.org"}), {"name": "web_read", "arguments": "{not json"}]
        p.batch_guard(batch)
        self.assertFalse(p.before_tool_call("web_read", {"url": "https://e.org"}))


class BoundaryRecheck(unittest.TestCase):                                  # F3
    def test_deadline_rechecked_at_execution(self):
        t = [0.0]
        p = P.AgentPolicy(TOOLS, allow={"web"}, budgets=P.Budgets(deadline_seconds=10), clock=lambda: t[0])
        args = {"url": "https://e.org"}
        self.assertTrue(p.before_tool_call("web_read", args))
        t[0] = 11
        with self.assertRaises(PermissionError):
            p.authorize_execution("web_read", args)

    def test_cancel_rechecked_at_execution(self):
        p = P.AgentPolicy(TOOLS, allow={"web"})
        args = {"url": "https://e.org"}
        self.assertTrue(p.before_tool_call("web_read", args))
        p.cancel()
        with self.assertRaises(PermissionError):
            p.authorize_execution("web_read", args)


class MandatoryAudit(unittest.TestCase):                                   # F4
    def broken(self):
        d = Path(tempfile.mkdtemp())
        (d / "blocker").write_text("x")
        return d / "blocker" / "agent.jsonl"          # parent is a file: every write fails

    def test_unpersistable_audit_denies_without_side_effects(self):
        p = P.AgentPolicy(TOOLS, allow={"web"}, audit_path=self.broken())
        self.assertFalse(p.before_tool_call("web_read", {"url": "https://e.org"}))
        self.assertEqual(p.per_tool, {})
        self.assertEqual(p._approved, [])
        self.assertEqual(p.audit_failures, 1)
        with self.assertRaises(PermissionError):
            p.authorize_execution("web_read", {"url": "https://e.org"})

    def test_audit_failure_after_execution_is_reported(self):
        good = Path(tempfile.mkdtemp()) / "agent.jsonl"
        p = P.AgentPolicy(TOOLS, allow={"web"}, audit_path=good)
        args = {"url": "https://e.org"}
        self.assertTrue(p.before_tool_call("web_read", args))
        p.authorize_execution("web_read", args)
        p.audit_path = self.broken()
        self.assertFalse(p.note_outcome("web_read", args, "OK"))
        self.assertEqual(p.audit_failures, 1)

    def test_working_audit_records_before_state_changes(self):
        path = Path(tempfile.mkdtemp()) / "agent.jsonl"
        p = P.AgentPolicy(TOOLS, allow={"web"}, audit_path=path)
        self.assertTrue(p.before_tool_call("web_read", {"url": "https://e.org"}))
        self.assertTrue(p.note_outcome("web_read", {"url": "https://e.org"}, "OK"))
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)
        self.assertEqual(p.audit_failures, 0)


if __name__ == "__main__":
    unittest.main()
