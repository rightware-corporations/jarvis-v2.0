"""DB01: explicit PostgreSQL backend. No implicit DDL, no fallback, no credential logs."""
from __future__ import annotations

import contextlib
import os
import uuid

from rightware.memory.identity import Owner


class DatabaseUnavailable(RuntimeError):
    """Sanitised failure; do not expose driver errors containing connection or row data."""


class PostgresDatabase:
    def __init__(self, dsn: str, instance_id: str):
        if not dsn or not instance_id:
            raise ValueError("PostgreSQL DSN and expected instance ID required")
        self._dsn = dsn
        self.instance_id = str(uuid.UUID(instance_id))
        try:
            import psycopg
            from psycopg.conninfo import conninfo_to_dict
        except ImportError:
            raise DatabaseUnavailable("PostgreSQL driver not installed") from None
        try:
            config = conninfo_to_dict(dsn)
        except Exception:
            raise ValueError("invalid PostgreSQL connection configuration") from None
        # Explicit TLS verification for every deployment; no implicit service/hostaddr substitution.
        if (config.get("sslmode") != "verify-full" or not config.get("host") or
                not config.get("dbname") or not config.get("user") or
                any(k in config for k in ("service", "hostaddr", "options"))):
            raise ValueError("PostgreSQL requires explicit host/database/user and sslmode=verify-full")
        self._driver = psycopg
        self.check()

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("JARVIS_POSTGRES_DSN", ""),
                   os.environ.get("JARVIS_POSTGRES_INSTANCE", ""))

    def _verify(self, con):
        row = con.execute("SELECT instance_id::text, version FROM jarvis.instance WHERE singleton").fetchone()
        if row != (self.instance_id, 1):
            raise DatabaseUnavailable("PostgreSQL instance or schema version mismatch")
        role = con.execute(
            "SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb "
            "FROM pg_catalog.pg_roles r WHERE r.rolname=current_user").fetchone()
        if role != (False,):
            raise DatabaseUnavailable("PostgreSQL runtime role is too privileged")
        rows = con.execute(
            "SELECT c.relname, c.relrowsecurity AND c.relforcerowsecurity, "
            "pg_catalog.pg_has_role(current_user,c.relowner,'MEMBER') "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='jarvis' AND c.relname IN "
            "('memories','memory_events','documents','segments','document_events')").fetchall()
        if len(rows) != 5 or any(not enabled or owns for _, enabled, owns in rows):
            raise DatabaseUnavailable("PostgreSQL owner isolation is not configured")
        if con.execute("SELECT count(*) FROM jarvis.memories").fetchone() != (0,):
            raise DatabaseUnavailable("PostgreSQL ownerless query was not isolated")
        if con.execute("SELECT count(*) FROM jarvis.documents").fetchone() != (0,):
            raise DatabaseUnavailable("PostgreSQL ownerless document query was not isolated")

    @contextlib.contextmanager
    def transaction(self, owner: str | None = None, *, write: bool = False):
        if owner is not None:
            Owner(owner, "operator-config")
        try:
            with self._driver.connect(self._dsn, connect_timeout=5, autocommit=False,
                                      sslmode="verify-full", options="-c search_path=pg_catalog") as con:
                con.execute("SET LOCAL statement_timeout = '8s'")
                con.execute("SET LOCAL lock_timeout = '4s'")
                con.execute("SELECT set_config('jarvis.owner', '', true)")
                self._verify(con)
                if owner is not None:
                    con.execute("SELECT set_config('jarvis.owner', %s, true)", (owner,))
                if write:
                    if owner is None:
                        raise DatabaseUnavailable("write requires owner")
                    # Cross-process serialization for quotas, supersession and deduplication.
                    con.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1901))", (owner,))
                yield con
        except DatabaseUnavailable:
            raise
        except self._driver.Error:
            raise DatabaseUnavailable("PostgreSQL operation failed; no SQLite fallback") from None

    def check(self):
        with self.transaction():
            pass
