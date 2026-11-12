"""WORK-07 R2 deterministic regression: real-run shape, source integrity and audit.

Does not contact RFC Editor or run Qwen. Test inputs are synthetic examples
derived from the approved WORK-07 run's externally visible failure mode.
"""
import unittest

from labs.work07_rfc_gate import evaluator as E
from labs.work07_rfc_gate import gate as G


REAL_SHAPE = (
    "Com base nas informações das RFC 9110 e RFC 9112, segue a análise:\n\n"
    "**RFC 9110 - Define a Semântica do HTTP:**\n"
    "* **Título Oficial:** \"HTTP Semantics\"\n"
    "* **Descrição:** Define a semântica do HTTP.\n"
    "* **Link da Fonte:** https://www.rfc-editor.org/info/rfc9110/\n\n"
    "**RFC 9112 - Define o HTTP/1.1:**\n"
    "* **Título Oficial:** \"HTTP/1.1\"\n"
    "* **Descrição:** Define a sintaxe das mensagens HTTP/1.1.\n"
    "* **Link da Fonte:** https://www.rfc-editor.org/info/rfc9112/\n"
)


class MarkdownSections(unittest.TestCase):
    def test_markdown_headings_preserve_title_and_purpose_attribution(self):
        problems = E.answer_rubric(REAL_SHAPE)
        self.assertNotIn("official title of RFC 9110 missing or not paired with it", problems)
        self.assertNotIn("official title of RFC 9112 missing or not paired with it", problems)
        self.assertNotIn("purpose of RFC 9110 missing or not paired with it", problems)
        self.assertNotIn("purpose of RFC 9112 missing or not paired with it", problems)
        self.assertIn("official URL of RFC 9110 not attributed in the answer", problems)
        self.assertIn("official URL of RFC 9112 not attributed in the answer", problems)

    def test_swapped_section_titles_still_fail(self):
        swapped = ("**RFC 9110:**\n* **Título Oficial:** \"HTTP/1.1\"\n"
                   "* Descrição: define a semântica do HTTP.\n"
                   "**RFC 9112:**\n* **Título Oficial:** \"HTTP Semantics\"\n"
                   "* Descrição: define a sintaxe das mensagens HTTP/1.1.\n")
        problems = E.answer_rubric(swapped)
        self.assertIn("official title of RFC 9110 missing or not paired with it", problems)
        self.assertIn("official title of RFC 9112 missing or not paired with it", problems)

    def test_unrelated_heading_ends_previous_attribution(self):
        answer = ("**RFC 9110**\n* Semântica do HTTP\n\n"
                  "**Outros assuntos:**\n* HTTP Semantics\n"
                  "**RFC 9112**\n* HTTP/1.1\n")
        self.assertIn("official title of RFC 9110 missing or not paired with it",
                      E.answer_rubric(answer))

    def test_info_pages_do_not_count_as_canonical_documents(self):
        events = [
            {"op": "open", "outcome": "OK", "status": 200,
             "final_url": "https://www.rfc-editor.org/info/rfc9110/"},
            {"op": "follow", "outcome": "OK", "status": 200,
             "final_url": "https://www.rfc-editor.org/info/rfc9112/"}
        ]
        responses = [
            {"tool_calls": [{"name": "web_type"}, {"name": "web_submit"}, {"name": "web_follow"}]}
        ]
        result = E.evaluate(
            engine_id="ollama", model_digest="a", expected_digest="a",
            responses=responses, events=events,
            reply={"completion": "ANSWERED_WITH_SOURCES", "flags": [], "halted": None},
            answer=REAL_SHAPE, max_tool_calls=14
        )
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("RFC 9110 was not actually opened", result["reasons"])
        self.assertIn("RFC 9112 was not actually opened", result["reasons"])


class AuditReconciliation(unittest.TestCase):
    def test_authorized_without_execution_is_visible_in_diagnostics(self):
        good = {"tool": "web_type", "args": {"field": "F1"}}
        orphan = {"tool": "web_open", "args": {"url": {"host": "example.org", "sha256": "abc"}}}
        entries = [
            {**good, "allowed": True},
            {**good, "allowed": True, "outcome": "OK"},
            {**orphan, "allowed": True},
            {**orphan, "allowed": False, "reason": "quota"},
        ]
        summary = G.reconcile_tool_audit(entries)
        self.assertEqual(summary["approved_without_outcome"], 1)
        self.assertEqual(summary["pending_tool_names"], ["web_open"])
        self.assertEqual(summary["outcome_without_approval"], 0)
        self.assertEqual(summary["audit_entries"], 4)

    def test_repeated_calls_pair_by_arguments_and_never_log_values(self):
        a = {"tool": "web_follow", "args": {"link": "L1"}, "allowed": True}
        b = {"tool": "web_follow", "args": {"link": "L2"}, "allowed": True}
        summary = G.reconcile_tool_audit([
            a, b, {**b, "outcome": "OK"}, {**a, "outcome": "OK"}
        ])
        self.assertEqual(summary["approved_without_outcome"], 0)
        self.assertEqual(summary["pending_tool_names"], [])
        self.assertEqual(summary["outcome_without_approval"], 0)

    def test_unexpected_outcome_and_corrupt_audit_are_reported(self):
        import tempfile
        from pathlib import Path
        event = {"tool": "web_open", "args": {"url": {"host": "x.example"}}, "allowed": True,
                 "outcome": "OK"}
        self.assertEqual(G.reconcile_tool_audit([event])["outcome_without_approval"], 1)
        path = Path(tempfile.mkdtemp()) / "audit.jsonl"
        self.assertEqual(G.read_tool_audit(path)["status"], "UNREADABLE")
        path.write_text("invalid-json", encoding="utf-8")
        self.assertEqual(G.read_tool_audit(path)["status"], "UNREADABLE")


class FixedPlanAndProduct(unittest.TestCase):
    def test_approved_plan_hashes_stay_exact(self):
        self.assertEqual(G.plan_sha256("qwen"),
                         "44d9664812cd98648f17691508f4adf9710463ef20354b09ed4d12e144a02d94")
        self.assertEqual(G.plan_sha256("site-preflight"),
                         "b0e4ac7849b7ad14d19ca4c61da7f0929fa1ef351c5b0a5f633419eba6178ef4")

    def test_product_research_guidance_is_generic_without_answers(self):
        try:
            from rightware.agent import session as S
        except ImportError:
            self.skipTest("pinned OpenJarvis venv required")
        prompt = S.BROWSE_PROMPT.lower()
        for token in ("web_follow", "web_find", "documento", "fonte primária"):
            self.assertIn(token, prompt)
        for oracle in ("rfc 9110", "rfc 9112", "http semantics", "rfc-editor"):
            self.assertNotIn(oracle, prompt)


if __name__ == "__main__":
    unittest.main()
