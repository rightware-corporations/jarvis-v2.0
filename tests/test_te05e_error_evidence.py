"""TE-05E: an ERROR must not destroy safe diagnostics; failures get finite codes; the live workflow
verdict is truthful.

Deterministic only: FAKE model, mocked HTTP (httpx.MockTransport through the real HttpxFetcher),
injected clocks, simulated engine exceptions. No Ollama, no real Qwen, no real network.
"""
from contextlib import redirect_stdout
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from labs.te05e_live import verdict as V
from rightware import runtime, task_cli
from rightware.task_entry import TaskEntry, TaskEntryResult
from rightware.text_facade import TextFacade

try:
    import httpx
    from openjarvis.engine._base import EngineConnectionError
    from rightware.agent import diagnostics as D
    from rightware.agent.session import AgentSession, Budgets, reply_json
    from rightware.agent.web import HttpxFetcher
    from labs.work07_r3c1.scenarios import FakeModel, call
except ImportError:                      # plain Python without the pinned vendor
    AgentSession = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
I1 = "https://www.iana.org/domains/reserved"
I2 = "https://www.iana.org/help/example-domains"
PRESET = "iana-reserved-example-public-readonly"
SECRET = "SECRET-7c1f https://evil.example/token=abc"


def _engine_timeout():
    try:
        raise httpx.ReadTimeout("read timed out")
    except httpx.ReadTimeout as exc:
        try:
            raise EngineConnectionError("Ollama not reachable") from exc
        except EngineConnectionError as wrapped:
            return wrapped


def _engine_unreachable():
    try:
        raise httpx.ConnectError("refused")
    except httpx.ConnectError as exc:
        try:
            raise EngineConnectionError("Ollama not reachable") from exc
        except EngineConnectionError as wrapped:
            return wrapped


@unittest.skipIf(AgentSession is None, "pinned OpenJarvis venv required")
class ErrorCodes(unittest.TestCase):
    def test_classification_uses_exception_types_only(self):
        self.assertEqual(D.engine_error_code(_engine_timeout()), "ENGINE_TIMEOUT")
        self.assertEqual(D.engine_error_code(_engine_unreachable()), "ENGINE_CONNECTION")
        self.assertEqual(D.engine_error_code(EngineConnectionError("x")), "ENGINE_CONNECTION")
        self.assertEqual(D.engine_error_code(TimeoutError()), "ENGINE_TIMEOUT")
        self.assertEqual(D.engine_error_code(RuntimeError("Ollama returned 500: timeout")), "ENGINE_FAILURE")
        self.assertEqual(D.engine_error_code(ValueError("ENGINE_TIMEOUT connect refused")), "ENGINE_FAILURE")
        self.assertTrue({"NONE", "ENGINE_TIMEOUT", "ENGINE_CONNECTION", "ENGINE_FAILURE", "AGENT_FAILURE",
                         "AUDIT_FAILURE", "EVIDENCE_INCOMPLETE", "OTHER"} == D.ERROR_CODES)

    def test_task_entry_error_vocabulary_matches_and_rejects_inconsistent_records(self):
        from rightware import task_entry
        self.assertEqual(task_entry._ERROR_CODES, D.ERROR_CODES)
        base = dict(request_id="r", session_id="s", route="TASK", objective_states=(), receipts_count=0,
                    factual_verified=False, completion_verified=False, model_commentary_unverified="",
                    limitations=())
        for state, code in (("ERROR", "NONE"), ("UNKNOWN_IDENTITY", "ENGINE_TIMEOUT"), ("ERROR", SECRET)):
            with self.subTest(state=state, code=code), self.assertRaises(ValueError):
                TaskEntryResult(operational_state=state, error_code=code, **base)
        with self.assertRaises(ValueError):           # ERROR can never be presented as verified complete
            TaskEntryResult(operational_state="ERROR", error_code="OTHER",
                            **{**base, "completion_verified": True})


