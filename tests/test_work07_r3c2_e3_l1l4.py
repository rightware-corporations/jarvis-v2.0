"""WORK-07 R3-C2-014: 27 deterministic LAB contract tests (FAKE, no model).

E3 scenarios exercise manually supplied trusted objective contracts, NOT NLP extraction.
L1-L4 scenarios exercise SYNTHETIC receipt logic, NOT AgentSession integration.
These tests must not be cited as proof of real Qwen behaviour or production completion.
"""
import unittest
from dataclasses import replace
from labs.work07_r3c2.contracts_e3_l1l4 import (
    Objective as O, Contract as C, assess, protect_trusted, receipt as R,
)


class E3_TrustedContractOracle(unittest.TestCase):
    def test_e3_01_two_originals_have_separate_find_open_cite_requirements(self):
        os = tuple(O(f"{v}-{t}", v, t) for t in ("A", "B") for v in ("locate", "open_original", "cite"))
        c = C(os)
        self.assertEqual(len([o for o in c.objectives if o.mandatory]), 6)
        self.assertIn("open_original-B", assess(c, [R(o.oid, o.verb, o.target) for o in os if o.target == "A"]).missing)

    def test_e3_02_optional_b_is_not_mandatory(self):
        c = C((O("A", "read", "A"), O("B", "read", "B", mandatory=False)))
        self.assertEqual(assess(c, [R("A", "read", "A")]).verdict, "PASS_OPERATIONAL_ONLY")

    def test_e3_03_send_is_forbidden_not_positive_objective(self):
        c = C((O("S", "search", "A"),), forbidden=frozenset({"send_message"}))
        self.assertIn("send_message", c.forbidden)
        self.assertTrue(all(o.verb != "send_message" for o in c.objectives))

    def test_e3_04_order_dependency_retained(self):
        c = C((O("READ", "read", "A"), O("SUMMARY", "summarize", "B", after="READ")))
        self.assertEqual(c.objectives[1].after, "READ")
        self.assertEqual(assess(c, [R("SUMMARY", "summarize", "B")]).missing, ("READ",))

    def test_e3_05_unspecified_document_and_version_are_ambiguous(self):
        c = C((O("OPEN", "read", "?"),), ambiguity=("document_identity", "expected_version"))
        self.assertEqual(assess(c, []).verdict, "UNKNOWN")

    def test_e3_06_repeated_action_not_silently_deduplicated(self):
        c = C((O("FIRST", "read", "A"), O("SECOND", "read", "A", after="FIRST")))
        self.assertEqual(assess(c, [R("FIRST", "read", "A")]).missing, ("SECOND",))

    def test_e3_07_three_named_artifacts_retained(self):
        c = C(tuple(O(t, "locate", t) for t in ("A", "B", "C")))
        self.assertEqual(assess(c, [R("A", "locate", "A"), R("B", "locate", "B")]).missing, ("C",))

    def test_e3_08_conditional_b_is_not_unconditional(self):
        c = C((O("A", "summarize", "A"), O("B", "cite", "B", mandatory=False, condition="exists(B)")))
        self.assertEqual(c.objectives[1].condition, "exists(B)")
        self.assertEqual(assess(c, [R("A", "summarize", "A")]).verdict, "PASS_OPERATIONAL_ONLY")

    def test_e3_09_untrusted_proposal_cannot_downgrade_open_to_locate(self):
        c = C((O("A", "open_original", "A"),))
        merged = protect_trusted(c, (O("A", "locate", "A", mandatory=False),))
        self.assertEqual(merged.objectives, c.objectives)
        self.assertEqual(assess(merged, [R("A", "locate", "A")]).verdict, "INCOMPLETE")

    def test_e3_10_empty_contract_cannot_pass(self):
        self.assertEqual(assess(C(()), []).verdict, "UNKNOWN")

    def test_e3_11_unapproved_mirror_is_forbidden(self):
        c = C((O("A", "read", "approved-source"),),
              forbidden=frozenset({"use_mirror", "use_unapproved_source"}),
              ambiguity=("approved_source_identity",))
        self.assertEqual(assess(c, []).verdict, "UNKNOWN")
        self.assertIn("use_mirror", c.forbidden)

    def test_e3_12_explanation_not_substitute_for_read_receipt(self):
        c = C((O("READ", "read", "A"), O("EXPLAIN", "explain", "A")))
        self.assertEqual(assess(c, [R("EXPLAIN", "explain", "A")]).missing, ("READ",))


