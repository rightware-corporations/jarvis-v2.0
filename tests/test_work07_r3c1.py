"""WORK-07 R3-C1: deterministic reconstruction of premature task completion and observability.

REAL AgentSession + PublicBrowser + pinned OrchestratorAgent; FAKE scripted model (it can only
use link ids it was SHOWN); synthetic archive served locally (labs/work07_r3c1/site.py). These
tests OBSERVE current product behaviour; they do not change _compose() and are NOT evidence
about Qwen.
"""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest

try:
    import httpx  # noqa: F401
    from rightware.agent import session as S
    from labs.work07_r3c1.scenarios import INSTRUCTION, PLAUSIBLE, FakeModel, report, run_scenario, scenario_steps
    from labs.work07_r3c1.site import HOST, ORIGINALS, START, Archive
except ImportError:              # system Python without the pinned venv
    S = None


def tool_messages(model):
    """Every tool message the FAKE model received, in order (from its last turn's history)."""
    return [m["content"] for m in model.received[-1] if m["role"].lower().endswith("tool")]


def proposals(session):
    return [p for t in session.trace.turns for p in t["proposals"]]


def opened(session):
    return [e["final_url"] for e in session.browser.events if e.get("outcome") == "OK"]


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class ScenarioA_IncompleteTask(unittest.TestCase):
    """Information pages only + plausible answer -> the product still says ANSWERED_WITH_SOURCES."""

    @classmethod
    def setUpClass(cls):
        cls.s, cls.reply, cls.model, _ = run_scenario("A_incomplete")

    def test_answer_text_is_plausible(self):
        self.assertEqual(self.model.final_texts[-1]["content"], PLAUSIBLE)

    def test_pages_actually_consulted_are_information_pages(self):
        got = opened(self.s)
        for doc, ref in ORIGINALS.items():
            self.assertIn(ref["info"], got)
            self.assertNotIn(ref["original"], got)

    def test_current_product_classification_is_answered_with_sources(self):
        # OBSERVED behaviour (the finding R3-C1 reproduces): no original was opened, yet completion
        # is ANSWERED_WITH_SOURCES with no flag, because any successful page read counts as a source.
        self.assertEqual(self.reply.completion, "ANSWERED_WITH_SOURCES")
        self.assertEqual(self.reply.flags, [])
        self.assertEqual({x["final_url"] for x in self.reply.sources}, set(opened(self.s)))

    def test_objectives_still_unproven_are_reported_by_the_reconstruction(self):
        r = report("A_incomplete")
        self.assertEqual(r["originals_not_opened"], [ref["original"] for ref in ORIGINALS.values()])
        self.assertEqual(r["objectives_unproven"], ["AX-101: original not opened", "AX-202: original not opened"])

    def test_the_original_links_existed_and_one_was_even_presented(self):
        links = {url: lid for lid, (url, _) in self.s.browser.links.items()}
        for ref in ORIGINALS.values():
            self.assertIn(ref["original"], links)                       # registered by the browser
        vis = self.s.trace.final["links"]
        self.assertIn(links[ORIGINALS["AX-101"]["original"]], vis["presented"])     # shown, not used
        self.assertNotIn(links[ORIGINALS["AX-202"]["original"]], vis["presented"])  # hidden, not used
        self.assertNotIn(links[ORIGINALS["AX-101"]["original"]], vis["used"])


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class ScenarioB_CompleteTask(unittest.TestCase):
    def test_both_originals_are_in_real_tool_results(self):
        s, reply, model, _ = run_scenario("B_complete")
        executed = {o.evidence.get("final_url") for o in reply.outcomes if o.status == "OK"}
        for ref in ORIGINALS.values():
            self.assertIn(ref["original"], executed)
            self.assertIn(ref["original"], [x["final_url"] for x in reply.sources])
        self.assertEqual(report("B_complete")["originals_not_opened"], [])
        titles = {e["final_url"]: e["title"] for e in s.browser.events if e.get("outcome") == "OK"}
        for ref in ORIGINALS.values():
            self.assertEqual(titles[ref["original"]], ref["title"])


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class ScenarioC_HiddenLink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s, cls.reply, cls.model, _ = run_scenario("C_hidden_link")
        cls.lid = next(l for l, (u, _) in cls.s.browser.links.items() if u == ORIGINALS["AX-202"]["original"])
        cls.p = proposals(cls.s)

    def test_registered_but_absent_from_the_first_view(self):
        info_view = self.p[3]["view"]
        self.assertEqual(self.p[3]["name"], "web_follow")
        self.assertEqual(info_view["page"], ORIGINALS["AX-202"]["info"])
        self.assertNotIn(self.lid, info_view["shown_links"])
        self.assertEqual(len(info_view["shown_links"]), 25)
        self.assertGreater(info_view["not_shown_links"], 0)
        self.assertTrue(info_view["text_cut_in_view"])
        self.assertNotIn(self.lid + ":", tool_messages(self.model)[3])   # really not in what the model got

    def test_the_fake_model_could_not_use_an_id_it_was_not_shown(self):
        self.assertEqual((self.p[4]["name"], self.p[4]["status"]), ("web_follow", "REFUSED"))

    def test_web_find_discovers_it_and_web_follow_opens_it(self):
        self.assertIn(self.lid, self.p[5]["view"]["find_matches"])
        self.assertIn(self.lid + ":", tool_messages(self.model)[5])
        self.assertEqual((self.p[6]["status"], self.p[6]["view"]["followed"]), ("OK", self.lid))
        self.assertEqual(self.p[6]["view"]["page"], ORIGINALS["AX-202"]["original"])

    def test_registered_presented_used_are_distinct_facts(self):
        vis = self.s.trace.final["links"]
        self.assertGreater(vis["registered"], len(vis["presented"]))
        self.assertGreater(vis["registered_not_presented"], 0)
        self.assertIn(self.lid, vis["presented"])
        self.assertIn(self.lid, vis["used"])
        self.assertEqual(vis["used_without_presentation"], [])


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class ScenarioD_RefusedCalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s, cls.reply, cls.model, _ = run_scenario("D_refused")

    def test_refused_and_denied_operations_are_not_evidence_of_reading(self):
        p = proposals(self.s)
        statuses = [(x["name"], x["decision"], x["status"]) for x in p]
        self.assertIn(("web_open", "APPROVED", "REFUSED"), statuses)         # off-site mirror
        self.assertIn(("web_follow", "DENIED", "DENIED"), statuses)          # same page a 3rd time
        self.assertEqual(statuses[-1], ("web_open", "DENIED", "DENIED"))      # quota
        sources = [x["final_url"] for x in self.reply.sources]
        self.assertNotIn(ORIGINALS["AX-101"]["original"], sources)
        self.assertFalse(any("mirror.other.example" in u for u in sources + opened(self.s)))
        self.assertEqual(Archive().requests, [])
        self.assertIn("TOOL_REFUSALS", self.reply.flags)

    def test_each_denial_carries_its_reason_to_the_model_and_the_trace(self):
        denied = [x for x in proposals(self.s) if x["decision"] == "DENIED"]
        self.assertEqual([d["reason"][:24] for d in denied], ["acção idêntica já pedida", "limite de chamadas desta"])
        msgs = [m for m in tool_messages(self.model) if m.startswith("[RIGHTWARE]")]
        self.assertEqual(len(msgs), 2)

    def test_not_executed_approval_is_not_a_source(self):
        """NOT_EXECUTED path (R3-B reconciliation): an upstream guard re-injected with a tiny budget
        skips the 2nd web_follow after approval; it must not count as a page read."""
        from openjarvis.agents.loop_guard import LoopGuard, LoopGuardConfig
        original = S._RightwareOrchestrator.__init__

        def with_guard(self, *a, **k):
            original(self, *a, **k)
            self._loop_guard = LoopGuard(LoopGuardConfig(poll_tool_budget=1, warn_before_block=False))
        S._RightwareOrchestrator.__init__ = with_guard
        try:
            s, reply, model, _ = run_scenario("A_incomplete")
        finally:
            S._RightwareOrchestrator.__init__ = original
        self.assertIn("APPROVED_NOT_EXECUTED", reply.flags)
        not_executed = [x for x in proposals(s) if x["status"] == "NOT_EXECUTED"]
        self.assertTrue(not_executed)
        self.assertTrue(all(x["decision"] == "APPROVED" for x in not_executed))
        self.assertNotIn(ORIGINALS["AX-202"]["info"], [x["final_url"] for x in reply.sources])


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class ScenarioE_PrematureTermination(unittest.TestCase):
    def test_one_information_page_then_stop_is_still_answered_with_sources(self):
        s, reply, model, _ = run_scenario("E_premature")
        self.assertEqual(opened(s)[-1], ORIGINALS["AX-101"]["info"])
        self.assertEqual(reply.completion, "ANSWERED_WITH_SOURCES")      # OBSERVED current behaviour
        self.assertEqual(reply.flags, [])
        r = report("E_premature")
        self.assertEqual(len(r["objectives_unproven"]), 2)               # AX-202 never even searched
        self.assertFalse(any("AX-202" in str(p["args"]) for p in proposals(s)))


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class TraceProperties(unittest.TestCase):
    def test_result_hashes_are_the_hashes_of_what_the_model_received(self):
        for name in ("A_incomplete", "C_hidden_link", "D_refused"):
            with self.subTest(name=name):
                s, reply, model, _ = run_scenario(name)
                got = [hashlib.sha256(m.encode("utf-8")).hexdigest()[:16] for m in tool_messages(model)]
                self.assertEqual([p["result_sha256"] for p in proposals(s)], got)
                views = [p["view"]["view_sha256"] for p in proposals(s) if p.get("view", {}).get("view_sha256")]
                self.assertTrue(set(views) <= set(got))

    def test_turns_correlate_response_ids_tools_offered_and_final_state(self):
        s, reply, model, _ = run_scenario("B_complete")
        turns = s.trace.turns
        self.assertEqual(len(turns), len(model.received))
        self.assertTrue(all(len(t["response_id"]) == 16 for t in turns))
        self.assertTrue(all(t["tools_offered"] == ["web_find", "web_follow", "web_open", "web_submit", "web_type"]
                            for t in turns))
        self.assertEqual(s.trace.final["completion"], reply.completion)
        self.assertEqual(s.trace.final["turns"], len(turns))

    def test_trace_is_off_by_default(self):
        archive = Archive()
        s = S.AgentSession(FakeModel(scenario_steps("E_premature")), "fake", allow={"browse"},
                           confirm=lambda q: None, sites=(HOST,), start_url=START, browser_fetcher=archive.fetcher(),
                           budgets=S.Budgets(max_calls=14), max_turns=14)
        s.run(INSTRUCTION)
        self.assertIsNone(s.trace)
        self.assertFalse(s.browser.observe)
        self.assertIsNone(s.browser.last_view)

    def test_tracing_changes_no_decision_and_no_model_input(self):
        boundary = re.compile(r"PAGINA-NAO-CONFIAVEL [0-9A-F]{16}")
        for name in ("A_incomplete", "D_refused"):
            with self.subTest(name=name):
                on = run_scenario(name, trace=True)
                off = run_scenario(name, trace=False)
                self.assertEqual([(o.tool, o.status) for o in on[1].outcomes],
                                 [(o.tool, o.status) for o in off[1].outcomes])
                self.assertEqual([boundary.sub("B", m) for m in tool_messages(on[2])],
                                 [boundary.sub("B", m) for m in tool_messages(off[2])])
                self.assertEqual((on[1].completion, on[1].flags), (off[1].completion, off[1].flags))

    def test_trace_holds_no_page_text_queries_or_secrets(self):
        for name in ("A_incomplete", "B_complete", "D_refused"):
            s, _, _, _ = run_scenario(name)
            blob = json.dumps(s.trace.as_dict(), ensure_ascii=False)
            for forbidden in ("AX-101", "AX-202", "q=", "Summary:", "Status history", "OFFSITE CONTENT",
                              "This original document", "PAGINA-NAO-CONFIAVEL", "REDACTED"):
                self.assertNotIn(forbidden, blob, (name, forbidden))

    def test_only_executed_follows_count_as_used(self):
        from rightware.agent.trace import TaskTrace

        class B:
            links = {"L1": ("u1", ""), "L2": ("u2", ""), "L3": ("u3", "")}
        t = TaskTrace()
        t.turns = [{"turn": 1, "proposals": [
            {"name": "web_follow", "status": "OK", "view": {"followed": "L1", "shown_links": ["L2"]}},
            {"name": "web_follow", "status": "FAILED", "view": {"followed": "L2"}},
            {"name": "web_follow", "status": "NOT_EXECUTED", "view": {"followed": "L3"}}]}]
        vis = t.link_visibility(B())
        self.assertEqual(vis["used"], ["L1"])
        self.assertEqual(vis["used_without_presentation"], ["L1"])
        self.assertEqual(vis["registered_not_presented"], 2)

    def test_synthetic_report_is_writable_and_hash_only(self):
        import subprocess
        import sys
        out = Path(tempfile.mkdtemp()) / "r.json"
        root = Path(__file__).resolve().parents[1]
        subprocess.run([sys.executable, "-m", "labs.work07_r3c1.scenarios", str(out)], cwd=root, check=True)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual([x["scenario"] for x in data["scenarios"]],
                         ["A_incomplete", "B_complete", "C_hidden_link", "D_refused", "E_premature"])
        self.assertIn("NOT evidence about Qwen", data["note"])


if __name__ == "__main__":
    unittest.main()
