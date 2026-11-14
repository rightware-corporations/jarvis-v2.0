"""Shared helpers for the WORK-02 lab tests (all results are FAKE)."""
import os
from pathlib import Path
import sys
import tempfile

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parents[1]
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

from w02lab import fixtures, harness, fake  # noqa: E402,F401
from w02lab.policy import Policy  # noqa: E402,F401
from w02lab.sandbox import Sandbox, SandboxError  # noqa: E402,F401

INITIAL_HEAD = "6bac396a5c9db65879feccfb064fdb502d814c7e"
# CEO-authorized reconciliation (09/11/2026): WORK-02 rebased onto this remote
# develop, which added two docs-only commits by another author.
RECONCILED_BASE = "7079e188ca69ff609923a03078758bf0f03185ec"
PRESERVED_REMOTE_COMMITS = ["62ee5ee", "7079e18"]
# Last commit of the WORK-02 publication (immutable). The WORK-02 scope check
# covers exactly RECONCILED_BASE..WORK02_PUBLISHED; later authorized missions
# (K04 docs, WORK-03) are outside that range by construction.
WORK02_PUBLISHED = "fa9faa9256b7941f2efd5c638fe6b6b7bb6efdb5"
PIN = "f21d902f4d3bd7f0f3f138f1a4613019a394b549"


def report_name(seed: int) -> str:
    with tempfile.TemporaryDirectory() as d:
        return fixtures.generate(Path(d), seed).report_name


class Scratch:
    """Fresh scenario + sandbox + policy for unit-level tests."""

    def __init__(self, seed=1, with_trap=False, write_authorized=True):
        self._tmp = tempfile.TemporaryDirectory(prefix="w02-test-")
        self.root = Path(self._tmp.name)
        self.scn = fixtures.generate(self.root, seed, with_trap=with_trap)
        self.sandbox = Sandbox(self.scn.sandbox)
        self.policy = Policy(write_authorized=write_authorized)
        self.trace = []
        from w02lab.tools import build_tools
        self.sources = {n: (self.scn.input_dir / n).read_text(encoding="utf-8")
                        for n in self.scn.truth["sources"]}
        self.tools = {t.tool_name: t for t in
                      build_tools(self.sandbox, self.policy, self.trace, self.scn.truth, self.sources)}

    def call(self, tool, **args):
        """Hook then execution, exactly as the Orchestrator does."""
        if not self.policy.before_tool_call(tool, args):
            return None
        return self.tools[tool].execute(**args)

    def close(self):
        self._tmp.cleanup()


def lab_threads_alive():
    import threading
    return [t.name for t in threading.enumerate() if t.name.startswith("w02-run") and t.is_alive()]


def outside(audit_paths, sandbox_root):
    sb = os.path.realpath(sandbox_root)
    return [p for p in audit_paths if not p.startswith(sb)]
