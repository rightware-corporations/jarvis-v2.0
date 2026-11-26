"""PostgreSQL K01 store: same public contract, owner-isolated full-text retrieval."""
from __future__ import annotations

import re
import secrets
import time

from rightware.knowledge.store import Doc, Hit, MAX_DOCS_PER_OWNER, MAX_BYTES_PER_OWNER
from rightware.research.text import content_words

COLS = "id,owner,name,kind,sha256,size,units,segments,created_at,injection_suspected"


class PostgresKnowledgeStore:
    def __init__(self, database, clock=time.time):
        self.db, self.clock = database, clock

    def add(self, owner, ex, injection_suspected):
        with self.db.transaction(owner, write=True) as c:
            row = c.execute("SELECT " + COLS + " FROM jarvis.documents WHERE owner=%s AND sha256=%s",
                            (owner, ex.sha256)).fetchone()
            if row:
                return Doc(*row), False
            n, total = c.execute("SELECT count(*),coalesce(sum(size),0) FROM jarvis.documents WHERE owner=%s",
                                 (owner,)).fetchone()
            if n >= MAX_DOCS_PER_OWNER or total + ex.size > MAX_BYTES_PER_OWNER:
                raise ValueError("limite de documentos deste utilizador atingido")
            did, now = "d-" + secrets.token_hex(16), self.clock()
            row = c.execute("INSERT INTO jarvis.documents (" + COLS + ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING " + COLS,
                            (did, owner, ex.name, ex.kind, ex.sha256, ex.size, ex.units, len(ex.segments), now,
                             bool(injection_suspected))).fetchone()
            for s in ex.segments:
                c.execute("INSERT INTO jarvis.segments(doc_id,owner,seq,locator,text) VALUES (%s,%s,%s,%s,%s)",
                          (did, owner, s.seq, s.locator, s.text))
            c.execute("INSERT INTO jarvis.document_events(at,owner,doc_id,action) VALUES (%s,%s,%s,'uploaded')",
                      (now, owner, did))
            return Doc(*row), True

    def get(self, owner, did):
        with self.db.transaction(owner) as c:
            row = c.execute("SELECT " + COLS + " FROM jarvis.documents WHERE owner=%s AND id=%s", (owner, did)).fetchone()
            return Doc(*row) if row else None

    def list(self, owner):
        with self.db.transaction(owner) as c:
            return [Doc(*r) for r in c.execute("SELECT " + COLS + " FROM jarvis.documents WHERE owner=%s ORDER BY created_at,id", (owner,))]

    def delete(self, owner, did):
        with self.db.transaction(owner, write=True) as c:
            n = c.execute("DELETE FROM jarvis.documents WHERE owner=%s AND id=%s", (owner, did)).rowcount
            if n:
                c.execute("INSERT INTO jarvis.document_events(at,owner,doc_id,action) VALUES (%s,%s,%s,'deleted')",
                          (self.clock(), owner, did))
            return n > 0

    def segments(self, owner, did, first=0, limit=4):
        with self.db.transaction(owner) as c:
            rows = c.execute("SELECT s.doc_id,d.name,s.seq,s.locator,s.text FROM jarvis.segments s "
                             "JOIN jarvis.documents d ON d.owner=s.owner AND d.id=s.doc_id "
                             "WHERE s.owner=%s AND s.doc_id=%s AND s.seq >= %s ORDER BY s.seq LIMIT %s",
                             (owner, did, first, max(0, min(limit, 50)))).fetchall()
            return [Hit(*row, 0.0) for row in rows]

    def by_locator(self, owner, did, locator_prefix):
        with self.db.transaction(owner) as c:
            rows = c.execute("SELECT s.doc_id,d.name,s.seq,s.locator,s.text FROM jarvis.segments s "
                             "JOIN jarvis.documents d ON d.owner=s.owner AND d.id=s.doc_id "
                             "WHERE s.owner=%s AND s.doc_id=%s AND (s.locator=%s OR starts_with(s.locator,%s)) ORDER BY s.seq",
                             (owner, did, locator_prefix, locator_prefix + " (")).fetchall()
            return [Hit(*row, 0.0) for row in rows]

    def search(self, owner, query, doc_ids=None, k=6):
        terms = [w for w in content_words(query) if re.fullmatch(r"[a-z0-9]+", w)]
        terms += [n for n in re.findall(r"\d+", query) if len(n) >= 2]
        terms = list(dict.fromkeys(terms))[:32]
        if not terms:
            return []
        # Each term restricted to ASCII alphanumerics; use parameterized tsquery, not raw user syntax.
        tsquery = " | ".join(w + (":*" if w.isalpha() else "") for w in terms)
        sql = ("SELECT s.doc_id,d.name,s.seq,s.locator,s.text,"
               "-ts_rank_cd(s.search_vector,q.query) AS score FROM jarvis.segments s "
               "JOIN jarvis.documents d ON d.owner=s.owner AND d.id=s.doc_id "
               "CROSS JOIN to_tsquery('pg_catalog.simple'::regconfig,%s) AS q(query) "
               "WHERE s.owner=%s AND s.search_vector @@ q.query")
        args = [tsquery, owner]
        if doc_ids:
            sql += " AND s.doc_id=ANY(%s)"
            args.append(list(doc_ids))
        sql += " ORDER BY score,s.doc_id,s.seq LIMIT %s"
        args.append(max(0, min(k, 50)))
        with self.db.transaction(owner) as c:
            return [Hit(*row) for row in c.execute(sql,args)]
