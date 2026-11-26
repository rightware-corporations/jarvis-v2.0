"""Private document index: SQLite + FTS5 (BM25) under ``.runtime/knowledge`` (mode 0600, never committed).
Same design as the OpenJarvis SQLite/FTS5 knowledge backend (whose Rust extension is not installed here), with owner
isolation and page/line locators. Deletion removes the document row, its segments and its FTS entries."""
from __future__ import annotations

import contextlib
import dataclasses
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from rightware.knowledge.ingest import Extracted
from rightware.research.text import content_words

DEFAULT_PATH = Path(__file__).resolve().parents[2] / ".runtime" / "knowledge" / "jarvis-knowledge.sqlite3"
MAX_DOCS_PER_OWNER = 50
MAX_BYTES_PER_OWNER = 50_000_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT NOT NULL,
  size INTEGER NOT NULL, units INTEGER NOT NULL, segments INTEGER NOT NULL, created_at REAL NOT NULL,
  injection_suspected INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_doc_owner ON documents(owner);
CREATE TABLE IF NOT EXISTS segments (
  doc_id TEXT NOT NULL, owner TEXT NOT NULL, seq INTEGER NOT NULL, locator TEXT NOT NULL, text TEXT NOT NULL,
  PRIMARY KEY (doc_id, seq)
);
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
  text, doc_id UNINDEXED, owner UNINDEXED, seq UNINDEXED, tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS document_events (at REAL NOT NULL, owner TEXT NOT NULL, doc_id TEXT NOT NULL,
  action TEXT NOT NULL);
"""


@dataclasses.dataclass
class Doc:
    id: str
    owner: str
    name: str
    kind: str
    sha256: str
    size: int
    units: int
    segments: int
    created_at: float
    injection_suspected: bool


@dataclasses.dataclass
class Hit:
    doc_id: str
    doc_name: str
    seq: int
    locator: str
    text: str
    score: float


class KnowledgeStore:
    def __init__(self, path: Path | str = DEFAULT_PATH, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock, self._lock = clock, threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextlib.contextmanager
    def _conn(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            c.execute("PRAGMA journal_mode=WAL")
            yield c
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    @staticmethod
    def _doc(r) -> Doc:
        return Doc(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], bool(r[9]))

    def add(self, owner: str, ex: Extracted, injection_suspected: bool) -> tuple[Doc, bool]:
        """→ (document, created). The same content (sha256) for the same owner is not stored twice."""
        with self._lock, self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            r = c.execute("SELECT * FROM documents WHERE owner=? AND sha256=?", (owner, ex.sha256)).fetchone()
            if r:
                c.execute("ROLLBACK")
                return self._doc(r), False
            n, total = c.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM documents WHERE owner=?",
                                 (owner,)).fetchone()
            if n >= MAX_DOCS_PER_OWNER or total + ex.size > MAX_BYTES_PER_OWNER:
                c.execute("ROLLBACK")
                raise ValueError("limite de documentos deste utilizador atingido")
            did, now = "d-" + secrets.token_hex(4), self._clock()
            c.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (did, owner, ex.name, ex.kind, ex.sha256, ex.size, ex.units, len(ex.segments), now,
                       int(injection_suspected)))
            for s in ex.segments:
                c.execute("INSERT INTO segments VALUES (?,?,?,?,?)", (did, owner, s.seq, s.locator, s.text))
                c.execute("INSERT INTO segments_fts (text, doc_id, owner, seq) VALUES (?,?,?,?)",
                          (s.text, did, owner, s.seq))
            c.execute("INSERT INTO document_events VALUES (?,?,?,?)", (now, owner, did, "uploaded"))
            c.execute("COMMIT")
        return self.get(owner, did), True

    def get(self, owner: str, did: str) -> Doc | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM documents WHERE owner=? AND id=?", (owner, did)).fetchone()
        return self._doc(r) if r else None

    def list(self, owner: str) -> list[Doc]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM documents WHERE owner=? ORDER BY created_at", (owner,)).fetchall()
        return [self._doc(r) for r in rows]

    def delete(self, owner: str, did: str) -> bool:
        with self._lock, self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            n = c.execute("DELETE FROM documents WHERE owner=? AND id=?", (owner, did)).rowcount
            if n:
                c.execute("DELETE FROM segments WHERE owner=? AND doc_id=?", (owner, did))
                c.execute("DELETE FROM segments_fts WHERE owner=? AND doc_id=?", (owner, did))
                c.execute("INSERT INTO document_events VALUES (?,?,?,?)", (self._clock(), owner, did, "deleted"))
            c.execute("COMMIT")
        return n > 0

    def segments(self, owner: str, did: str, first: int = 0, limit: int = 4) -> list[Hit]:
        d = self.get(owner, did)
        if d is None:
            return []
        with self._conn() as c:
            rows = c.execute("SELECT seq, locator, text FROM segments WHERE owner=? AND doc_id=? AND seq>=? "
                             "ORDER BY seq LIMIT ?", (owner, did, first, limit)).fetchall()
        return [Hit(did, d.name, r[0], r[1], r[2], 0.0) for r in rows]

    def by_locator(self, owner: str, did: str, locator_prefix: str) -> list[Hit]:
        d = self.get(owner, did)
        if d is None:
            return []
        with self._conn() as c:
            rows = c.execute("SELECT seq, locator, text FROM segments WHERE owner=? AND doc_id=? AND "
                             "(locator=? OR locator LIKE ?) ORDER BY seq", (owner, did, locator_prefix,
                                                                          locator_prefix + " (%")).fetchall()
        return [Hit(did, d.name, r[0], r[1], r[2], 0.0) for r in rows]

    def search(self, owner: str, query: str, doc_ids: list[str] | None = None, k: int = 6) -> list[Hit]:
        terms = [w for w in content_words(query) if re.fullmatch(r"[a-z0-9]+", w)]
        terms += [n for n in re.findall(r"\d[\d.,]*\d|\d", query) if len(n) >= 2]
        if not terms:
            return []
        q = " OR ".join(f'"{t}"*' if t.isalpha() else f'"{t}"' for t in dict.fromkeys(terms))
        sql = ("SELECT f.doc_id, d.name, f.seq, s.locator, s.text, bm25(segments_fts) AS sc FROM segments_fts f "
               "JOIN documents d ON d.id=f.doc_id AND d.owner=f.owner "
               "JOIN segments s ON s.doc_id=f.doc_id AND s.seq=f.seq "
               "WHERE segments_fts MATCH ? AND f.owner=?")
        args: list = [q, owner]
        if doc_ids:
            sql += " AND f.doc_id IN (" + ",".join("?" * len(doc_ids)) + ")"
            args += list(doc_ids)
        sql += " ORDER BY sc LIMIT ?"
        args.append(k)
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
        return [Hit(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]
