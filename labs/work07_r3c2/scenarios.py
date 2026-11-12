"""WORK-07 R3-C2-012 E1/E4 scenarios on the R3-C1 synthetic archive. FAKE model, TEST-ONLY.

``run_experiment`` builds a REAL AgentSession (real pinned OrchestratorAgent, AgentPolicy,
PublicBrowser over the local archive), installs the test-only InterceptingEngine and returns
everything needed to check the accounting. Not evidence about Qwen.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from labs.work07_r3c1.scenarios import FakeModel, INSTRUCTION, call, shown_link
from labs.work07_r3c1.site import HOST, OFFSITE, ORIGINALS, START, Archive
from labs.work07_r3c2.interception import (FEEDBACK_TAG, CountingEngine, ExperimentState, Objective,
                                           installed)

OBJECTIVES = tuple(Objective(f"O{i}", f"abrir o documento original de {doc}", ref["original"])
                   for i, (doc, ref) in enumerate(ORIGINALS.items(), 1))


def search(doc):
    return [lambda m, d=doc: call("web_type", field="F1", text=d), lambda m: call("web_submit", field="F1"),
            lambda m, d=doc: call("web_follow", link=shown_link(m, f"/info/{d.lower()}/"))]


START_STEPS = [lambda m: call("web_open", url=START)]
INFO_ONLY = START_STEPS + search("AX-101") + search("AX-202")          # R3-C1 scenario A, before the answer


def premature(m):
    return {"content": "AX-101 trata do enquadramento e AX-202 do transporte (segundo as páginas de informação)."}


def follow_originals():
    return [lambda m: call("web_follow", link=shown_link(m, "/docs/ax-101.html")),
            lambda m: call("web_find", text="View original"),
            lambda m: call("web_follow", link=shown_link(m, "/docs/ax-202.html")),
            lambda m: {"content": "Abertos os dois originais: AX-101 (Widget Framing) e AX-202 (Widget Transport)."}]


def run_experiment(steps, *, budget=1, max_turns=14, budgets=None, clock=None, hook=None,
                   objectives=OBJECTIVES, upstream_guard=None):
    from rightware.agent import session as S
    archive = Archive()
    model = FakeModel(steps)
    if hook is not None:
        inner = model.generate

        def generate(messages, **kw):
            hook(len(model.received))
            return inner(messages, **kw)
        model.generate = generate
    counting = CountingEngine(model)
    audit = Path(tempfile.mkdtemp()) / "audit.jsonl"
    kwargs = {"clock": clock} if clock else {}
    session = S.AgentSession(counting, "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,),
                             start_url=START, browser_fetcher=archive.fetcher(), audit_path=audit,
                             budgets=budgets or S.Budgets(max_calls=14, deadline_seconds=900),
                             max_turns=max_turns, trace=True, **kwargs)
    state = ExperimentState(objectives=tuple(objectives), budget=budget)
    original_init = S._RightwareOrchestrator.__init__
    if upstream_guard is not None:                     # re-inject a misplaced guard (approved-not-executed path)
        def with_guard(self, *a, **k):
            original_init(self, *a, **k)
            self._loop_guard = upstream_guard()
        S._RightwareOrchestrator.__init__ = with_guard
    try:
        with installed(session, state):
            reply = session.run(INSTRUCTION)
    finally:
        S._RightwareOrchestrator.__init__ = original_init
    return {"session": session, "reply": reply, "state": state, "model": model, "counting": counting,
            "archive": archive, "audit": audit}


__all__ = ["FEEDBACK_TAG", "HOST", "OFFSITE", "OBJECTIVES", "ORIGINALS", "START", "INFO_ONLY", "premature",
           "follow_originals", "search", "run_experiment", "call", "shown_link"]
