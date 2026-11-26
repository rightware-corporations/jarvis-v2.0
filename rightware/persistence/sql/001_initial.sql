-- DB01 revision 1: run ONCE in a dedicated database using a migration role.
-- No application credentials, no public grants, no destructive or implicit migrations.
BEGIN;
CREATE SCHEMA jarvis;
REVOKE ALL ON SCHEMA jarvis FROM PUBLIC;
CREATE TABLE jarvis.instance (
    singleton boolean PRIMARY KEY CHECK (singleton),
    instance_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0)
);
INSERT INTO jarvis.instance VALUES (true, gen_random_uuid(), 1);
CREATE TABLE jarvis.memories (
    id text PRIMARY KEY, owner text NOT NULL, category text NOT NULL
        CHECK (category IN ('preferencia','facto','objectivo','contexto')),
    topic text NOT NULL CHECK (length(topic) BETWEEN 1 AND 80),
    content text NOT NULL CHECK (length(content) BETWEEN 1 AND 400),
    provenance jsonb NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
    created_at double precision NOT NULL, updated_at double precision NOT NULL,
    status text NOT NULL CHECK (status IN ('confirmed','pending','superseded')),
    superseded_by text,
    UNIQUE (owner, id)
);
CREATE INDEX memories_owner_status ON jarvis.memories(owner, status);
CREATE UNIQUE INDEX memories_active_topic ON jarvis.memories(owner, category, topic) WHERE status='confirmed';
CREATE TABLE jarvis.memory_events (
    at double precision NOT NULL, owner text NOT NULL, memory_id text NOT NULL, action text NOT NULL
);
CREATE INDEX memory_events_owner ON jarvis.memory_events(owner, at);
CREATE TABLE jarvis.documents (
    id text PRIMARY KEY, owner text NOT NULL, name text NOT NULL, kind text NOT NULL,
    sha256 text NOT NULL, size bigint NOT NULL CHECK (size >= 0),
    units integer NOT NULL, segments integer NOT NULL, created_at double precision NOT NULL,
    injection_suspected boolean NOT NULL DEFAULT false,
    UNIQUE (owner, id), UNIQUE (owner, sha256)
);
CREATE TABLE jarvis.segments (
    doc_id text NOT NULL, owner text NOT NULL, seq integer NOT NULL,
    locator text NOT NULL, text text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS
        (to_tsvector('pg_catalog.simple'::regconfig,
         translate(lower(text),'áàâãäéèêëíìîïóòôõöúùûüç','aaaaaeeeeiiiiooooouuuuc'))) STORED,
    PRIMARY KEY (doc_id, seq),
    FOREIGN KEY (owner, doc_id) REFERENCES jarvis.documents(owner,id) ON DELETE CASCADE
);
CREATE INDEX segments_search ON jarvis.segments USING gin(search_vector);
CREATE INDEX segments_owner ON jarvis.segments(owner,doc_id);
CREATE TABLE jarvis.document_events (
    at double precision NOT NULL, owner text NOT NULL, doc_id text NOT NULL, action text NOT NULL
);
CREATE INDEX document_events_owner ON jarvis.document_events(owner,at);
ALTER TABLE jarvis.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis.memories FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_only ON jarvis.memories
    USING (owner = nullif(current_setting('jarvis.owner', true), ''))
    WITH CHECK (owner = nullif(current_setting('jarvis.owner', true), ''));
ALTER TABLE jarvis.memory_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis.memory_events FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_only ON jarvis.memory_events
    USING (owner = nullif(current_setting('jarvis.owner', true), ''))
    WITH CHECK (owner = nullif(current_setting('jarvis.owner', true), ''));
ALTER TABLE jarvis.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis.documents FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_only ON jarvis.documents
    USING (owner = nullif(current_setting('jarvis.owner', true), ''))
    WITH CHECK (owner = nullif(current_setting('jarvis.owner', true), ''));
ALTER TABLE jarvis.segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis.segments FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_only ON jarvis.segments
    USING (owner = nullif(current_setting('jarvis.owner', true), ''))
    WITH CHECK (owner = nullif(current_setting('jarvis.owner', true), ''));
ALTER TABLE jarvis.document_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis.document_events FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_only ON jarvis.document_events
    USING (owner = nullif(current_setting('jarvis.owner', true), ''))
    WITH CHECK (owner = nullif(current_setting('jarvis.owner', true), ''));
REVOKE ALL ON ALL TABLES IN SCHEMA jarvis FROM PUBLIC;
COMMIT;