@unittest.skipIf(AgentSession is None, "pinned OpenJarvis venv required")
class _Harness(unittest.TestCase):
    def setUp(self):
        self.visits, self.now, self.engine = [], [0.0], None
        self.facade = TextFacade(adapter=object())
        self.sid = self.facade.open_session()

    def tearDown(self):
        self.facade.close()

    def fetcher(self):
        def handler(request):
            self.visits.append(str(request.url))
            if request.url.host != "www.iana.org":
                return httpx.Response(403, text="FORBIDDEN")
            body = {"/domains/reserved": "<h1>Reserved</h1><a href='/help/example-domains'>Example</a>",
                    "/help/example-domains": "<h1>Example domains</h1>"}.get(request.url.path)
            if body is None:
                return httpx.Response(404, text="NOT FOUND")
            return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<html>{body}</html>")
        return HttpxFetcher(resolver=lambda host: ["93.184.216.34"], transport=httpx.MockTransport(handler),
                            peer_check=lambda response: True, ssrf=lambda url: None)

    def failing(self, steps, fail_at, exc, advance=0.0):
        """FAKE engine: the ``fail_at``-th generation raises ``exc`` after ``advance`` clock seconds."""
        inner = FakeModel(steps)
        harness = self

        class Engine:
            engine_id = "fake-failing"
            calls = 0

            def generate(self, messages, **kw):
                Engine.calls += 1
                if Engine.calls == fail_at:
                    harness.now[0] += advance
                    raise exc
                return inner.generate(messages, **kw)
        self.engine = Engine()
        return self.engine

    def tick(self, seconds, step):
        def run(m):
            self.now[0] += seconds
            return step(m)
        return run

    def session(self, gate=True):
        return AgentSession(self.engine, "fake", allow={"browse"}, confirm=lambda q: None, actions=None,
                            sites=("www.iana.org",), start_url=I1, browser_fetcher=self.fetcher(),
                            task_preset=PRESET if gate else None, receipts=gate, completion_gate=gate,
                            budgets=Budgets(max_calls=10, deadline_seconds=115), max_turns=10,
                            clock=lambda: self.now[0])

    def run_task(self):
        return TaskEntry(self.facade, public_session_factory=self.session).run_trusted_public_iana_task(
            self.sid, "Consulta as duas páginas da IANA.")

    def states(self, result):
        return {o: (s, seq) for o, s, seq in result.objective_states}


