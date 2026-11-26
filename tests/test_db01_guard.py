import unittest

from rightware.persistence.pg_guard import EXPECTED, EXPRESSION, PRIVILEGES, grants_match, policies_match


def policies():
    return [(t, "owner_only", "PERMISSIVE", "{public}", "ALL", EXPRESSION, EXPRESSION)
            for t in EXPECTED if t != "instance"]


def grants():
    return [(t, p, p in allowed, False) for t, allowed in EXPECTED.items() for p in PRIVILEGES]


class GuardTests(unittest.TestCase):
    def test_expected(self):
        self.assertTrue(policies_match(policies()))
        self.assertTrue(grants_match(grants()))

    def test_policy_or_true(self):
        rows = policies()
        rows[0] = (*rows[0][:5], EXPRESSION + " OR true", EXPRESSION)
        self.assertFalse(policies_match(rows))

    def test_duplicate_policy(self):
        rows = policies()
        self.assertFalse(policies_match(rows + [rows[0]]))

    def test_wrong_role(self):
        rows = policies()
        rows[0] = (*rows[0][:3], "{other}", *rows[0][4:])
        self.assertFalse(policies_match(rows))

    def test_excessive_audit_grant(self):
        rows = [(t, p, True if (t, p) == ("memory_events", "DELETE") else a, g)
                for t, p, a, g in grants()]
        self.assertFalse(grants_match(rows))

    def test_grant_option(self):
        rows = [(t, p, a, True if (t, p) == ("instance", "SELECT") else g)
                for t, p, a, g in grants()]
        self.assertFalse(grants_match(rows))

    def test_missing_grant(self):
        self.assertFalse(grants_match(grants()[:-1]))


if __name__ == "__main__":
    unittest.main()
