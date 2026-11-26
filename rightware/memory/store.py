"""SQLite store for personal memory. Stdlib only; one file under ``.runtime/memory`` (never committed).

Statuses: ``confirmed`` (recalled), ``pending`` (reserved for future suggested learning; never recalled),
``superseded`` (replaced by a newer memory on the same topic; kept with provenance, never recalled).
Deletion removes the row (content gone); ``memory_events`` keeps only id/owner/action/time.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / ".runtime" / "memory" / "jarvis-memory.sqlite3"
CATEGORIES = ("preferencia", "facto", "objectivo", "contexto")
MAX_CONTENT = 400
MAX_PER_OWNER = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  category TEXT NOT NULL,
  topic TEXT NOT NULL,
  content TEXT NOT NULL,
  provenance TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  status TEXT NOT NULL,
  superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_mem_owner ON memories(owner, status);
CREATE TABLE IF NOT EXISTS memory_events (
  at REAL NOT NULL, owner TEXT NOT NULL, memory_id TEXT NOT NULL, action TEXT NOT NULL
);
"""


@dataclasses.dataclass
class Memory:
    id: str
    owner: str
    category: str
    topic: str
    content: str
    provenance: dict
    created_at: float
    updated_at: float
    status: str
    superseded_by: str | None = None


class MemoryStore:
    def __init__(self, path: Path | str = DEFAULT_PATH, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lock = threading.Lock()
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
    def _row(r) -> Memory:
        return Memory(r[0], r[1], r[2], r[3], r[4], json.loads(r[5]), r[6], r[7], r[8], r[9])

    # -- writes (each returns what was REALLY committed) -----------------------------------------------------------
    def add(self, owner: str, category: str, topic: str, content: str, provenance: dict) -> tuple[Memory, list[str]]:
        """Insert a confirmed memory; confirmed memories of the same owner/category/topic become superseded.
        Returns (new memory, ids superseded)."""
        if category not in CATEGORIES:
            raise ValueError("categoria inválida")
        content = " ".join(str(content).split())[:MAX_CONTENT]
        topic = " ".join(str(topic).lower().split())[:80]
        if not content or not topic:
            raise ValueError("conteúdo ou tópico vazio")
        now = self._clock()
        mid = "m-" + secrets.token_hex(4)
        with self._lock, self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            n = c.execute("SELECT COUNT(*) FROM memories WHERE owner=? AND status='confirmed'", (owner,)).fetchone()[0]
            if n >= MAX_PER_OWNER:
                c.execute("ROLLBACK")
                raise ValueError("limite de memórias atingido")
            old = [r[0] for r in c.execute("SELECT id FROM memories WHERE owner=? AND category=? AND topic=? AND "
                                           "status='confirmed'", (owner, category, topic))]
            c.execute("INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                      (mid, owner, category, topic, content, json.dumps(provenance, ensure_ascii=False), now, now,
                       "confirmed"))
            for o in old:
                c.execute("UPDATE memories SET status='superseded', superseded_by=?, updated_at=? WHERE id=?",
                          (mid, now, o))
                c.execute("INSERT INTO memory_events VALUES (?,?,?,?)", (now, owner, o, "superseded"))
            c.execute("INSERT INTO memory_events VALUES (?,?,?,?)", (now, owner, mid, "created"))
            c.execute("COMMIT")
        return self.get(owner, mid), old

    def update(self, owner: str, mid: str, content: str, provenance: dict) -> Memory | None:
        """Correct a memory of THIS owner in place (provenance history appended). None if not found."""
        content = " ".join(str(content).split())[:MAX_CONTENT]
        if not content:
            raise ValueError("conteúdo vazio")
        now = self._clock()
        with self._lock, self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            r = c.execute("SELECT provenance FROM memories WHERE owner=? AND id=? AND status='confirmed'",
                          (owner, mid)).fetchone()
            if r is None:
                c.execute("ROLLBACK")
                return None
            prov = json.loads(r[0])
            prov.setdefault("corrections", []).append(provenance)
            c.execute("UPDATE memories SET content=?, provenance=?, updated_at=? WHERE id=?",
                      (content, json.dumps(prov, ensure_ascii=False), now, mid))
            c.execute("INSERT INTO memory_events VALUES (?,?,?,?)", (now, owner, mid, "corrected"))
            c.execute("COMMIT")
        return self.get(owner, mid)

    def delete(self, owner: str, mid: str) -> bool:
        """Remove the memory (and any superseded versions it replaced) of THIS owner. True if a row was deleted."""
        now = self._clock()
        with self._lock, self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            n = c.execute("DELETE FROM memories WHERE owner=? AND (id=? OR superseded_by=?)", (owner, mid, mid)).rowcount
            if n:
                c.execute("INSERT INTO memory_events VALUES (?,?,?,?)", (now, owner, mid, "deleted"))
            c.execute("COMMIT")
        return n > 0

    # -- reads --------------------------------------------------------------------------------------------------
    def get(self, owner: str, mid: str) -> Memory | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM memories WHERE owner=? AND id=?", (owner, mid)).fetchone()
        return self._row(r) if r else None

    def active(self, owner: str) -> list[Memory]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM memories WHERE owner=? AND status='confirmed' ORDER BY updated_at DESC",
                             (owner,)).fetchall()
        return [self._row(r) for r in rows]

    def events(self, owner: str) -> list[tuple]:
        with self._conn() as c:
            return c.execute("SELECT at, memory_id, action FROM memory_events WHERE owner=? ORDER BY at",
                             (owner,)).fetchall()
