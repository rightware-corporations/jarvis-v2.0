"""DB01 exact schema-revision-1 permission and RLS contracts (PostgreSQL 17)."""

EXPECTED = {
    "instance": {"SELECT"},
    "memories": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "memory_events": {"SELECT", "INSERT"},
    "documents": {"SELECT", "INSERT", "DELETE"},
    "segments": {"SELECT", "INSERT", "DELETE"},
    "document_events": {"SELECT", "INSERT"},
}
PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
EXPRESSION = "(owner = NULLIF(current_setting('jarvis.owner'::text, true), ''::text))"


def policies_match(rows):
    expected = set(EXPECTED) - {"instance"}
    return (len(rows) == len(expected) and {r[0] for r in rows} == expected and
            all(r[1:] == ("owner_only", "PERMISSIVE", "{public}", "ALL", EXPRESSION, EXPRESSION)
                for r in rows))


def grants_match(rows):
    expected = {(table, privilege, privilege in allowed, False)
                for table, allowed in EXPECTED.items() for privilege in PRIVILEGES}
    return len(rows) == len(expected) and set(rows) == expected
