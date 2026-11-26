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