class ErrorPathPreservation(_Harness):
    def test_1_engine_error_before_any_tool(self):
        self.failing([], 1, _engine_unreachable())
        r = self.run_task()
        self.assertEqual((r.operational_state, r.error_code), ("ERROR", "ENGINE_CONNECTION"))
        self.assertEqual(self.states(r), {"IANA_RESERVED": ("MISSING", None), "IANA_EXAMPLE": ("MISSING", None)})
        self.assertEqual((r.receipts_count, r.receipt_events), (0, ()))
        (m,) = r.generation_metrics
        self.assertEqual((m.engine_error, m.prompt_tokens, m.completion_tokens, m.load_seconds),
                         ("ENGINE_CONNECTION", None, None, None))
        self.assertFalse(r.completion_verified)
        self.assertIn("EXECUTION_ERROR", r.limitations)
        self.assertEqual(self.visits, [])

    def test_2_5_6_error_after_a_successful_tool_keeps_receipts_and_partial_objectives(self):
        self.failing([lambda m: call("web_open", url=I1)], 2, RuntimeError(SECRET))
        r = self.run_task()
        self.assertEqual((r.operational_state, r.error_code), ("ERROR", "ENGINE_FAILURE"))
        self.assertEqual(self.states(r), {"IANA_RESERVED": ("PAGE_OBSERVED", 1), "IANA_EXAMPLE": ("MISSING", None)})
        self.assertEqual(r.receipt_events, ((1, "web_open", "OK"),))
        self.assertEqual([m.engine_error for m in r.generation_metrics], [None, "ENGINE_FAILURE"])
        self.assertNotIn("SECRET", repr(r) + r.model_commentary_unverified)

    def test_3_simulated_engine_timeout_reproduces_the_te05_4b_shape(self):
        # two pages observed in ~61 s, then one generation is cut by the 120 s client timeout
        self.failing([self.tick(30, lambda m: call("web_open", url=I1)),
                      self.tick(31, lambda m: call("web_open", url=I2))], 3, _engine_timeout(), advance=120)
        r = self.run_task()
        self.assertEqual((r.operational_state, r.error_code, r.halt_reason_code), ("ERROR", "ENGINE_TIMEOUT", "NONE"))
        self.assertEqual(self.states(r), {"IANA_RESERVED": ("PAGE_OBSERVED", 1), "IANA_EXAMPLE": ("PAGE_OBSERVED", 2)})
        self.assertEqual(r.receipts_count, 2)
        self.assertFalse(r.completion_verified)              # observed pages + ERROR is still not complete
        last = r.generation_metrics[-1]
        self.assertEqual((last.engine_error, last.deadline_overrun_seconds), ("ENGINE_TIMEOUT", 66.0))

    def test_4_generation_past_the_deadline_is_a_halt_not_an_error(self):
        self.failing([self.tick(130, lambda m: call("web_open", url=I1))], 99, None)
        r = self.run_task()
        self.assertEqual((r.operational_state, r.halt_reason_code, r.error_code), ("HALTED", "DEADLINE", "NONE"))
        self.assertEqual(r.receipt_reason_codes, ((1, "DEADLINE"),))
        self.assertEqual(r.generation_metrics[0].deadline_overrun_seconds, 15.0)
        self.assertEqual(self.visits, [])

    def test_7_missing_engine_metrics_are_reported_as_unavailable_not_invented(self):
        self.failing([lambda m: call("web_open", url=I1), lambda m: call("web_open", url=I2),
                      lambda m: {"content": "Feito."}], 99, None)
        r = self.run_task()
        self.assertEqual(r.operational_state, "UNKNOWN_IDENTITY")
        self.assertEqual(r.error_code, "NONE")
        for m in r.generation_metrics:
            self.assertEqual((m.prompt_tokens, m.completion_tokens, m.load_seconds, m.prompt_eval_seconds,
                              m.eval_seconds, m.total_seconds, m.engine_error), (None,) * 7)

    def test_8_premature_answer_stays_incomplete_without_error(self):
        self.failing([lambda m: {"content": "Concluído."}] * 2, 99, None)
        r = self.run_task()
        self.assertEqual((r.operational_state, r.error_code, r.continuations), ("INCOMPLETE", "NONE", 1))

    def test_9_false_completion_then_engine_failure_never_completes(self):
        self.failing([lambda m: {"content": "Li as duas páginas; tarefa concluída e verificada."}], 2,
                     _engine_timeout())
        r = self.run_task()
        self.assertEqual((r.operational_state, r.error_code, r.receipts_count), ("ERROR", "ENGINE_TIMEOUT", 0))
        self.assertEqual({s for _, s, _ in r.objective_states}, {"MISSING"})
        self.assertFalse(r.completion_verified)

    def test_10_unauthorised_tool_refusal_is_preserved_through_an_error(self):
        self.failing([lambda m: call("windows_action", action_id="notepad")], 2, RuntimeError("boom"))
        r = self.run_task()
        self.assertEqual((r.operational_state, r.error_code), ("ERROR", "ENGINE_FAILURE"))
        self.assertEqual(r.receipt_events, ((1, "OTHER", "DENIED"),))
        self.assertEqual(r.receipt_reason_codes, ((1, "CAPABILITY_NOT_AUTHORIZED"),))
        self.assertEqual(self.visits, [])

    def test_11_unexpected_failure_outside_the_engine_yields_a_safe_record(self):
        self.failing([lambda m: call("web_open", url=I1), lambda m: {"content": "ok"}], 99, None)
        with patch.object(AgentSession, "_apply_completion_gate", side_effect=RuntimeError(SECRET)):
            r = self.run_task()
        self.assertEqual((r.operational_state, r.error_code), ("ERROR", "AGENT_FAILURE"))
        self.assertEqual({s for _, s, _ in r.objective_states}, {"UNKNOWN"})   # not trusted, not invented
        self.assertEqual(r.receipt_events, ((1, "web_open", "OK"),))           # but receipts are kept
        self.assertEqual(r.limitations, ("EXECUTION_FAILED",))
        self.assertNotIn("SECRET", repr(r))

    def test_sessions_without_the_gate_keep_their_reply_shape_on_engine_errors(self):
        self.failing([], 1, _engine_timeout())
        agent = self.session(gate=False)
        reply = agent.run("Olá")
        self.assertEqual(reply.completion, "ERROR")
        self.assertIsNone(reply.task_completion)
        self.assertEqual(set(json.loads(reply_json(reply))),
                         {"completion", "halted", "flags", "verification", "sources", "outcomes"})
        self.assertEqual(agent.error_code, "ENGINE_TIMEOUT")

    def test_cli_json_carries_error_diagnostics_without_leaking(self):
        self.failing([lambda m: call("web_open", url=I1)], 2, ValueError(SECRET))
        out = io.StringIO()
        with patch.object(runtime, "prepare_config", return_value={"intelligence": {"default_model": "qwen3.5:2b"}}):
            with redirect_stdout(out):
                code = task_cli.main(["--allow-public-read", "--json"], engine_factory=lambda: self.engine,
                                     session_factory=self.session)
        raw = out.getvalue()
        data = json.loads(raw)
        self.assertEqual(code, 3)
        self.assertEqual((data["operational_state"], data["error_code"]), ("ERROR", "ENGINE_FAILURE"))
        self.assertEqual([o["state"] for o in data["objectives"]], ["PAGE_OBSERVED", "MISSING"])
        self.assertEqual([g["engine_error"] for g in data["generations"]], [None, "ENGINE_FAILURE"])
        self.assertEqual(data["generation_totals"]["engine_errors"], 1)
        for leak in ("SECRET", "evil.example", I1, I2):
            self.assertNotIn(leak, raw)
        verdict = V.decide(raw, code)
        self.assertEqual((verdict["verdict"], verdict["functional_pass"], verdict["error_code"]),
                         ("ERROR", False, "ENGINE_FAILURE"))


