"""LIVE02 stdlib recovery tests: synthetic SQLite only; no model, tunnel or personal data."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rightware.gui.recovery import absolute_expiry, state_files, FILES, TABLES, model_present


class DeadlineTests(unittest.TestCase):
    def test_restart_does_not_extend(self):
        self.assertEqual(absolute_expiry(59, 4500, now=1000), 4500)
        self.assertEqual(absolute_expiry(59, 4500, now=4400), 4500)
        self.assertEqual(absolute_expiry(10, 4500, now=1000), 1600)

    def test_refuses_expired_and_excessive(self):
        for deadline in (999, 1000, 4601, float("nan"), float("inf")):
            with self.subTest(deadline=deadline), self.assertRaises(ValueError):
                absolute_expiry(59, deadline, now=1000)
        for minutes in (0, 61, float("nan")):
            with self.assertRaises(ValueError):
                absolute_expiry(minutes, now=1000)


@unittest.skipUnless(hasattr(os, "getuid"), "Linux cloud permissions")
class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for kind, filename in FILES.items():
            path = self.root / filename
            with sqlite3.connect(path) as con:
                for table in TABLES[kind]:
                    con.execute(f"CREATE TABLE {table} (value TEXT)")
            path.chmod(0o600)

    def test_existing_stores_are_reused(self):
        self.assertEqual(state_files(self.root)["memory"], self.root / FILES["memory"])

    def test_missing_db_does_not_create_empty_replacement(self):
        path = self.root / FILES["memory"]
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            state_files(self.root)
        self.assertFalse(path.exists())

    def test_corrupt_and_wrong_schema_fail(self):
        path = self.root / FILES["memory"]
        path.write_bytes(b"not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            state_files(self.root)
        path.unlink()
        with sqlite3.connect(path) as con:
            con.execute("CREATE TABLE unrelated (value TEXT)")
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            state_files(self.root)

    def test_permissions_and_symlink_refused(self):
        path = self.root / FILES["memory"]
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            state_files(self.root)
        path.chmod(0o600)
        path.rename(self.root / "other.sqlite3")
        path.symlink_to(self.root / "other.sqlite3")
        with self.assertRaises(ValueError):
            state_files(self.root)

    def test_sidecar_symlink_refused(self):
        path = self.root / FILES["memory"]
        Path(str(path) + "-wal").symlink_to(self.root / FILES["documents"])
        with self.assertRaises(ValueError):
            state_files(self.root)

    def test_directory_permissions(self):
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            state_files(self.root)


class OllamaTests(unittest.TestCase):
    def test_presence_is_not_inference(self):
        with patch("urllib.request.build_opener") as builder:
            response = builder.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'{"models":[{"name":"qwen3.5:2b"}]}'
            self.assertTrue(model_present("qwen3.5:2b"))
            self.assertFalse(model_present("other:2b"))
            builder.return_value.open.assert_called_with("http://127.0.0.1:11434/api/tags", timeout=5)


if __name__ == "__main__":
    unittest.main()
