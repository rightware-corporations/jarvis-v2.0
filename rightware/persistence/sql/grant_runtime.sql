-- Run as the migration role after 001. psql -v app_role=... -f grant_runtime.sql
-- The pre-provisioned application LOGIN role must not own objects, be a superuser,
-- have BYPASSRLS, CREATEROLE, CREATEDB, or be a member of privileged roles.
BEGIN;
GRANT USAGE ON SCHEMA jarvis TO :"app_role";
GRANT SELECT ON jarvis.instance TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON jarvis.memories TO :"app_role";
GRANT SELECT, INSERT ON jarvis.memory_events TO :"app_role";
GRANT SELECT, INSERT, DELETE ON jarvis.documents, jarvis.segments TO :"app_role";
GRANT SELECT, INSERT ON jarvis.document_events TO :"app_role";
COMMIT;
