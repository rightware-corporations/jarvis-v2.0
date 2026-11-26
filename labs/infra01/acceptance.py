"""INFRA01-B: explicit acceptance runner for an isolated cloud DB.

Default runs local synthetic SQLite tests only. --live requires dedicated test variables.
No infrastructure creation, installs, production credentials, raw error messages or tunnel.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_suite(pattern, expected):
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern,
                                                top_level_dir=str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    failed = [test.id() for test, _ in result.failures + result.errors]
    passed = result.wasSuccessful() and result.testsRun == expected and not result.skipped
    return {"status": "PASS" if passed else "FAIL_OR_INCOMPLETE", "expected": expected,
            "executed": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped), "failed_tests": failed,
            "seconds": round(time.monotonic() - started, 3)}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--live", action="store_true")
    x = a.parse_args(argv)
    report = {"sqlite_source": run_suite("test_db01_migrate.py", 9),
              "postgres": {"status": "NOT_RUN"}}
    if report["sqlite_source"]["status"] != "PASS":
        print(json.dumps(report, indent=2))
        return 2
    if x.live:
        # Never use production env as a substitute for disposable test credentials.
        if (os.environ.get("JARVIS_DB01_TEST") != "1"
                or not os.environ.get("JARVIS_DB01_TEST_DSN")
                or not os.environ.get("JARVIS_DB01_TEST_INSTANCE")
                or os.environ.get("JARVIS_DB01_TEST_DSN") == os.environ.get("JARVIS_POSTGRES_DSN")
                or os.environ.get("JARVIS_DB01_TEST_INSTANCE") == os.environ.get("JARVIS_POSTGRES_INSTANCE")):
            report["postgres"] = {"status": "BLOCKED", "reason": "DISPOSABLE_TEST_CONFIGURATION_REQUIRED"}
        else:
            report["postgres"] = run_suite("test_db01_postgres.py", 6)
    print(json.dumps(report, indent=2))
    return 0 if not x.live or report["postgres"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