class WorkflowVerdict(unittest.TestCase):
    PASS = {"route": "TASK", "operational_state": "UNKNOWN_IDENTITY", "factual_verified": False,
            "completion_verified": False, "error_code": "NONE", "halt_reason_code": "NONE",
            "objectives": [{"id": "IANA_RESERVED", "state": "PAGE_OBSERVED", "receipt_sequence": 1},
                           {"id": "IANA_EXAMPLE", "state": "PAGE_OBSERVED", "receipt_sequence": 2}],
            "receipts_count": 2, "generation_totals": {"wall_seconds": 80.0},
            "timing": {"task_wall_seconds": 81.0, "note": "x"}, "model_commentary": SECRET}

    def run_main(self, task, exit_code):
        with tempfile.TemporaryDirectory() as tmp:
            ev = pathlib.Path(tmp)
            (ev / "exit.txt").write_text(str(exit_code))
            if task is not None:
                (ev / "task.json").write_text(task if isinstance(task, str) else json.dumps(task))
            with redirect_stdout(io.StringIO()):
                rc = V.main([str(ev)])
            return rc, json.loads((ev / "verdict.json").read_text())

    def test_12_review_error_incomplete_blocked_all_fail_the_job(self):
        historical_4b = {**self.PASS, "operational_state": "ERROR", "objectives": [],
                         "limitations": ["INCOMPLETE_OBJECTIVE_EVIDENCE"]}
        historical_4b.pop("error_code")
        cases = {
            "ERROR": (historical_4b, 3),
            "INCOMPLETE": ({**self.PASS, "operational_state": "HALTED", "objectives": [
                self.PASS["objectives"][0], {"id": "IANA_EXAMPLE", "state": "MISSING", "receipt_sequence": None}]}, 3),
            "REVIEW": (self.PASS, 0),                                 # unexpected exit code
            "BLOCKED": (None, 124),                                   # killed before any report
        }
        for expected, (task, code) in cases.items():
            with self.subTest(expected=expected):
                rc, v = self.run_main(task, code)
                self.assertEqual((rc, v["verdict"], v["functional_pass"]), (1, expected, False))

    def test_pass_limited_is_the_only_green_result_and_output_is_whitelisted(self):
        rc, v = self.run_main(self.PASS, 3)
        self.assertEqual((rc, v["verdict"], v["derived_tools_and_overhead_seconds"]), (0, "PASS_LIMITED", 1.0))
        self.assertNotIn("SECRET", json.dumps(v))
        self.assertNotIn("note", v["timing"])
        rc, v = self.run_main({**self.PASS, "completion_verified": True}, 3)   # an impossible claim
        self.assertEqual((rc, v["verdict"]), (1, "REVIEW"))

    def test_live_workflow_fails_on_non_pass_and_still_uploads_evidence(self):
        wf = (ROOT / ".github/workflows/te05e-live-qwen.yml").read_text(encoding="utf-8")
        verdict_step = wf.index("python3 -I labs/te05e_live/verdict.py ev")
        task_step = wf.index("timeout 320 python jarvis.py task")
        upload = wf.index("Preserve bounded evidence")
        self.assertLess(task_step, verdict_step)
        self.assertLess(verdict_step, upload)
        self.assertNotIn("continue-on-error", wf)
        self.assertNotIn("|| true", wf)
        self.assertIn("if: always()", wf[upload - 120:upload + 200])
        self.assertIn("branches: [exp/te05e-live-qwen]", wf)        # never triggered by this PR's branches
        self.assertIn("paths: [ops/te05e_live_model_request.json]", wf)
        self.assertFalse((ROOT / "ops/te05e_live_model_request.json").exists())   # no live request here
        for budget in ("max_calls=10", "deadline_seconds=115", "max_turns=10", "timeout=120"):
            self.assertIn(budget, (ROOT / "rightware/task_cli.py").read_text(encoding="utf-8"))


del _Harness

if __name__ == "__main__":
    unittest.main()
