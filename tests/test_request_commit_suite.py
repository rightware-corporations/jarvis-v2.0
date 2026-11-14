"""Regression (WORK-06 request 1, WORK-07 R1): the WHOLE product suite must pass on a request
commit, because every request-triggered workflow runs it at GATE 2 on that very commit.

Runs the suite in a temporary copy of the repository with valid WORK-07 request files added.
No network, no model. Skipped inside the copy itself (no recursion).
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FLAG = "RIGHTWARE_REQUEST_COMMIT_SIMULATION"


@unittest.skipIf(os.environ.get(FLAG), "inside the simulation copy")
class SuiteOnARequestCommit(unittest.TestCase):
    def test_full_suite_passes_with_every_work07_request_file_present(self):
        from labs.work07_rfc_gate import gate as G
        tmp = Path(tempfile.mkdtemp()) / "repo"
        shutil.copytree(ROOT, tmp, ignore=shutil.ignore_patterns(".git", "vendor", ".runtime", "__pycache__"))
        for op, spec in G.OPS.items():
            (tmp / spec["request"]).write_text(json.dumps(
                {"experiment": spec["experiment"], "request_id": 1, "approved_code_sha": "a" * 40,
                 "plan_sha256": G.plan_sha256(op), "authorized_by": "simulation"}), encoding="utf-8")
        env = {**os.environ, FLAG: "1"}
        proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=tmp, env=env,
                              capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])


if __name__ == "__main__":
    unittest.main()
