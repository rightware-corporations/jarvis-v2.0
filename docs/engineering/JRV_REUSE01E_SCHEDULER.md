# REUSE01-E — Scheduling reuse gate

**Status:** source-backed and laboratory-tested fit-gap. Production integration NOT IMPLEMENTED. No automation enabled for a real user.

**Blueprint:** UC-031, UC-033, AT-018 / NEG-16, CT-08/CT-09. The original requirement is a revocable, persistent recurring scope, verified outcomes, no duplicate effects, and notifications. See JRV-002/003.

## Reuse, do not rebuild

| Pinned OpenJarvis component | Reuse decision |
|---|---|
| `SchedulerStore` and `ScheduledTask` | Reuse SQLite storage and task representation, with a host-controlled owner boundary. |
| `TaskScheduler.create_task` and recurrence computation | Reuse once/interval/cron semantics, normalize once values to UTC, validate bounds and timezone. |
| `TaskScheduler` polling lifecycle | Candidate to reuse under a guarded, single-worker dispatch contract; must not expose raw stock execution. |
| `scheduler/tools.py` model-facing tools | Do not directly enable: proposed prompt, tools and agent are model inputs; creation/list/resume need authenticated owner and explicit recurring scope. |
| `agents/scheduler.py` managed agent ticks | Do not run a second scheduler for the same jobs. |
| Existing RIGHTWARE Control Plane, AgentPolicy, Gateway, receipts | Keep authority and verification. Do not create a second executor or approval model. |

## Measured findings

Run `PYTHONPATH=vendor/openjarvis/src python labs/reuse01/scheduler_probe.py` with the pinned source present. This probe reproduces known gaps; exit 0 is not production acceptance. The isolated execution used two source files whose Git hashes matched the pin, without the rest of the package. The daemon was stopped and the temporary SQLite DB deleted by the context manager. Only a synthetic callback was invoked; no Qwen, network, credentials or external effect. Three functional groups passed and six known gaps reproduced (see JSON evidence). Cron was not run: croniter was absent.

## Smallest safe integration gate (proposed; no new product authority)

1. Select the first authorized recurring action explicitly: initially a lab-only reminder/read-only approved capability, not unrestricted tool access. Use the existing scheduler as timing/storage, the existing Control Plane as authority, and its verified outcome as result. Keep disabled by default.
2. Bind each job to authenticated owner, immutable action/scope, consent/expiry, timezone and normalized schedule. Scope cannot be widened by the model. All list/pause/resume/revoke/read-log operations must be owner-filtered; resume after revocation requires new approval.
3. Re-read durable authorization and occurrence at dispatch, atomically claim a unique (schedule id, occurrence UTC) before invoking existing executor. Maintain one worker on the approved persistent host; an interrupted/unknown external effect is not automatically retried. Revocation must prevent future dispatch, never silently resurrect a cancelled job. Treat already-started effects separately.
4. Record verified receipts and outcomes, not upstream dry-run or a returned string as completion. Test actual action, restart, expired/revoked scope, cross-owner operations, duplicate occurrence, timezone, missed run and notification. Keep logs minimal. No stock scheduler daemon connected to JarvisSystem until these gates pass.

This is an integration contract candidate, not a claim that the recurring execution feature exists. Persistent host remains a prerequisite for delivery. Do not silently add a new storage engine or switch vendor revision.
