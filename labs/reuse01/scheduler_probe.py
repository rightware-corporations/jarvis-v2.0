"""REUSE01-E: run pinned OpenJarvis scheduler against disposable synthetic data.
No model, network, product DB, external actions or persistent service.
A passing gap test means a defect was reproduced, NOT a safe scheduler.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openjarvis.scheduler.scheduler import ScheduledTask, TaskScheduler
from openjarvis.scheduler.store import SchedulerStore


class SyntheticSink:
    def __init__(self):
        self.calls = []
        self.called = threading.Event()

    def ask(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        self.called.set()
        return "synthetic acknowledgement"


def probe():
    results = {}
    with tempfile.TemporaryDirectory(prefix="jrv-reuse01e-") as tmp:
        path = Path(tmp) / "scheduler.sqlite3"
        store = SchedulerStore(path)
        sink = SyntheticSink()
        scheduler = TaskScheduler(store, system=sink, poll_interval=0.05)
        # Real background worker, once, with a synthetic in-memory destination.
        target = (datetime.now(timezone.utc) + timedelta(seconds=0.15)).isoformat()
        task = scheduler.create_task("synthetic once", "once", target, metadata={"owner": "lab:a"})
        store.close()
        store = SchedulerStore(path)
        scheduler = TaskScheduler(store, system=sink, poll_interval=0.05)
        assert store.get_task(task.id)["next_run"] == target
        results["persist_restart"] = "PASS"
        scheduler.start()
        try:
            assert sink.called.wait(3), "worker did not dispatch"
        finally:
            scheduler.stop()
        assert len(sink.calls) == 1
        assert store.get_task(task.id)["status"] == "completed"
        assert store.get_run_logs(task.id)[0]["success"] == 1
        results["once_worker_synthetic_sink"] = "PASS"

        recurring = scheduler.create_task("synthetic interval", "interval", "3600")
        scheduler.pause_task(recurring.id)
        assert store.get_task(recurring.id)["status"] == "paused"
        scheduler.resume_task(recurring.id)
        assert store.get_task(recurring.id)["status"] == "active"
        scheduler.cancel_task(recurring.id)
        assert store.get_task(recurring.id)["status"] == "cancelled"
        assert store.get_task(recurring.id)["next_run"] is None
        results["lifecycle_crud"] = "PASS"

        # A snapshot of due work is not revalidated by the pinned executor.
        due = scheduler.create_task("synthetic revoked", "once", "2000-01-01T00:00:00+00:00")
        snapshot = ScheduledTask.from_dict(next(d for d in store.get_due_tasks(datetime.now(timezone.utc).isoformat()) if d["id"] == due.id))
        scheduler.cancel_task(due.id)
        before = len(sink.calls)
        scheduler._execute_task(snapshot)
        results["revoked_snapshot_dispatched"] = "GAP_REPRODUCED" if len(sink.calls) == before + 1 else "NOT_REPRODUCED"
        results["revoked_once_status_overwritten"] = "GAP_REPRODUCED" if store.get_task(due.id)["status"] == "completed" else "NOT_REPRODUCED"

        # Two independent due snapshots can dispatch the same occurrence twice.
        once = scheduler.create_task("synthetic duplicate", "once", "2000-01-01T00:00:00+00:00")
        snapshot = ScheduledTask.from_dict(store.get_task(once.id))
        before = len(sink.calls)
        scheduler._execute_task(snapshot)
        scheduler._execute_task(snapshot)
        results["duplicate_occurrence"] = "GAP_REPRODUCED" if len(sink.calls) == before + 2 and len(store.get_run_logs(once.id)) == 2 else "NOT_REPRODUCED"

        dry = TaskScheduler(store, system=None)
        fake = dry.create_task("synthetic dry-run", "once", "2000-01-01T00:00:00+00:00")
        dry._execute_task(fake)
        log = store.get_run_logs(fake.id)[0]
        results["dry_run_marked_success"] = "GAP_REPRODUCED" if log["success"] == 1 and log["result"].startswith("[dry-run]") else "NOT_REPRODUCED"

        a = scheduler.create_task("synthetic owner A", "interval", "3600", metadata={"owner": "lab:a"})
        b = scheduler.create_task("synthetic owner B", "interval", "3600", metadata={"owner": "lab:b"})
        visible = {d.id for d in scheduler.list_tasks()}
        results["global_listing_no_owner_boundary"] = "GAP_REPRODUCED" if {a.id, b.id} <= visible else "NOT_REPRODUCED"
        # SQLite compares strings; normalize offset-bearing once schedules before storage.
        offset_task = scheduler.create_task("synthetic timezone", "once", "2026-01-01T10:00:00+02:00")
        due_ids = {d["id"] for d in store.get_due_tasks("2026-01-01T09:00:00+00:00")}
        results["once_noncanonical_offset"] = "GAP_REPRODUCED" if offset_task.id not in due_ids else "NOT_REPRODUCED"
        store.close()
    return {"python": __import__("platform").python_version(), "sqlite": sqlite3.sqlite_version,
            "scope": "pinned upstream store and scheduler; real SQLite and local worker; synthetic in-memory sink only",
            "results": results, "production_enabled": False}


if __name__ == "__main__":
    report = probe()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # This is a discovery probe, not an acceptance gate. Any changed finding must be reviewed.
    raise SystemExit(0 if list(report["results"].values()).count("PASS") == 3 and
                     list(report["results"].values()).count("GAP_REPRODUCED") == 6 else 1)
