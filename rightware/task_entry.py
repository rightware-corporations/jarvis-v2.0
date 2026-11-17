"""TE-02: opt-in trusted task entry using existing AgentSession, not a new agent.

Only an application host may call run_trusted_browser_fixture() with a factory
that creates a constrained AgentSession. Plain TextFacade.submit() is unchanged.
This deliberately narrow experiment is NOT a general NL task classifier,
Goose adapter, user-facing CLI, durable task ledger or real-model acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import secrets
from threading import Lock
from typing import Callable

from rightware.text_facade import TextFacade, TextResult

_FIXTURE_ID = "synthetic-archive-two-originals"
_IANA_ID = "iana-reserved-example-public-readonly"
_ALLOWED_SCOPE = frozenset({"browse"})
_TERMINAL = frozenset({
    "COMPLETE_VERIFIED", "INCOMPLETE", "UNKNOWN", "UNKNOWN_IDENTITY", "HALTED", "ERROR",
})


@dataclass(frozen=True)
class TaskEntryResult:
    request_id: str
    session_id: str
    route: str
    operational_state: str
    objective_states: tuple[tuple[str, str, int | None], ...]
    receipts_count: int
    factual_verified: bool
    completion_verified: bool
    model_commentary_unverified: str
    limitations: tuple[str, ...]

    def __post_init__(self):
        if self.route != "TASK" or self.operational_state not in _TERMINAL:
            raise ValueError("invalid task result")
        if self.factual_verified or (self.completion_verified and self.operational_state != "COMPLETE_VERIFIED"):
            raise ValueError("unverified claims must not become verified")


class TaskEntry:
    """Host-controlled opt-in bridge for ONE existing synthetic browser preset.

    Host code supplies the factory. Neither the natural-language instruction,
    nor model output, nor a user-supplied JSON object selects a capability.
    The factory must produce an actual protected AgentSession with receipt and
    completion gates already enabled. All execution stays in AgentSession.
    """

    def __init__(self, text_facade: TextFacade, *, fixture_session_factory: Callable | None = None,
                 public_session_factory: Callable | None = None):
        if not isinstance(text_facade, TextFacade):
            raise TypeError("expected a RIGHTWARE text facade")
        if fixture_session_factory is not None and not callable(fixture_session_factory):
            raise TypeError("fixture_session_factory must be callable")
        if public_session_factory is not None and not callable(public_session_factory):
            raise TypeError("public_session_factory must be callable")
        self.text_facade = text_facade
        self._fixture_session_factory = fixture_session_factory
        self._public_session_factory = public_session_factory
        self._lock = Lock()
        self._active: set[str] = set()

    def submit_text(self, session_id: str, text: str) -> TextResult:
        """The existing, tool-free D01/D02 path remains the default."""
        return self.text_facade.submit(session_id, text)

    def run_trusted_browser_fixture(self, session_id: str, instruction: str) -> TaskEntryResult:
        """Preserve TE-02 synthetic test-only mode (no real network)."""
        return self._run_trusted(session_id, instruction, self._fixture_session_factory, _FIXTURE_ID, True)

    def run_trusted_public_iana_task(self, session_id: str, instruction: str) -> TaskEntryResult:
        """Explicit host-authorized IANA-9110/9112 read-only task (real network permitted).

        This does not parse intents, enable tools on the default text path,
        or permit shell/filesystem/Windows effects. Document authenticity and
        factual correctness remain UNVERIFIED even if both pages are fetched.
        """
        return self._run_trusted(session_id, instruction, self._public_session_factory, _IANA_ID, False)

    def _run_trusted(self, session_id: str, instruction: str, factory: Callable | None,
                     preset_id: str, synthetic: bool) -> TaskEntryResult:
        """Only trusted host methods choose preset/grants; user text is never authority."""
        if (not isinstance(instruction, str) or not instruction.strip()
                or len(instruction) > self.text_facade.max_input_chars
                or any(ord(c) < 32 and c not in "\n\t\r" for c in instruction)):
            raise ValueError("invalid task instruction")
        self.text_facade.history_snapshot(session_id)  # checks host-minted session ownership
        if factory is None:
            raise PermissionError("No task execution has been enabled by the host")
        with self._lock:
            if session_id in self._active:
                raise RuntimeError("Task already running in this session")
            self._active.add(session_id)
        try:
            # Do not import the pinned vendor or start Ollama on text-only calls.
            from rightware.agent.session import AgentSession
            from rightware.agent.task_contract import TRUSTED_PRESETS

            agent = factory()
            if type(agent) is not AgentSession:
                raise PermissionError("Untrusted task executor")
            preset = TRUSTED_PRESETS[preset_id]
            budgets = agent.budgets
            if (agent.allow != _ALLOWED_SCOPE or agent.actions is not None
                    or agent.task_contract is not preset
                    or preset.synthetic is not synthetic
                    or agent.sites != preset.hosts
                    or not agent.receipts_enabled or not agent.completion_gate
                    or budgets is None or not 1 <= budgets.max_calls <= 12
                    or not 0 < budgets.deadline_seconds <= 120
                    or not 1 <= agent.max_turns <= 12):
                raise PermissionError("Task session is outside the approved task envelope")

            reply = agent.run(instruction)
            detail = reply.task_completion
            if (not isinstance(detail, dict)
                    or reply.completion not in _TERMINAL
                    or detail.get("state") != reply.completion
                    or detail.get("contract_id") != preset_id
                    or detail.get("answer_factually_verified") is not False):
                # Do not trust an unchecked model answer or an absent gate.
                return TaskEntryResult(
                    secrets.token_hex(16), session_id, "TASK", "ERROR", (), len(agent.receipts),
                    False, False, "", ("INVALID_COMPLETION_EVIDENCE",),
                )
            objectives = detail.get("objectives")
            if not isinstance(objectives, list) or len(objectives) != len(preset.objectives):
                return TaskEntryResult(
                    secrets.token_hex(16), session_id, "TASK", "ERROR", (), len(agent.receipts),
                    False, False, "", ("INCOMPLETE_OBJECTIVE_EVIDENCE",),
                )
            result_rows = []
            for index, o in enumerate(objectives):
                if (not isinstance(o, dict) or o.get("oid") != preset.objectives[index].oid
                        or o.get("state") not in ("VERIFIED", "PAGE_OBSERVED", "UNKNOWN", "MISSING")
                        or (o.get("evidence_sequence") is not None
                            and (type(o["evidence_sequence"]) is not int or o["evidence_sequence"] < 1))):
                    return TaskEntryResult(
                        secrets.token_hex(16), session_id, "TASK", "ERROR", (), len(agent.receipts),
                        False, False, "", ("MALFORMED_OBJECTIVE_EVIDENCE",),
                    )
                result_rows.append((o["oid"], o["state"], o.get("evidence_sequence")))
            return TaskEntryResult(
                request_id=secrets.token_hex(16), session_id=session_id, route="TASK",
                operational_state=reply.completion,
                objective_states=tuple(result_rows), receipts_count=len(agent.receipts),
                factual_verified=False, completion_verified=reply.completion == "COMPLETE_VERIFIED",
                model_commentary_unverified=reply.text,
                limitations=(("SYNTHETIC_READ_ONLY" if synthetic else "PUBLIC_IANA_READ_ONLY"),
                             "NO_FACTUAL_VERIFICATION", "NO_INDEPENDENT_MODEL_VERIFICATION"),
            )
        finally:
            with self._lock:
                self._active.discard(session_id)
