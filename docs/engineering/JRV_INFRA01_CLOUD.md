# JRV-INFRA01 — Persistent cloud infrastructure: decision proposal
Date: 2026-11-26. Status: RESEARCHED / PROPOSED; no accounts, provisioning, network authorization, credentials, or deployment. Cloud-only operator constraint. Baseline 8682ff1c03293f7c812bf6e082f1de11a800d05a.

## Evidence and candidate selection
- Neon Free: $0 within allowance, 1 GB PostgreSQL/project, 100 CU-hours/month/project, compute suspension after five idle minutes, 5 GB public transfer/month/project, limited six-hour restore history. https://neon.com/docs/introduction/plans
- Supabase Free: 500 MB database, inactivity pause after seven days, external backups recommended. https://supabase.com/pricing ; https://supabase.com/docs/guides/platform/free-project-pausing ; https://supabase.com/docs/guides/platform/backups
- OCI Always Free A1: CURRENT official documentation specifies 2 OCPU, 12 GB RAM, 200 GB total boot/block storage and five volume backups; idle compute may be reclaimed and home-region capacity is not guaranteed. https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Johannesburg is an OCI region; verify signup eligibility and free A1 capacity before selecting home region. https://www.oracle.com/za/cloud/cloud-regions/johannesburg/
- Hugging Face CPU Basic hardware: 2 vCPU, 16 GB RAM, ephemeral disk; Docker/Gradio compute Spaces currently require paid subscription despite zero hourly CPU Basic price. https://huggingface.co/docs/hub/en/spaces-overview
- Google free e2-micro unsuitable for combined inference stack. https://cloud.google.com/products/compute
- Paid fallback: benchmark an x86_64 Linux VPS with >=4 vCPU, 16 GB RAM and >=80 GB SSD (engineering target, not measured requirement or approved spending). https://www.hetzner.com/cloud/cost-optimized/

## Proposed topology
Private HTTPS client -> existing B6 auth boundary -> JARVIS service on persistent Linux VM -> loopback-only Ollama/Qwen, Faster Whisper, Kokoro. Independent PostgreSQL candidate Neon, verified TLS direct endpoint and dedicated runtime role. Models/cache on private VM disk. Off-host encrypted backup plan required; no raw user data in GitHub. No public model/DB ports on VM. Do not use Claude session as permanent host. OCI A1 requires ARM64 compatibility and voice/inference performance benchmark; free tier has no uptime guarantee. Do not reuse consumed network authorization.

## Gates (sequential)
INFRA01-A: operator selects DB/compute candidate and confirms cost ceiling and region/data residency. No provisioning before approval.
INFRA01-B: provision separate disposable PostgreSQL instance with least-privileged runtime role and verified TLS CA; run DB01 source tests plus six live PG tests and inspect rollback. Check role/grants, cold connection and network latency. No real data.
INFRA01-C: provision candidate VM only if approved; check CPU architecture, RAM/disk, pinned dependency availability, build hash, model artifact integrity, loopback binding. Execute synthetic E2E and concurrent STT/LLM/TTS benchmark; measure first-response and transcription latencies, peak RSS, restart recovery.
INFRA01-D: verify off-host encrypted backups and restore, access/revocation, egress scope, durable DB instance identity, host restart recovery. Configure bounded private HTTPS window only with explicit authorization. No persistent public exposure until approved.
INFRA01-E: decide actual migration/cutover after DB01-H evidence; physical operator voice acceptance, then Issa preview subject to separate approval. No production claims.

## Limitations
No cloud availability, region latency, ARM64 dependency compatibility, backup recovery or service uptime measured. DB01 tests remain NOT_RUN in current sandbox (postgres/psql/psycopg unavailable). Free PostgreSQL allowances can be exhausted; no artificial keepalive or cost-increasing provisioning. pgvector deferred until retrieval baseline. Personal-data retention, encryption, jurisdiction and backups must be approved before production.


## 2026-11-26 — INFRA01-B operator decision and execution preparation
**Approved:** evaluate Neon Free and OCI Always Free. No paid services, no real-data migration without approval. No account provisioning or connection established in this session. Do not upgrade either plan.

### Neon disposable PostgreSQL
1. Connect the Neon integration or use the Neon Console in the cloud. Confirm organization Free plan, quota, region/data jurisdiction and no paid upgrade. Create a NEW isolated project `jarvis-db01-lab` (suggested name), no copy/branch of personal data. PostgreSQL 17 candidate; record selected version and region. Use a direct endpoint (not -pooler).
2. Neon console/API-created roles are administrative members of neon_superuser. Use the project admin only for schema setup, then create a separate LOGIN role through SQL (not console/API role creation): NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS, no role memberships, not DB owner. Generate and assign a strong random password through a secure operator-controlled method; never include password in repo, transcript, command history, or evidence. Verify actual roles/grants. Apply `rightware/persistence/sql/001_initial.sql` and `grant_runtime.sql` against the disposable target as migration role. Confirm all five forced RLS policies.
3. Retrieve instance UUID from jarvis.instance. Inject test-only secrets via approved cloud secret mechanism: JARVIS_DB01_TEST=1, JARVIS_DB01_TEST_DSN, JARVIS_DB01_TEST_INSTANCE. Direct connection uses sslmode=verify-full; explicitly trust system CA using sslrootcert=system when supported by installed libpq, otherwise approved CA file. Preserve channel_binding=require when supported; no fallback to weaker TLS. Check direct TCP access to that exact endpoint:5432 only under the operator-approved test scope. No old proxy/tunnel authorization is reused. Never paste a full DSN into chat.
4. In cloud checkout use a separate temporary Python environment for acceptance with optional requirements-db01.txt; no changes to GUI venv, no installation on operator PC. First run `python -m labs.infra01.acceptance` (source-only, no DB). Then `python -m labs.infra01.acceptance --live` only after dedicated TLS test configuration. Runner requires exactly nine source tests and six live tests, no skips; emits metadata and failed method names, never raw traceback/DSN. Review detailed errors privately only when needed. Report latency, actual version, role and TLS checks separately; no inference or physical mic claim. Delete disposable synthetic project only after evidence is retained and operator authorizes cleanup.
5. No runtime launch with `--storage postgres` until live acceptance passes. A real persistent DB is a separate project/instance and requires cutover approval.

### Oracle Always Free candidate (INFRA01-C, not provisioned)
- Verify home region, signup/verification and A1 capacity in OCI Console. Only resources explicitly Always Free eligible; no PAYG upgrade. VM.Standard.A1.Flex with 2 OCPU, 12 GB RAM; Ubuntu 24.04 ARM64 candidate. Keep combined boot/block volumes within 200 GB allowance, confirm eligibility before create. No public Ollama/JARVIS/DB ports. SSH only restricted to approved operator/management source; never send SSH private keys.
- Test actual ARM64 dependencies, model cache size, cold/warm inference, voice and memory/disk pressure before approving this host. Free compute idle reclamation means no guaranteed permanent availability. No account or VM was created here.

References (official): https://neon.com/docs/manage/roles ; https://neon.com/docs/get-started/connect-neon ; https://neon.com/docs/security/security-overview ; https://www.postgresql.org/docs/17/libpq-connect.html ; https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

## Live Neon SQL checkpoint
Free lab created and schema applied. Provider now supports scoped read_write roles; this was used instead of administrative default, then explicit revokes narrowed broad DML grants. See `docs/evidence/infra01/neon-sql.json`. SQL-level evidence is not equivalent to Python acceptance; direct TLS and full runtime remain pending. Synthetic rows retained; no destructive cleanup performed.
