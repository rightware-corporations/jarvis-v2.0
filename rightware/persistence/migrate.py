"""DB01-G: read-only SQLite snapshot inspection and explicit single-transaction PostgreSQL import.

Operator must stop all writers on both stores and target, and retain the source securely.
Default CLI is local inspection only; no network or personal values in output.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import math
import os
import re
import sqlite3
from pathlib import Path

from rightware.gui.recovery import state_files
from rightware.memory.identity import Owner
from rightware.memory.store import CATEGORIES, MAX_PER_OWNER
from rightware.knowledge.store import MAX_DOCS_PER_OWNER, MAX_BYTES_PER_OWNER

# Explicit column lists; do not transfer SQLite FTS internals or auth/session data.
TABLES = {
    "memories": ("memory", "id,owner,category,topic,content,provenance,created_at,updated_at,status,superseded_by"),
    "memory_events": ("memory", "at,owner,memory_id,action"),
    "documents": ("documents", "id,owner,name,kind,sha256,size,units,segments,created_at,injection_suspected"),
    "segments": ("documents", "doc_id,owner,seq,locator,text"),
    "document_events": ("documents", "at,owner,doc_id,action"),
}
OWNER_INDEX = {table: cols.split(",").index("owner") for table, (_, cols) in TABLES.items()}
# This is a bounded maintenance utility, not a streaming ETL for unlimited datasets.
MAX_TOTAL_ROWS = 200_000
MAX_TOTAL_BYTES = 128 * 1024 * 1024


def _normalize(table, row):
    values = list(row)
    if table == "memories":
        values[5] = json.loads(values[5]) if isinstance(values[5], str) else values[5]
        if not isinstance(values[5], dict):
            raise ValueError("invalid memory provenance")
        values[6], values[7] = float(values[6]), float(values[7])
    elif table in ("memory_events", "document_events"):
        values[0] = float(values[0])
    elif table == "documents":
        if values[9] not in (0, 1, False, True):
            raise ValueError("invalid injection flag")
        values[8], values[9] = float(values[8]), bool(values[9])
    # JSON also rejects NaN/Infinity and provides unambiguous type/length boundaries.
    json.dumps(values, ensure_ascii=False, allow_nan=False)
    return tuple(values)


def _encoded(row):
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(rows):
    """Canonical multiset hash; preserves duplicate audit events. Never emitted to public logs."""
    return hashlib.sha256(b"".join(sorted(hashlib.sha256(_encoded(r)).digest() for r in rows))).digest()


def read_snapshot(state_dir):
    paths = state_files(state_dir)
    result = {}
    total_rows = total_bytes = 0
    with contextlib.ExitStack() as stack:
        conns = {}
        for kind, path in paths.items():
            con = stack.enter_context(contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)))
            con.execute("PRAGMA query_only=ON")
            con.execute("BEGIN")
            # Pin each read transaction; cross-file consistency requires a stopped source.
            con.execute("SELECT count(*) FROM sqlite_master").fetchone()
            conns[kind] = con
        for table, (kind, cols) in TABLES.items():
            rows = []
            for raw in conns[kind].execute(f"SELECT {cols} FROM {table}"):
                row = _normalize(table, raw)
                total_rows += 1
                total_bytes += len(_encoded(row))
                if total_rows > MAX_TOTAL_ROWS or total_bytes > MAX_TOTAL_BYTES:
                    raise ValueError("migration snapshot exceeds maintenance limits")
                rows.append(row)
            result[table] = rows
    validate(result)
    return result


def validate(rows):
    owners = set()
    for table, data in rows.items():
        for row in data:
            owner = row[OWNER_INDEX[table]]
            Owner(owner, "operator-config")
            owners.add(owner)
            _encoded(row)
    mem = {}
    topics = set()
    counts = collections.Counter()
    for row in rows["memories"]:
        mid, owner, category, topic, content, prov, created, updated, status, successor = row
        if (not isinstance(mid, str) or not re.fullmatch(r"m-(?:[a-f0-9]{8}|[a-f0-9]{32})", mid)
                or mid in mem or category not in CATEGORIES or not isinstance(topic, str)
                or not 1 <= len(topic) <= 80 or not isinstance(content, str) or not 1 <= len(content) <= 400
                or not isinstance(prov, dict) or status not in ("confirmed", "pending", "superseded")
                or not math.isfinite(created) or not math.isfinite(updated)):
            raise ValueError("invalid memory row")
        mem[mid] = row
        if status == "confirmed":
            key = (owner, category, topic)
            if key in topics:
                raise ValueError("duplicate active memory topic")
            topics.add(key)
            counts[owner] += 1
    if any(n > MAX_PER_OWNER for n in counts.values()):
        raise ValueError("memory quota exceeded")
    # Historical SQLite delete can leave a dangling predecessor. Refuse rather than silently resurrect it.
    for row in mem.values():
        mid, owner, _, _, _, _, _, _, status, successor = row
        if status != "superseded":
            if successor is not None:
                raise ValueError("invalid active successor")
            continue
        seen = {mid}
        while successor is not None:
            next_row = mem.get(successor)
            if next_row is None or next_row[1] != owner or successor in seen:
                raise ValueError("invalid memory supersession chain")
            seen.add(successor)
            if next_row[8] != "superseded":
                break
            successor = next_row[9]
        else:
            raise ValueError("superseded memory has no active successor")
    docs, hashes = {}, set()
    quotas = collections.defaultdict(lambda: [0, 0])
    for row in rows["documents"]:
        did, owner, name, kind, digest, size, units, segments, created, flag = row
        if (not isinstance(did, str) or not re.fullmatch(r"d-(?:[a-f0-9]{8}|[a-f0-9]{32})", did)
                or did in docs or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or (owner, digest) in hashes or not isinstance(size, int) or size < 0
                or not isinstance(segments, int) or segments < 0 or not isinstance(units, int) or units < 0):
            raise ValueError("invalid document row")
        docs[did] = row
        hashes.add((owner, digest))
        quotas[owner][0] += 1
        quotas[owner][1] += size
    if any(n > MAX_DOCS_PER_OWNER or b > MAX_BYTES_PER_OWNER for n, b in quotas.values()):
        raise ValueError("document quota exceeded")
    counts = collections.Counter()
    keys = set()
    for did, owner, seq, locator, text in rows["segments"]:
        if (did not in docs or docs[did][1] != owner or (did, seq) in keys
                or not isinstance(seq, int) or seq < 0 or not isinstance(locator, str) or not isinstance(text, str)):
            raise ValueError("invalid document segment")
        counts[did] += 1
        keys.add((did, seq))
    if any(counts[did] != row[7] for did, row in docs.items()):
        raise ValueError("document segment count mismatch")
    return sorted(owners)


def report(rows):
    return {"owners": len(validate(rows)), "rows": {k: len(v) for k, v in rows.items()}}


def import_snapshot(database, rows):
    """One PG transaction, scoped owner by owner. No merge/overwrite. All-or-nothing.

    The caller must separately verify the target is a dedicated empty database via migration
    administrator; RLS cannot establish global emptiness. This checks every imported owner.
    """
    from psycopg.types.json import Jsonb

    owners = validate(rows)
    if not owners:
        raise ValueError("empty snapshot refused")
    by_owner = {owner: {table: [] for table in TABLES} for owner in owners}
    for table, data in rows.items():
        for row in data:
            by_owner[row[OWNER_INDEX[table]]][table].append(row)
    with database.transaction() as con:
        # Lock all source owners in deterministic order. Existing runtime writes use same lock.
        for owner in owners:
            con.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1901))", (owner,))
        for owner in owners:
            con.execute("SELECT set_config('jarvis.owner', %s, true)", (owner,))
            for table in TABLES:
                if con.execute(f"SELECT count(*) FROM jarvis.{table} WHERE owner=%s", (owner,)).fetchone()[0]:
                    raise ValueError("target owner is not empty; import refused")
        for owner in owners:
            con.execute("SELECT set_config('jarvis.owner', %s, true)", (owner,))
            for table, (_, cols) in TABLES.items():
                params = ",".join(["%s"] * len(cols.split(",")))
                for row in by_owner[owner][table]:
                    values = list(row)
                    if table == "memories":
                        values[5] = Jsonb(values[5])
                    con.execute(f"INSERT INTO jarvis.{table} ({cols}) VALUES ({params})", values)
            # Compare read-back of all base rows (not generated FTS scores) before committing.
            for table, (_, cols) in TABLES.items():
                actual = [_normalize(table, row) for row in con.execute(
                    f"SELECT {cols} FROM jarvis.{table} WHERE owner=%s", (owner,))]
                expected = by_owner[owner][table]
                if len(actual) != len(expected) or fingerprint(actual) != fingerprint(expected):
                    raise ValueError("target read-back mismatch; rollback")
        con.execute("SELECT set_config('jarvis.owner', '', true)")
    return {"committed": True, "verified": True, **report(rows)}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--state-dir", required=True)
    a.add_argument("--apply", action="store_true", help="write to separately approved dedicated target")
    a.add_argument("--confirm-quiescent", action="store_true")
    a.add_argument("--confirm-empty-target", action="store_true")
    a.add_argument("--confirm-instance", help="expected target UUID; must match secret environment")
    x = a.parse_args(argv)
    if not x.confirm_quiescent:
        a.error("stop SQLite and target writers; explicitly confirm quiescence")
    try:
        rows = read_snapshot(x.state_dir)
        if not x.apply:
            print(json.dumps({"mode": "inspect", "target_contacted": False, **report(rows)}))
            return 0
        if not x.confirm_empty_target or not x.confirm_instance or x.confirm_instance != os.environ.get("JARVIS_POSTGRES_INSTANCE"):
            a.error("apply requires an administrator-verified empty target and matching instance UUID")
        from rightware.persistence.postgres import PostgresDatabase
        db = PostgresDatabase.from_env()
        print(json.dumps({"mode": "apply", **import_snapshot(db, rows)}))
        return 0
    except Exception:
        # A connection loss during COMMIT is ambiguous: inspect target before any retry.
        print(json.dumps({"ok": False, "reason": "MIGRATION_REFUSED_OR_FAILED",
                          "commit_status": "UNKNOWN_CHECK_TARGET" if x.apply else "NOT_ATTEMPTED"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
