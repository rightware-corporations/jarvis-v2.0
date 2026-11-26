"""PostgreSQL implementation of the M01 store contract; caller supplies authenticated owner."""
from __future__ import annotations

import secrets
import time

from rightware.memory.store import CATEGORIES, MAX_CONTENT, MAX_PER_OWNER, Memory

COLS = "id,owner,category,topic,content,provenance,created_at,updated_at,status,superseded_by"


class PostgresMemoryStore:
    def __init__(self, database, clock=time.time):
        self.db, self.clock = database, clock

    @staticmethod
    def _event(c, owner, mid, action, now):
        c.execute("INSERT INTO jarvis.memory_events(at,owner,memory_id,action) VALUES (%s,%s,%s,%s)",
                  (now, owner, mid, action))

    def add(self, owner, category, topic, content, provenance):
        from psycopg.types.json import Jsonb
        if category not in CATEGORIES:
            raise ValueError("categoria inválida")
        content = " ".join(str(content).split())[:MAX_CONTENT]
        topic = " ".join(str(topic).lower().split())[:80]
        if not content or not topic:
            raise ValueError("conteúdo ou tópico vazio")
        now, mid = self.clock(), "m-" + secrets.token_hex(16)
        with self.db.transaction(owner, write=True) as c:
            old = [r[0] for r in c.execute(
                "SELECT id FROM jarvis.memories WHERE owner=%s AND category=%s AND topic=%s AND status='confirmed'",
                (owner, category, topic))]
            n = c.execute("SELECT count(*) FROM jarvis.memories WHERE owner=%s AND status='confirmed'", (owner,)).fetchone()[0]
            if n >= MAX_PER_OWNER and not old:
                raise ValueError("limite de memórias atingido")
            for previous in old:
                c.execute("UPDATE jarvis.memories SET status='superseded',superseded_by=%s,updated_at=%s WHERE owner=%s AND id=%s",
                          (mid, now, owner, previous))
                self._event(c, owner, previous, "superseded", now)
            row = c.execute(
                "INSERT INTO jarvis.memories (" + COLS + ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',NULL) RETURNING " + COLS,
                (mid, owner, category, topic, content, Jsonb(provenance), now, now)).fetchone()
            self._event(c, owner, mid, "created", now)
            result = Memory(*row)
        return result, old

    def update(self, owner, mid, content, provenance):
        from psycopg.types.json import Jsonb
        content = " ".join(str(content).split())[:MAX_CONTENT]
        if not content:
            raise ValueError("conteúdo vazio")
        now = self.clock()
        with self.db.transaction(owner, write=True) as c:
            row = c.execute("SELECT provenance FROM jarvis.memories WHERE owner=%s AND id=%s AND status='confirmed'",
                            (owner, mid)).fetchone()
            if row is None:
                return None
            prov = row[0]
            prov.setdefault("corrections", []).append(provenance)
            result = c.execute(
                "UPDATE jarvis.memories SET content=%s,provenance=%s,updated_at=%s WHERE owner=%s AND id=%s RETURNING " + COLS,
                (content, Jsonb(prov), now, owner, mid)).fetchone()
            self._event(c, owner, mid, "corrected", now)
            return Memory(*result)

    def delete(self, owner, mid):
        with self.db.transaction(owner, write=True) as c:
            # Traverse the whole supersession chain, not just the immediately previous version.
            n = c.execute(
                "WITH RECURSIVE chain(id) AS (SELECT id FROM jarvis.memories WHERE owner=%s AND id=%s "
                "UNION SELECT m.id FROM jarvis.memories m JOIN chain c ON m.superseded_by=c.id WHERE m.owner=%s) "
                "DELETE FROM jarvis.memories WHERE owner=%s AND id IN (SELECT id FROM chain)",
                (owner, mid, owner, owner)).rowcount
            if n:
                self._event(c, owner, mid, "deleted", self.clock())
            return n > 0

    def get(self, owner, mid):
        with self.db.transaction(owner) as c:
            row = c.execute("SELECT " + COLS + " FROM jarvis.memories WHERE owner=%s AND id=%s", (owner, mid)).fetchone()
            return Memory(*row) if row else None

    def active(self, owner):
        with self.db.transaction(owner) as c:
            return [Memory(*row) for row in c.execute(
                "SELECT " + COLS + " FROM jarvis.memories WHERE owner=%s AND status='confirmed' ORDER BY updated_at DESC,id",
                (owner,))]

    def events(self, owner):
        with self.db.transaction(owner) as c:
            return c.execute("SELECT at,memory_id,action FROM jarvis.memory_events WHERE owner=%s ORDER BY at",
                             (owner,)).fetchall()
