"""JRV-P2: P1 fixes + goose adapter behind the Control Plane. FAKE/offline only (no Docker, no goose, no model).

The adapter's verdict mapping is exercised on evidence produced by the REAL experimental Gateway (AgentPolicy +
ReceiptLedger + te-p2b.report.v1) in-process with a mocked synthetic catalogue, plus synthetic model-tap and goose
session-store records. Not real-model or real-isolation evidence.
"""
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import httpx
    from labs.te_p1_bakeoff.site import PAGES
    from labs.te_p2a_gateway import fixture_transport as FT
    from labs.te_p2a_gateway.gateway import Gateway
    from labs.te_p2a_gateway.mcp_http import McpApp
    from labs.work07_r3c1.scenarios import FakeModel, call
    from rightware import console as C
    from rightware import control_plane as CP
    from rightware import goose_adapter as G
    from rightware.agent.policy import Budgets
    from rightware.agent.session import AgentSession
    from rightware.text_facade import TextFacade
except ImportError:
    CP = None

SECURE = os.name != "nt" and hasattr(os, "O_NOFOLLOW") and os.open in getattr(os, "supports_dir_fd", set())
BASE = "https://catalog.fixture.example/"
REPORT = {"report_schema_version": "te-p2b.report.v1", "recommendation": "TerraLens", "products": [
    {"name": "AtlasBoard", "mac_support": True, "csv_support": True, "offline": True, "scheduled_automation": False,
     "price_usd_month": 0},
    {"name": "NovaView", "mac_support": True, "csv_support": True, "offline": False, "scheduled_automation": True,
     "price_usd_month": 9},
    {"name": "TerraLens", "mac_support": True, "csv_support": True, "offline": True, "scheduled_automation": True,
     "price_usd_month": 12}],
    "sources": [BASE, BASE + "catalog", BASE + "vendors/atlasboard", BASE + "vendors/novaview",
                BASE + "vendors/terralens-factsheet"]}
GOOD_PROBE = {"probe": {"fixture": "BLOCKED URLError", "internet": "BLOCKED URLError", "gateway": "REACHED 405",
                        "non_goose_initialize": "403"},
              "goose_container": {"networks": ["jrv-agent"], "mounts": []}}


class TextModel:
    def reply(self, text, history):
        return "Texto do modelo."

    def close(self):
        pass