class L1_OperationalCompleteness(unittest.TestCase):
    def test_l1_01_two_required_one_receipt_is_incomplete(self):
        c = C((O("A", "read", "A"), O("B", "read", "B")))
        self.assertEqual(assess(c, [R("A", "read", "A")]).missing, ("B",))

    def test_l1_02_both_valid_synthetic_receipts_pass_operational_only(self):
        c = C((O("A", "read", "A"), O("B", "read", "B")))
        self.assertEqual(assess(c, [R("A", "read", "A"), R("B", "read", "B")]).verdict,
                         "PASS_OPERATIONAL_ONLY")

    def test_l1_03_model_claim_without_receipt_incomplete(self):
        self.assertEqual(assess(C((O("A", "read", "A"),)), []).verdict, "INCOMPLETE")


class L2_DocumentIdentity(unittest.TestCase):
    def test_l2_01_landing_title_matches_but_original_content_absent(self):
        c = C((O("A", "open_original", "A"),))
        self.assertEqual(assess(c, [R("A", "open_original", "A", identity="landing")]).verdict,
                         "INCOMPLETE")

    def test_l2_02_original_url_returns_404(self):
        c = C((O("A", "read", "A"),))
        self.assertEqual(assess(c, [R("A", "read", "A", status="HTTP_ERROR")]).verdict,
                         "INCOMPLETE")

    def test_l2_03_http_200_challenge_content_not_proof(self):
        c = C((O("A", "read", "A"),))
        self.assertEqual(assess(c, [R("A", "read", "A", content_signal="challenge")]).verdict,
                         "INCOMPLETE")

    def test_l2_04_equivalent_redirect_with_content_identity(self):
        c = C((O("A", "read", "A"),))
        self.assertEqual(assess(c, [R("A", "read", "A", content_hash="h123")],
                                known_hashes={"A": ("h123", "page")}).verdict, "PASS_OPERATIONAL_ONLY")

    def test_l2_05_same_host_mirror_without_identity_not_proof(self):
        c = C((O("A", "read", "A"),))
        self.assertEqual(assess(c, [R("A", "read", "A", identity=None)]).verdict, "INCOMPLETE")


class L3_ExecutionProvenance(unittest.TestCase):
    def test_l3_01_refused_or_not_executed_not_proof(self):
        c = C((O("A", "read", "A"),))
        for status in ("REFUSED", "NOT_EXECUTED"):
            with self.subTest(status=status):
                self.assertEqual(assess(c, [R("A", "read", "A", status=status)]).verdict,
                                 "INCOMPLETE")

    def test_l3_02_memory_says_done_but_no_outcome(self):
        self.assertEqual(assess(C((O("A", "read", "A"),)), []).missing, ("A",))

    def test_l3_03_fabricated_outcome_id_not_proof(self):
        c = C((O("A", "read", "A"),))
        self.assertEqual(assess(c, [R("A", "read", "A", outcome_id="", executed=False)]).verdict,
                         "INCOMPLETE")


class L4_RunAndVersionBinding(unittest.TestCase):
    def test_l4_01_other_run_or_task_rejected(self):
        c = C((O("A", "read", "A"),))
        for changes in ({"run_id": "foreign"}, {"task_id": "foreign"}):
            with self.subTest(changes=changes):
                self.assertEqual(assess(c, [R("A", "read", "A", **changes)]).verdict, "INCOMPLETE")

    def test_l4_02_page_hash_different_from_view_hash(self):
        c = C((O("A", "read", "A"),))
        self.assertEqual(assess(c, [R("A", "read", "A", content_hash="h123", hash_scope="view")],
                                known_hashes={"A": ("h123", "page")}).verdict, "INCOMPLETE")

    def test_l4_03_old_content_hash_needs_revalidation(self):
        c = C((O("A", "read", "A"),))
        self.assertEqual(assess(c, [R("A", "read", "A", content_hash="old")],
                                known_hashes={"A": ("new", "page")}).verdict, "INCOMPLETE")

    def test_l4_04_old_verifier_version_rejected(self):
        c = C((O("A", "read", "A"),))
        self.assertEqual(assess(c, [R("A", "read", "A", rule_version="v0")],
                                rule_version="v1").verdict, "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
