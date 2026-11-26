"""DB01-G synthetic source checks; no external DB, no personal data."""
import copy
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from rightware.persistence.migrate import validate, fingerprint, read_snapshot, report


def fixture():
    return {
        "memories": [
            ("m-00000001", "lab:a", "preferencia", "moeda", "Meticais", {"source": "test"}, 1.0, 2.0, "superseded", "m-00000002"),
            ("m-00000002", "lab:a", "preferencia", "moeda", "Meticais e dólares", {"source": "test"}, 2.0, 2.0, "confirmed", None),
        ],
        "memory_events": [(1.0, "lab:a", "m-00000001", "created"), (2.0, "lab:a", "m-00000002", "created")],
        "documents": [("d-00000001", "lab:b", "test.txt", "txt", "a"*64, 10, 1, 1, 3.0, False)],
        "segments": [("d-00000001", "lab:b", 0, "linhas 1–1", "Resultado 96")],
        "document_events": [(3.0, "lab:b", "d-00000001", "uploaded")],
    }


class ValidationTests(unittest.TestCase):
    def test_fixture(self):
        self.assertEqual(validate(fixture()), ["lab:a", "lab:b"])
        self.assertEqual(report(fixture())["rows"]["memories"], 2)

    def test_hash_order_and_duplicates(self):
        rows = fixture()["memory_events"]
        self.assertEqual(fingerprint(rows), fingerprint(list(reversed(rows))))
        self.assertNotEqual(fingerprint(rows), fingerprint(rows + rows[:1]))

    def test_cross_owner_segment_refused(self):
        rows = fixture()
        rows["segments"][0] = ("d-00000001", "lab:a", 0, "linhas 1–1", "Resultado 96")
        with self.assertRaises(ValueError):
            validate(rows)

    def test_missing_segment_refused(self):
        rows = fixture()
        rows["segments"] = []
        with self.assertRaises(ValueError):
            validate(rows)

    def test_dangling_supersession_refused(self):
        rows = fixture()
        rows["memories"].pop()
        with self.assertRaises(ValueError):
            validate(rows)

    def test_duplicate_active_topic_refused(self):
        rows = fixture()
        row = list(rows["memories"][1])
        row[0] = "m-00000003"
        rows["memories"].append(tuple(row))
        with self.assertRaises(ValueError):
            validate(rows)

    def test_wrong_owner_refused(self):
        rows = fixture()
        row = list(rows["memories"][0])
        row[1] = "lab:b"
        rows["memories"][0] = tuple(row)
        with self.assertRaises(ValueError):
            validate(rows)


@unittest.skipUnless(hasattr(os, "getuid"), "Linux cloud state")
class SnapshotTests(unittest.TestCase):
    def test_read_real_sqlite_stores(self):
        from rightware.memory.store import MemoryStore
        from rightware.knowledge.store import KnowledgeStore
        from rightware.knowledge.ingest import Extracted, Segment
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            m = MemoryStore(p / "mem.sqlite3")
            m.add("lab:a", "preferencia", "moeda", "Meticais", {"synthetic": True})
            m.add("lab:a", "preferencia", "moeda", "Dólares", {"synthetic": True})
            k = KnowledgeStore(p / "docs.sqlite3")
            k.add("lab:b", Extracted("test.txt", "txt", "a"*64, 10, 1, [Segment(0, "linhas 1–1", "Resultado 96")]), False)
            snap = read_snapshot(p)
            self.assertEqual(report(snap)["rows"]["memories"], 2)
            self.assertEqual(report(snap)["rows"]["segments"], 1)
            self.assertEqual(validate(snap), ["lab:a", "lab:b"])

    def test_missing_source_not_created(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                read_snapshot(d)
            self.assertFalse((Path(d) / "mem.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
