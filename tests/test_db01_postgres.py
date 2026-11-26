"""DB01 acceptance: opt-in against a dedicated disposable TLS PostgreSQL database."""
import concurrent.futures
import os
import secrets
import unittest
import uuid

from rightware.persistence.postgres import DatabaseUnavailable, PostgresDatabase
from rightware.persistence.pg_memory import PostgresMemoryStore
from rightware.persistence.pg_knowledge import PostgresKnowledgeStore
from rightware.knowledge.ingest import Extracted, Segment


@unittest.skipUnless(os.environ.get("JARVIS_DB01_TEST") == "1", "disposable PostgreSQL acceptance required")
class DB01(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ["JARVIS_DB01_TEST_DSN"]
        instance = os.environ["JARVIS_DB01_TEST_INSTANCE"]
        if dsn == os.environ.get("JARVIS_POSTGRES_DSN") or instance == os.environ.get("JARVIS_POSTGRES_INSTANCE"):
            raise RuntimeError("test database must differ from configured runtime")
        cls.db = PostgresDatabase(dsn, instance)

    def setUp(self):
        suffix = secrets.token_hex(6)
        self.a, self.b = "lab:db01-a-" + suffix, "lab:db01-b-" + suffix
        self.m, self.k = PostgresMemoryStore(self.db), PostgresKnowledgeStore(self.db)
        self.addCleanup(self.clean)

    def clean(self):
        for owner in (self.a, self.b):
            for row in self.m.active(owner):
                self.m.delete(owner, row.id)
            for doc in self.k.list(owner):
                self.k.delete(owner, doc.id)

    def test_memory_roundtrip_isolation_and_recursive_deletion(self):
        first, _ = self.m.add(self.a, "preferencia", "moeda", "Meticais e dólares", {"test": True})
        second, replaced = self.m.add(self.a, "preferencia", "moeda", "Meticais", {})
        self.assertEqual(replaced, [first.id])
        third, _ = self.m.add(self.a, "preferencia", "moeda", "Dólares", {})
        self.assertIsNone(self.m.get(self.b, third.id))
        self.assertIsNone(self.m.update(self.b, third.id, "Not allowed", {}))
        self.assertFalse(self.m.delete(self.b, third.id))
        updated = self.m.update(self.a, third.id, "Meticais e dólares", {"correction": True})
        self.assertEqual(updated.content, "Meticais e dólares")
        again = PostgresMemoryStore(PostgresDatabase(os.environ["JARVIS_DB01_TEST_DSN"], self.db.instance_id))
        self.assertEqual([row.id for row in again.active(self.a)], [third.id])
        self.assertTrue(again.delete(self.a, third.id))
        for mid in (first.id, second.id, third.id):
            self.assertIsNone(again.get(self.a, mid))

    def test_rls_direct_queries_and_cross_owner_write(self):
        mem, _ = self.m.add(self.a, "facto", "teste", "synthetic", {})
        with self.db.transaction() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM jarvis.memories").fetchone()[0], 0)
        with self.db.transaction(self.b) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM jarvis.memories WHERE id=%s", (mem.id,)).fetchone()[0], 0)
        with self.assertRaises(DatabaseUnavailable):
            with self.db.transaction(self.b, write=True) as con:
                con.execute("INSERT INTO jarvis.memory_events VALUES (0,%s,%s,'created')", (self.a, mem.id))
        self.assertIsNotNone(self.m.get(self.a, mem.id))

    def test_documents_dedup_search_locator_and_delete(self):
        ex = Extracted("synthetic.txt", "txt", "a" * 64, 100, 2,
                       [Segment(0, "página 2", "O resultado líquido foi 96 milhões de meticais.")])
        doc, created = self.k.add(self.a, ex, False)
        self.assertTrue(created)
        self.assertEqual(self.k.add(self.a, ex, False)[0].id, doc.id)
        self.assertFalse(self.k.add(self.a, ex, False)[1])
        self.assertNotEqual(self.k.add(self.b, ex, False)[0].id, doc.id)
        self.assertIsNone(self.k.get(self.b, doc.id))
        self.assertFalse(self.k.delete(self.b, doc.id))
        self.assertEqual(self.k.segments(self.b, doc.id), [])
        self.assertEqual(self.k.by_locator(self.a, doc.id, "página 2")[0].doc_id, doc.id)
        self.assertEqual(self.k.search(self.a, "resultado liquido 96", [doc.id])[0].doc_id, doc.id)
        self.assertEqual(self.k.search(self.b, "resultado liquido 96", [doc.id]), [])
        self.assertTrue(self.k.delete(self.a, doc.id))
        self.assertEqual(self.k.search(self.a, "resultado liquido 96"), [])

    def test_same_owner_concurrent_supersession(self):
        def add(i):
            return self.m.add(self.a, "preferencia", "moeda", str(i), {})[0].id
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(add, range(4)))
        active = self.m.active(self.a)
        self.assertEqual(len(active), 1)
        self.assertIn(active[0].id, ids)
        self.assertTrue(self.m.delete(self.a, active[0].id))
        self.assertTrue(all(self.m.get(self.a, mid) is None for mid in ids))

    def test_wrong_instance_refused(self):
        with self.assertRaises(DatabaseUnavailable):
            PostgresDatabase(os.environ["JARVIS_DB01_TEST_DSN"], str(uuid.uuid4()))


    def test_migration_readback_duplicate_and_transaction_rollback(self):
        from rightware.persistence.migrate import import_snapshot
        # Two owners, one real synthetic source snapshot with old-format IDs.
        # Random legacy IDs avoid collisions across disposable runs.
        first, second = "m-" + secrets.token_hex(4), "m-" + secrets.token_hex(4)
        did = "d-" + secrets.token_hex(4)
        data = {
            "memories": [(first, self.a, "preferencia", "moeda", "Meticais", {"source": "test"}, 1.0, 2.0, "superseded", second),
                         (second, self.a, "preferencia", "moeda", "Meticais e dólares", {"source": "test"}, 2.0, 2.0, "confirmed", None)],
            "memory_events": [(1.0, self.a, first, "created"), (2.0, self.a, second, "created")],
            "documents": [(did, self.b, "test.txt", "txt", "a"*64, 10, 1, 1, 3.0, False)],
            "segments": [(did, self.b, 0, "página 2", "Resultado líquido 96")],
            "document_events": [(3.0, self.b, did, "uploaded")],
        }
        # Force a read-back mismatch AFTER inserts to exercise actual rollback.
        from unittest.mock import patch
        with patch("rightware.persistence.migrate.fingerprint", side_effect=[b"a", b"b"]):
            with self.assertRaises(ValueError):
                import_snapshot(self.db, data)
        self.assertEqual(self.m.active(self.a), [])
        self.assertEqual(self.m.events(self.a), [])
        self.assertEqual(self.k.list(self.b), [])
        result = import_snapshot(self.db, data)
        self.assertTrue(result["committed"] and result["verified"])
        self.assertEqual(self.m.get(self.a, second).content, "Meticais e dólares")
        self.assertEqual(self.m.get(self.a, first).superseded_by, second)
        self.assertEqual(self.k.search(self.b, "resultado liquido 96")[0].doc_id, did)
        self.assertEqual(self.k.search(self.a, "resultado liquido 96"), [])
        with self.assertRaises(ValueError):
            import_snapshot(self.db, data)
        self.assertEqual(len(self.m.active(self.a)), 1)
        self.assertEqual(len(self.k.list(self.b)), 1)


if __name__ == "__main__":
    unittest.main()