# ------------------------------------------------------------------------------------------ evidence
class Mission:
    """Drives the REAL Gateway in-process like goose would, then writes the evidence files the adapter reads."""

    def __init__(self, out: Path):
        self.out, self.events, self.flaky = out, [], [0]

        def handler(request):
            path = request.url.path
            if path == "/vendors/terralens":
                self.flaky[0] += 1
                code = 503 if self.flaky[0] == 1 else 200
            else:
                code = 200 if path in PAGES else 404
            self.events.append({"path": path, "http_status": code})
            return httpx.Response(code, headers={"content-type": "text/html"},
                                  text=PAGES[path] if code == 200 else "unavailable")
        self.gw = Gateway(task_id="JRV-P2-T1", attempt_id="F1", sites=(FT.SYNTHETIC_HOST,),
                          fetcher=FT.fixture_fetcher(inner=httpx.MockTransport(handler)),
                          budgets=Budgets(max_calls=15, deadline_seconds=1700), report_contract="te-p2b.report.v1")
        self.app, self.rid, self.calls = McpApp(self.gw, out), 0, []
        self.app.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})

    def call(self, name, args):
        self.rid += 1
        self.calls.append(G.EXT_PREFIX + name)
        r = self.app.handle({"jsonrpc": "2.0", "id": self.rid, "method": "tools/call",
                             "params": {"name": name, "arguments": args}})
        return r["result"]["content"][0]["text"]

    @staticmethod
    def link(page, suffix):
        for line in page.splitlines():
            m = re.match(r"(L\d+): .* -> (\S+)$", line)
            if m and m.group(2).endswith(suffix):
                return m.group(1)
        raise AssertionError(suffix)

    def navigate(self, suffixes=("/vendors/atlasboard", "/vendors/novaview", "/vendors/terralens",
                                 "/vendors/terralens-factsheet")):
        root = self.call("web_open", {"url": BASE})
        cat = self.call("web_follow", {"link": self.link(root, "/catalog")})
        for s in suffixes:
            self.call("web_follow", {"link": self.link(cat, s)})

    def finish(self, extra_session_calls=(), forwarded=None, blocked=("load_skill",)):
        self.app._dump()
        (self.out / "http.jsonl").write_text("".join(json.dumps(e) + "\n" for e in self.events))
        fwd = forwarded if forwarded is not None else [G.EXT_PREFIX + t for t in G.GATEWAY_TOOLS]
        (self.out / "model_requests.jsonl").write_text(json.dumps({"forwarded_tool_names": fwd, "tool_names":
                                                                   fwd + ["load_skill"],
                                                                   "blocked_tool_calls_in_model_output": list(blocked)})
                                                       + "\n")
        db = self.out / "goose_state" / "sessions" / "sessions.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(db)
        con.execute("create table messages (id integer primary key, role text, content_json text)")
        for name in self.calls + list(extra_session_calls):
            con.execute("insert into messages (role, content_json) values ('assistant', ?)",
                        (json.dumps([{"type": "toolRequest", "toolCall": {"value": {"name": name}}}]),))
        con.commit()
        con.close()


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class AdapterEvaluation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.m = Mission(self.tmp)

    def outcome(self, run=None, prep=GOOD_PROBE, cancelled=False):
        return G.evaluate(self.tmp, run or {"end": "EXITED"}, prep, cancelled, 1.0)

    def test_full_mission_is_verified_only_from_receipts(self):
        self.m.navigate()
        self.m.call("submit_report", {"report": json.dumps(REPORT)})
        self.m.finish()
        o = self.outcome()
        self.assertEqual((o.state, o.verified, o.operational_state), (CP.State.RESULTADO_VERIFICADO, True,
                                                                       "TASK_VERIFIED_LIMITED"))
        self.assertEqual(o.receipts_count, 7)
        self.assertEqual([e[1] for e in o.receipt_events][-1], "submit_report")
        rec = json.loads((self.tmp / "verification.json").read_text())
        self.assertEqual(rec["blocked_in_model_output"], ["load_skill"])
        self.assertTrue(rec["recovered_from_503"])

    def test_page_failure_without_recovery_is_partial(self):
        self.m.navigate(("/vendors/atlasboard", "/vendors/novaview", "/vendors/terralens"))
        self.m.call("submit_report", {"report": json.dumps(REPORT)})
        self.m.finish()
        o = self.outcome()
        self.assertEqual(o.state, CP.State.EXECUCAO_PARCIAL)
        self.assertFalse(o.verified)

    def test_premature_answer_and_nothing_done(self):
        self.m.call("submit_report", {"report": json.dumps(REPORT)})
        self.m.finish()
        self.assertEqual(self.outcome().state, CP.State.RESULTADO_DESCONHECIDO)

    def test_wrong_report_values_are_not_verified(self):
        self.m.navigate()
        bad = json.loads(json.dumps(REPORT))
        bad["products"][1]["offline"] = True
        self.m.call("submit_report", {"report": json.dumps(bad)})
        self.m.finish()
        self.assertEqual(self.outcome().state, CP.State.EXECUCAO_PARCIAL)

    def test_tools_outside_allowlist_and_manipulated_parameters_never_execute(self):
        for name, args in (("load_skill", {"name": "goose-doc-guide"}), ("developer__shell", {"command": "id"}),
                           ("web_open", {"url": "https://example.com/"}), ("web_open", {"url": BASE, "extra": 1}),
                           ("web_follow", {"link": "../../etc"})):
            with self.subTest(name=name, args=args):
                self.m.call(name, args)
                r = self.m.gw.receipts()[-1]
                self.assertFalse(r.executed and r.status == "OK")
        self.assertEqual(self.m.events, [])

    def test_non_gateway_execution_or_inventory_is_a_failure(self):
        self.m.navigate()
        self.m.call("submit_report", {"report": json.dumps(REPORT)})
        self.m.finish(extra_session_calls=["load_skill"])
        o = self.outcome()
        self.assertEqual((o.state, o.error_code), (CP.State.EXECUCAO_FALHADA, "ISOLATION_OR_INVENTORY_VIOLATION"))
        self.assertFalse(o.verified)
        m2 = Mission(Path(tempfile.mkdtemp(dir=self.tmp)))
        m2.navigate()
        m2.call("submit_report", {"report": json.dumps(REPORT)})
        m2.finish(forwarded=[G.EXT_PREFIX + "web_open", "load_skill"])
        self.assertEqual(G.evaluate(m2.out, {"end": "EXITED"}, GOOD_PROBE, False, 1.0).state, CP.State.EXECUCAO_FALHADA)

    def test_isolation_problems_are_detected(self):
        for key, value in (("fixture", "REACHED 200"), ("internet", "REACHED 200"), ("gateway", "BLOCKED x"),
                           ("non_goose_initialize", "200")):
            with self.subTest(key=key):
                bad = {**GOOD_PROBE, "probe": {**GOOD_PROBE["probe"], key: value}}
                self.assertTrue(G.isolation_problems(bad))
        for gc in ({"networks": ["jrv-agent", "bridge"], "mounts": []}, {"networks": ["jrv-agent"],
                                                                          "mounts": [{"Source": "/home"}]}):
            self.assertTrue(G.isolation_problems({**GOOD_PROBE, "goose_container": gc}))
        self.assertEqual(G.isolation_problems(GOOD_PROBE), [])

    def test_inconsistent_or_missing_receipts_are_unknown(self):
        self.m.navigate()
        self.m.call("submit_report", {"report": json.dumps(REPORT)})
        self.m.finish()
        with (self.tmp / "http.jsonl").open("a") as f:                     # traffic without a receipt
            f.write(json.dumps({"path": "/catalog", "http_status": 200}) + "\n")
        o = self.outcome()
        self.assertEqual((o.state, o.error_code), (CP.State.RESULTADO_DESCONHECIDO, "EVIDENCE_INCONSISTENT"))
        (self.tmp / "receipts.jsonl").write_text("")                         # receipts lost
        self.assertFalse(self.outcome().verified)

    def test_tampered_submission_is_not_verified(self):
        self.m.navigate()
        self.m.call("submit_report", {"report": json.dumps(REPORT)})
        self.m.finish()
        rows = [json.loads(x) for x in (self.tmp / "submissions.jsonl").read_text().splitlines()]
        rows[0]["report"] = rows[0]["report"].replace("TerraLens", "NovaView", 1)
        (self.tmp / "submissions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.assertFalse(self.outcome().verified)

    def test_duplicate_submission_is_not_a_second_effect(self):
        self.m.navigate()
        self.m.call("submit_report", {"report": json.dumps(REPORT)})
        self.m.call("submit_report", {"report": json.dumps(REPORT)})
        self.m.finish()
        o = self.outcome()
        self.assertEqual(o.state, CP.State.RESULTADO_VERIFICADO)
        self.assertEqual(len(self.m.gw.submissions), 1)

    def test_cancel_and_timeout(self):
        self.m.navigate(("/vendors/atlasboard",))
        self.m.finish()
        self.assertEqual(self.outcome(run={"end": "CANCELLED"}).state, CP.State.TAREFA_CANCELADA)
        o = self.outcome(run={"end": "TIMED_OUT"})
        self.assertEqual((o.state, o.halt_reason_code), (CP.State.EXECUCAO_PARCIAL, "DEADLINE"))


class FakeRunner:
    def __init__(self, prep=GOOD_PROBE, run=None, prepare_error=None, block=None):
        self.prep, self.run_result, self.prepare_error, self.block = prep, run or {"end": "EXITED"}, prepare_error, block
        self.started = self.cleaned = self.stopped = 0

    def prepare(self):
        if self.prepare_error:
            raise self.prepare_error
        return self.prep

    def run_goose(self, cancelled, timeout):
        self.started += 1
        if self.block:
            self.block.wait(5)
        return {"end": "CANCELLED"} if cancelled.is_set() else self.run_result

    def stop(self):
        self.stopped += 1

    def cleanup(self):
        self.cleaned += 1


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class MissionCapability(unittest.TestCase):
    def mission(self, runner):
        self.runner = runner
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        return G.GooseMission(G.GooseRuntime(Path("/x/goose"), Path("/x/ollama"), Path("/x/models")),
                              evidence_root=root, runner_factory=lambda out: runner)

    def plane(self, mission):
        cp = CP.ControlPlane(TextFacade(adapter=TextModel()), goose=mission)
        self.addCleanup(cp.close)
        return cp

    def test_bad_isolation_never_starts_goose(self):
        r = FakeRunner(prep={**GOOD_PROBE, "probe": {**GOOD_PROBE["probe"], "internet": "REACHED 200"}})
        cp = self.plane(self.mission(r))
        _, code = cp.request(G.CAPABILITY)
        o = cp.authorize_and_run(code)
        self.assertEqual((o.state, o.error_code), (CP.State.EXECUCAO_FALHADA, "ISOLATION_OR_INVENTORY_VIOLATION"))
        self.assertEqual((r.started, r.cleaned), (0, 1))

    def test_preparation_error_is_a_failure_and_cleans_up(self):
        r = FakeRunner(prepare_error=RuntimeError("GATEWAY_IMAGE_MISSING"))
        cp = self.plane(self.mission(r))
        _, code = cp.request(G.CAPABILITY)
        o = cp.authorize_and_run(code)
        self.assertEqual((o.state, o.error_code), (CP.State.EXECUCAO_FALHADA, "INTERNAL_RUNTIMEERROR"))
        self.assertEqual(r.cleaned, 1)
        self.assertFalse(cp.running)

    def test_unauthorised_run_and_cancel(self):
        block = threading.Event()
        r = FakeRunner(block=block)
        m = self.mission(r)
        cp = self.plane(m)
        self.assertEqual(cp.authorize_and_run("ABCDEF"), CP.Refusal(CP.State.TAREFA_NAO_AUTORIZADA, "CODE_INVALID"))
        self.assertEqual(r.started, 0)
        _, code = cp.request(G.CAPABILITY)
        box = {}
        t = threading.Thread(target=lambda: box.update(o=cp.authorize_and_run(code)))
        t.start()
        for _ in range(50):
            if r.started:
                break
            time.sleep(0.02)
        self.assertTrue(cp.cancel())
        block.set()
        t.join(5)
        self.assertEqual(r.stopped, 1)
        self.assertEqual(box["o"].state, CP.State.TAREFA_CANCELADA)
        self.assertFalse(cp.cancel())

    def test_off_by_default_and_host_only(self):
        cp = self.plane(None)
        self.assertNotIn(G.CAPABILITY, cp.capabilities)
        self.assertEqual(cp.request(G.CAPABILITY), (CP.State.TAREFA_NAO_AUTORIZADA, ""))
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            C.main(["--missao-goose"], adapter=TextModel(), input_fn=lambda p: "/sair", out=io.StringIO())

    def test_runner_commands_isolation(self):
        rt = G.GooseRuntime(Path("/h/goose"), Path("/h/ollama"), Path("/h/models"))
        cmds = G.DockerGooseRunner(rt, Path("/tmp/p2-x")).commands()
        goose = cmds["goose"]
        self.assertNotIn("-v", goose)
        self.assertEqual(goose[goose.index("--network") + 1], G.AGENT_NET)
        self.assertEqual(goose[goose.index("--ip") + 1], G.GOOSE_IP)
        self.assertIn("--no-profile", goose)
        self.assertEqual(goose.count("--with-streamable-http-extension"), 1)
        self.assertIn("no-new-privileges", goose)
        self.assertFalse(any("shell" in a or "developer" in a for a in goose))
        self.assertEqual(cmds["fixture"][cmds["fixture"].index("--network") + 1], G.FIXTURE_NET)
        tap = cmds["ollama-tap"]
        self.assertEqual([tap[i + 1] for i, a in enumerate(tap) if a == "--allow-suffix"],
                         ["__" + t for t in G.GATEWAY_TOOLS])
        gw = cmds["gateway"]
        self.assertEqual(gw[gw.index("--allow-client") + 1], G.GOOSE_IP)
        calls = []
        with mock.patch.object(G, "sh", side_effect=lambda a, **k: calls.append(a) or mock.Mock(returncode=0,
                                                                                               stdout="[{}]")), \
                mock.patch.object(G.time, "sleep"), mock.patch.object(G.DockerGooseRunner, "probe", return_value={}):
            G.DockerGooseRunner(rt, Path("/tmp/p2-x")).prepare()
        creates = [c for c in calls if c[:3] == ["docker", "network", "create"]]
        self.assertTrue(creates and all("--internal" in c for c in creates))


# ------------------------------------------------------------------------------------------ P1 fixes
@unittest.skipIf(CP is None or not SECURE, "pinned venv and POSIX secure-open required (TE-06A)")
class P1Fixes(unittest.TestCase):
    def builder(self, steps=None):
        steps = steps or [lambda m: call("fixture_read", file="A"), lambda m: call("fixture_read", file="B"),
                          lambda m: call("fixture_compare"), lambda m: {"content": "Há 3 alterações."}]

        def b(model, ws, ab):
            def make():
                agent = AgentSession(FakeModel(list(steps)), "fake", allow={"files"}, confirm=lambda q: None,
                                     receipts=True, file_task="fixture-two-versions-compare",
                                     file_workspace=ws["ws"].workspace,
                                     budgets=Budgets(max_calls=6, deadline_seconds=60), max_turns=6)
                ab["agent"] = agent
                return agent
            return make
        return b

    def plane(self, builder=None):
        cp = CP.ControlPlane(TextFacade(adapter=TextModel()), enable_trial_compare=True,
                             session_factory_builder=builder or self.builder())
        self.addCleanup(cp.close)
        return cp

    def test_fix1_verified_state_prevails_over_host_status_lines(self):
        cp = self.plane()
        _, code = cp.request(CP.TRIAL_COMPARE)
        o = cp.authorize_and_run(code)
        self.assertEqual(o.state, CP.State.RESULTADO_VERIFICADO)
        self.assertNotIn("não foi possível concluir", o.model_commentary_unverified)
        self.assertNotIn("Estado da tarefa", o.model_commentary_unverified)
        self.assertIn("Há 3 alterações.", o.model_commentary_unverified)
        self.assertEqual(CP.model_text_only("a\nEstado: x\n  Estado da tarefa (t): y\nb"), "a\nb")
        self.assertEqual(CP.model_text_only("O Estado: é uma palavra"), "O Estado: é uma palavra")

    def test_fix2_preparation_failure_cleans_and_resets(self):
        made = []
        real = CP.tempfile.mkdtemp
        with mock.patch.object(CP.tempfile, "mkdtemp", side_effect=lambda **k: made.append(real(**k)) or made[-1]), \
                mock.patch("rightware.agent.file_task.FixtureWorkspace", side_effect=OSError("disk")):
            cp = self.plane()
            _, code = cp.request(CP.TRIAL_COMPARE)
            o = cp.authorize_and_run(code)
        self.assertEqual((o.state, o.error_code), (CP.State.EXECUCAO_FALHADA, "INTERNAL_OSERROR"))
        self.assertFalse(cp.running)
        self.assertTrue(made and not any(Path(d).exists() for d in made))
        _, code = cp.request(CP.TRIAL_COMPARE)                               # usable again afterwards
        self.assertEqual(cp.authorize_and_run(code).state, CP.State.RESULTADO_VERIFICADO)

    def test_fix3_banner_and_capabilities_reflect_the_active_mode(self):
        out = io.StringIO()
        feed = ["/capacidades"]
        C.main([], adapter=TextModel(), input_fn=lambda p: feed.pop(0) if feed else (_ for _ in ()).throw(EOFError),
               out=out, session_factory_builder=self.builder())
        text = out.getvalue()
        self.assertIn("Modo com tarefas supervisionadas: o anfitrião activou comparar-versoes-ensaio", text)
        self.assertNotIn("Sem ferramentas: não abro ficheiros", text)
        self.assertIn("Tarefas supervisionadas activadas pelo anfitrião", text)
        plain = io.StringIO()
        C.main([], adapter=TextModel(), input_fn=lambda p: (_ for _ in ()).throw(EOFError), out=plain)
        self.assertIn("Sem ferramentas: não abro ficheiros", plain.getvalue())

    def test_fix4_internal_error_is_failure_not_authorization(self):
        cp = self.plane()
        with mock.patch.object(cp.entry, "run_trusted_file_compare", side_effect=RuntimeError("boom")):
            _, code = cp.request(CP.TRIAL_COMPARE)
            o = cp.authorize_and_run(code)
        self.assertEqual((o.state, o.error_code), (CP.State.EXECUCAO_FALHADA, "INTERNAL_RUNTIMEERROR"))
        out = io.StringIO()
        con = C.Console(cp.entry, "m", out, cp)
        with mock.patch.object(cp, "authorize_and_run", side_effect=ValueError("bug")):
            con.task_authorize("ABCDEF")
        self.assertIn("[Execução falhada]", out.getvalue())
        self.assertNotIn("Código inválido", out.getvalue())

    def test_fix5_concurrency_is_atomic(self):
        gate = threading.Event()

        def slow(m):
            gate.wait(5)
            return call("fixture_read", file="A")
        cp = self.plane(self.builder([slow, lambda m: {"content": "fim"}]))
        _, code1 = cp.request(CP.TRIAL_COMPARE)
        box = {}
        t = threading.Thread(target=lambda: box.update(o=cp.authorize_and_run(code1)))
        t.start()
        for _ in range(100):
            if cp.running:
                break
            time.sleep(0.01)
        _, code2 = cp.request(CP.TRIAL_COMPARE)
        self.assertEqual(cp.authorize_and_run(code2), CP.Refusal(CP.State.TAREFA_NAO_AUTORIZADA, "BUSY"))
        gate.set()
        t.join(10)
        self.assertIsInstance(box["o"], CP.TaskOutcome)
        self.assertFalse(cp.running)


if __name__ == "__main__":
    unittest.main()
