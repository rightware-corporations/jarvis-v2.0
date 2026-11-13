"""WORK-07 R3-C2-019: receipt linking against a REAL AgentSession and FAKE model.

No product modifications. Neither a successful G2 correlation nor a URL match
proves verified original-document identity or factual correctness (G3).
"""
import unittest
from dataclasses import replace

from labs.work07_r3c2.live_receipt_adapter import correlate, observed_originals

try:
    import httpx  # noqa: F401
    from labs.work07_r3c1.scenarios import run_scenario
    from labs.work07_r3c1.site import ORIGINALS
    from rightware.agent.session import AgentReply, ToolOutcome
except ImportError:
    run_scenario = None


@unittest.skipIf(run_scenario is None, "pinned OpenJarvis venv required")
class LiveReceiptAdapterLab(unittest.TestCase):
    def test_incomplete_browser_run_does_not_prove_originals(self):
        session, reply, _, _ = run_scenario("A_incomplete")
        refs = {key: value["original"] for key, value in ORIGINALS.items()}
        self.assertEqual(observed_originals(session, reply, refs),
                         {key: "INCOMPLETE" for key in refs})
        self.assertEqual(reply.completion, "ANSWERED_WITH_SOURCES")

    def test_complete_browser_run_has_observed_originals_but_not_g3(self):
        session, reply, _, _ = run_scenario("B_complete")
        refs = {key: value["original"] for key, value in ORIGINALS.items()}
        grades = observed_originals(session, reply, refs)
        self.assertEqual(set(grades), set(refs))
        self.assertTrue(all(g in ("G1", "G2_OBSERVATIONAL") for g in grades.values()))
        self.assertFalse(reply.verification["answer_factually_verified"])

    def test_real_trace_correlates_a_unique_tool_outcome(self):
        session, reply, _, _ = run_scenario("B_complete")
        rows = correlate(session, reply)
        self.assertTrue(rows)
        self.assertTrue(any(r.grade == "G2_OBSERVATIONAL" and r.call_id for r in rows))
        self.assertTrue(all(r.grade != "G3" for r in rows))

    def test_trace_disabled_never_promotes_to_g2(self):
        session, reply, _, _ = run_scenario("B_complete", trace=False)
        rows = correlate(session, reply)
        self.assertTrue(rows)
        self.assertFalse(any(r.grade == "G2_OBSERVATIONAL" for r in rows))

    def test_trace_hashed_result_mutated_is_only_g1(self):
        session, reply, _, _ = run_scenario("B_complete")
        for turn in session.trace.turns:
            for p in turn["proposals"]:
                if p.get("result_sha256"):
                    p["result_sha256"] = "0000000000000000"
        self.assertFalse(any(r.grade == "G2_OBSERVATIONAL" for r in correlate(session, reply)))

    def test_duplicate_matching_outcome_never_gets_g2(self):
        session, reply, _, _ = run_scenario("B_complete")
        o = next(o for o in reply.outcomes if o.status == "OK")
        clone = AgentReply(reply.text, reply.completion, reply.outcomes + [o], reply.sources,
                           reply.halted, reply.flags, reply.verification)
        rows = correlate(session, clone)
        matching = [r for r in rows if r.tool == o.tool and
                    r.content_digest == __import__("hashlib").sha256(o.content.encode("utf-8")).hexdigest()[:16]]
        self.assertGreaterEqual(len(matching), 2)
        self.assertTrue(all(r.grade != "G2_OBSERVATIONAL" for r in matching))

    def test_unsupported_claim_does_not_invent_receipt(self):
        session, reply, _, _ = run_scenario("A_incomplete")
        clone = replace(reply, text=reply.text + "\nAbri o original B.")
        self.assertEqual(correlate(session, clone), correlate(session, reply))

    def test_nonexecuted_synthetic_outcome_is_never_g2(self):
        session, reply, _, _ = run_scenario("A_incomplete")
        clone = replace(reply, outcomes=reply.outcomes +
                        [ToolOutcome("web_follow", "NOT_EXECUTED", "not executed", {})])
        self.assertEqual(correlate(session, clone)[-1].grade, "UNKNOWN")

    def test_repeated_event_is_not_unique_browser_provenance(self):
        session, reply, _, _ = run_scenario("B_complete")
        e = next(e for e in session.browser.events if e.get("outcome") == "OK")
        session.browser.events.append(dict(e))
        rows = correlate(session, reply)
        affected = [r for r in rows if r.url == e["final_url"] and r.status == "OK"]
        self.assertTrue(affected)
        self.assertTrue(all(r.grade != "G2_OBSERVATIONAL" for r in affected))


if __name__ == "__main__":
    unittest.main()
