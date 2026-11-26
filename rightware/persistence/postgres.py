"""DB01: explicit PostgreSQL backend. No implicit DDL, no fallback, no credential logs."""
from __future__ import annotations

import contextlib
import os
import uuid

from rightware.memory.identity import Owner
from rightware.persistence.pg_guard import policies_match, grants_match


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
        if (any(os.environ.get(k) for k in ("PGSERVICE", "PGHOSTADDR", "PGOPTIONS")) or
                "/" in config["host"] or "," in config["host"]):
            raise ValueError("PostgreSQL requires a single explicit TCP host and no ambient service overrides")
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
            "SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication "
            "FROM pg_catalog.pg_roles r WHERE r.rolname=current_user").fetchone()
        if role != (False,):
            raise DatabaseUnavailable("PostgreSQL runtime role is too privileged")
        # Neon console/API roles are administrators. The runtime must be a separate SQL role.
        elevated = con.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles r "
            "WHERE r.rolname <> current_user AND "
            "(r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication "
            "OR r.rolname IN ('neon_superuser','pg_read_all_data','pg_write_all_data',"
            "'pg_execute_server_program','pg_read_server_files','pg_write_server_files')) "
            "AND pg_catalog.pg_has_role(current_user,r.oid,'MEMBER'))").fetchone()
        owns_database = con.execute(
            "SELECT pg_catalog.pg_has_role(current_user,datdba,'MEMBER') "
            "FROM pg_catalog.pg_database WHERE datname=current_database()").fetchone()
        if elevated != (False,) or owns_database != (False,):
            raise DatabaseUnavailable("PostgreSQL runtime has elevated membership or database ownership")
        rows = con.execute(
            "SELECT c.relname, c.relrowsecurity AND c.relforcerowsecurity, "
            "pg_catalog.pg_has_role(current_user,c.relowner,'MEMBER') "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='jarvis' AND c.relname IN "
            "('memories','memory_events','documents','segments','document_events')").fetchall()
        if len(rows) != 5 or any(not enabled or owns for _, enabled, owns in rows):
            raise DatabaseUnavailable("PostgreSQL owner isolation is not configured")
        policies = con.execute(
            "SELECT tablename,policyname,permissive,roles::text,cmd,qual,with_check "
            "FROM pg_catalog.pg_policies WHERE schemaname='jarvis'").fetchall()
        if not policies_match(policies):
            raise DatabaseUnavailable("PostgreSQL owner policy does not match schema revision 1")
        schema = con.execute(
            "SELECT has_schema_privilege(current_user,n.oid,'USAGE'), "
            "has_schema_privilege(current_user,n.oid,'CREATE'), "
            "pg_has_role(current_user,n.nspowner,'MEMBER') "
            "FROM pg_catalog.pg_namespace n WHERE n.nspname='jarvis'").fetchone()
        if schema != (True, False, False):
            raise DatabaseUnavailable("PostgreSQL runtime schema privileges mismatch")
        grants = con.execute(
            "SELECT c.relname,p.privilege,has_table_privilege(current_user,c.oid,p.privilege), "
            "has_table_privilege(current_user,c.oid,p.privilege || ' WITH GRANT OPTION') "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p(privilege) "
            "WHERE n.nspname='jarvis' AND c.relkind='r'").fetchall()
        if not grants_match(grants):
            raise DatabaseUnavailable("PostgreSQL runtime table privileges mismatch")
        extra_columns = con.execute(
            "SELECT c.relname,p.privilege FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) p(privilege) "
            "WHERE n.nspname='jarvis' AND c.relkind='r' AND "
            "(has_any_column_privilege(current_user,c.oid,p.privilege || ' WITH GRANT OPTION') "
            "OR (has_any_column_privilege(current_user,c.oid,p.privilege) "
            "AND NOT has_table_privilege(current_user,c.oid,p.privilege)))").fetchall()
        if extra_columns:
            raise DatabaseUnavailable("PostgreSQL runtime column privileges mismatch")
        for table in ("memories", "documents", "segments", "memory_events", "document_events"):
            if con.execute(f"SELECT count(*) FROM jarvis.{table}").fetchone() != (0,):
                raise DatabaseUnavailable("PostgreSQL ownerless query was not isolated")

    @contextlib.contextmanager
    def transaction(self, owner: str | None = None, *, write: bool = False):
        if owner is not None:
            Owner(owner, "operator-config")
        try:
            with self._driver.connect(self._dsn, connect_timeout=5, autocommit=False,
                                      sslmode="verify-full", gssencmode="disable",
                                      options="-c search_path=pg_catalog") as con:
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
