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
MID = "0a1b2c3d"
AGENT = f"jrv-p2-{MID}-agent"
GOOD_PROBE = {"probe": {"fixture": "BLOCKED URLError", "internet": "BLOCKED URLError", "gateway": "REACHED 405",
                        "non_goose_initialize": "403"},
              "goose_container": {"networks": [AGENT], "mounts": [], "label": MID},
              "mission": MID, "agent_network": AGENT, "baseline": []}
# Operational success of the goose PROCESS as run_goose reports it (R1 gate 2).
OK_RUN = {"end": "EXITED", "exit_code": 0, "status": "exited", "seconds": 1.0, "state_copied": True}


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
        for name in G.HOST_BASELINE:                     # created empty by the host before any container (R1)
            (out / name).touch()

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
                          budgets=Budgets(max_calls=15, deadline_seconds=1700), report_contract="te-p2b.report.v1",
                          audit_path=out / "audit.jsonl")
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
        return G.evaluate(self.tmp, run or OK_RUN, prep, cancelled, 1.0)

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
        self.assertEqual(G.evaluate(m2.out, OK_RUN, GOOD_PROBE, False, 1.0).state, CP.State.EXECUCAO_FALHADA)

    def test_isolation_problems_are_detected(self):
        for key, value in (("fixture", "REACHED 200"), ("internet", "REACHED 200"), ("gateway", "BLOCKED x"),
                           ("non_goose_initialize", "200")):
            with self.subTest(key=key):
                bad = {**GOOD_PROBE, "probe": {**GOOD_PROBE["probe"], key: value}}
                self.assertTrue(G.isolation_problems(bad))
        for gc in ({"networks": [AGENT, "bridge"], "mounts": [], "label": MID},
                   {"networks": [AGENT], "mounts": [{"Source": "/home"}], "label": MID},
                   {"networks": ["jrv-agent"], "mounts": [], "label": MID},          # another mission's network
                   {"networks": [AGENT], "mounts": [], "label": "ffffffff"}):        # not this mission's goose
            self.assertTrue(G.isolation_problems({**GOOD_PROBE, "goose_container": gc}))
        self.assertTrue(G.isolation_problems({**GOOD_PROBE, "baseline": ["receipts.jsonl: MISSING"]}))
        self.assertTrue(G.isolation_problems({k: v for k, v in GOOD_PROBE.items() if k != "mission"}))
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
        self.assertEqual(self.outcome(run={**OK_RUN, "end": "CANCELLED", "exit_code": 137}).state,
                         CP.State.TAREFA_CANCELADA)
        o = self.outcome(run={**OK_RUN, "end": "TIMED_OUT", "exit_code": 137})
        self.assertEqual((o.state, o.halt_reason_code, o.error_code),
                         (CP.State.EXECUCAO_PARCIAL, "DEADLINE", "PROCESS_TIMED_OUT"))


class FakeRunner:
    def __init__(self, prep=GOOD_PROBE, run=None, prepare_error=None, block=None):
        self.prep, self.run_result, self.prepare_error, self.block = prep, run or OK_RUN, prepare_error, block
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
        self.assertEqual((o.state, o.error_code), (CP.State.EXECUCAO_FALHADA, "GATEWAY_IMAGE_MISSING"))
        self.assertEqual((r.started, r.cleaned), (0, 1))
        r2 = FakeRunner(prepare_error=RuntimeError("GATEWAY_NOT_READY"))
        cp2 = self.plane(self.mission(r2))
        _, code = cp2.request(G.CAPABILITY)
        o = cp2.authorize_and_run(code)
        self.assertEqual((o.state, o.error_code, o.verified), (CP.State.EXECUCAO_FALHADA, "GATEWAY_NOT_READY", False))
        self.assertEqual((r2.started, r2.cleaned), (0, 1))
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

    def test_console_renders_a_verified_goose_outcome_without_changes(self):
        cp = self.plane(self.mission(FakeRunner()))
        verified = CP.TaskOutcome(CP.State.RESULTADO_VERIFICADO, G.CAPABILITY, "TASK_VERIFIED_LIMITED", True, None,
                                  (("CATALOG", "PAGE_OBSERVED", 2),), 7, ((1, "web_open", "OK"),), "NONE", "NONE",
                                  "Relatório submetido pelo goose: {}", 1.0)
        out = io.StringIO()
        con = C.Console(cp.entry, "m", out, cp)
        with mock.patch.object(cp, "authorize_and_run", return_value=verified):
            con.task_authorize("ABCDEF")                      # found by the REAL run: must not crash on changes=None
        text = out.getvalue()
        self.assertIn("[Resultado verificado por evidência (recibos + verificador RIGHTWARE)]", text)
        self.assertIn("Estado do executor: TASK_VERIFIED_LIMITED", text)
        self.assertNotIn("Alterações (calculadas", text)
        self.assertIn("Comentário do modelo (NÃO verificado):", text)

    def test_off_by_default_and_host_only(self):
        cp = self.plane(None)
        self.assertNotIn(G.CAPABILITY, cp.capabilities)
        self.assertEqual(cp.request(G.CAPABILITY), (CP.State.TAREFA_NAO_AUTORIZADA, ""))
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            C.main(["--missao-goose"], adapter=TextModel(), input_fn=lambda p: "/sair", out=io.StringIO())

    def test_runner_commands_isolation(self):
        rt = G.GooseRuntime(Path("/h/goose"), Path("/h/ollama"), Path("/h/models"))
        r = G.DockerGooseRunner(rt, Path("/tmp/p2-x"), mission_id=MID)
        cmds = r.commands()
        goose = cmds["goose"]
        self.assertNotIn("-v", goose)
        self.assertEqual(goose[goose.index("--network") + 1], r.net["agent"])
        self.assertEqual(goose[goose.index("--ip") + 1], r.goose_ip)
        self.assertTrue(r.goose_ip.startswith(r.subnet.rsplit(".", 1)[0] + "."))
        self.assertIn("--no-profile", goose)
        self.assertEqual(goose.count("--with-streamable-http-extension"), 1)
        self.assertIn("no-new-privileges", goose)
        self.assertFalse(any("shell" in a or "developer" in a for a in goose))
        self.assertEqual(cmds["fixture"][cmds["fixture"].index("--network") + 1], r.net["fixture"])
        tap = cmds["ollama-tap"]
        self.assertEqual([tap[i + 1] for i, a in enumerate(tap) if a == "--allow-suffix"],
                         ["__" + t for t in G.GATEWAY_TOOLS])
        gw = cmds["gateway"]
        self.assertEqual(gw[gw.index("--allow-client") + 1], r.goose_ip)
        for role, c in cmds.items():                          # every resource is named AND labelled per mission
            with self.subTest(role=role):
                self.assertEqual(c[c.index("--name") + 1], f"jrv-p2-{MID}-{role}")
                self.assertEqual(c[c.index("--label") + 1], f"{G.LABEL}={MID}")
                if role != "goose":                           # in-mission DNS names kept as aliases
                    self.assertEqual(c[c.index("--network-alias") + 1], role)


class FakeDocker:
    """In-memory Docker daemon for the runner's fixed argument lists. Resolves names and ids like Docker does,
    refuses name conflicts, and emulates the Gateway's first evidence dump when the probe's refused request hits it."""

    def __init__(self, out=None, *, fail_role=None, ready=True, exit_code=0, start_rc=0, state_rc=0, cp_rc=0,
                 running_polls=1, running_rc=0):
        self.out, self.fail_role, self.ready, self.running_rc = out, fail_role, ready, running_rc
        self.exit_code, self.start_rc, self.state_rc, self.cp_rc, self.running_polls = (exit_code, start_rc, state_rc,
                                                                                       cp_rc, running_polls)
        self.res, self.calls, self.n = {}, [], 0

    def add(self, kind, name, label=None):
        self.n += 1
        rid = f"{self.n:064x}"
        self.res[rid] = {"kind": kind, "name": name, "labels": {G.LABEL: label} if label else {}, "running": False,
                         "nets": []}
        return rid

    def find(self, ref, kind=None):
        for rid, r in self.res.items():
            if (rid == ref or r["name"] == ref) and (kind is None or r["kind"] == kind):
                return rid
        return None

    @staticmethod
    def ok(stdout="", rc=0):
        return mock.Mock(returncode=rc, stdout=stdout, stderr="")

    def _label(self, args):
        return args[args.index("--label") + 1].split("=", 1)[1] if "--label" in args else None

    def __call__(self, args, **kw):
        self.calls.append(list(args))
        a = args[1:]
        if a[:2] == ["image", "inspect"]:
            return self.ok("[{}]")
        if a[:2] == ["network", "create"]:
            if self.find(a[-1], "network"):
                return self.ok(rc=1)
            return self.ok(self.add("network", a[-1], self._label(a)) + "\n")
        if a[:2] == ["network", "connect"]:
            rid = self.find(a[-1], "container")
            return self.ok(rc=0 if rid else 1)
        if a[:2] == ["network", "rm"] or a[:2] == ["rm", "-f"]:
            rid = self.find(a[2], "network" if a[0] == "network" else "container")
            if rid:
                del self.res[rid]
            return self.ok(rc=0 if rid else 1)
        if a[:2] == ["network", "inspect"] or a[:2] == ["container", "inspect"]:
            rid = self.find(a[-1], a[0])
            return self.ok(self.res[rid]["labels"].get(G.LABEL, "") + "\n" if rid else "", 0 if rid else 1)
        if a[:1] == ["run"] and "--rm" in a:                  # probe containers (labelled, removed by Docker)
            if "initialize" in a[-1]:
                if self.out is not None:                      # the Gateway refuses and dumps its evidence
                    for name in G.GATEWAY_BASELINE:
                        (self.out / name).write_text("")
                    (self.out / "transport_rejections.jsonl").write_text(
                        json.dumps({"client": "172.30.0.2", "code": 403, "reason": "client not allowed"}) + "\n")
                return self.ok("403\n")
            return self.ok(json.dumps(GOOD_PROBE["probe"]) + "\n")
        if a[:1] in (["run"], ["create"]):
            name = a[a.index("--name") + 1]
            if self.fail_role and name.endswith("-" + self.fail_role):
                return self.ok(rc=125)
            if self.find(name, "container"):
                return self.ok(rc=125)                        # name conflict: Docker refuses, nothing created
            rid = self.add("container", name, self._label(a))
            self.res[rid]["nets"] = [a[a.index("--network") + 1]]
            self.res[rid]["running"] = a[0] == "run"
            return self.ok(rid + "\n")
        if a[:1] == ["logs"]:
            return self.ok('{"gateway": "http://0.0.0.0:8790/mcp"}\n' if self.ready else "")
        if a[:1] == ["cp"]:                                   # cp_rc: failure to copy goose's state OUT
            return self.ok(rc=self.cp_rc if a[1].endswith(":/root/.local/share/goose") else 0)
        if a[:1] == ["start"]:
            rid = self.find(a[1], "container")
            if rid and not self.start_rc:
                self.res[rid]["running"] = True
            return self.ok(rc=self.start_rc if rid else 1)
        if a[:1] in (["stop"], ["kill"]):
            rid = self.find(a[-1], "container")
            if rid:
                self.res[rid]["running"] = False
            return self.ok(rc=0 if rid else 1)
        if a[:2] == ["inspect", "-f"]:
            rid = self.find(a[-1], "container")
            if a[2] == "{{.State.Running}}":
                if not rid or (self.running_rc and "goose" in self.res[rid]["name"]):
                    return self.ok(rc=1)
                if self.res[rid]["running"] and "goose" in self.res[rid]["name"] and self.running_polls is not None:
                    self.running_polls -= 1
                    if self.running_polls < 0:
                        self.res[rid]["running"] = False
                return self.ok("true\n" if self.res[rid]["running"] else "false\n")
            if a[2].startswith("{{.State.ExitCode}}"):
                if self.state_rc or not rid:
                    return self.ok(rc=1)
                return self.ok(f"{self.exit_code} exited\n")
        if a[:1] == ["inspect"]:
            rid = self.find(a[1], "container")
            if not rid:
                return self.ok("[]", 1)
            r = self.res[rid]
            return self.ok(json.dumps([{"NetworkSettings": {"Networks": {n: {"IPAMConfig": {}} for n in r["nets"]}},
                                        "Mounts": [], "Config": {"Labels": r["labels"]}}]))
        raise AssertionError(f"unexpected docker command {args}")


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class DockerRunnerR1(unittest.TestCase):
    """R1 gates 1, 2 and 4 on the runner's real command sequence against an in-memory daemon (FAKE: no Docker)."""

    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.out, ignore_errors=True))
        self.rt = G.GooseRuntime(Path("/h/goose"), Path("/h/ollama"), Path("/h/models"))

    def runner(self, docker, mid=MID):
        r = G.DockerGooseRunner(self.rt, self.out, mission_id=mid)
        self.patch = mock.patch.object(G, "sh", side_effect=docker)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        mock.patch.object(G.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)
        return r

    def external(self, d):
        """Pre-existing resources NOT created by this mission, including look-alike names and another mission."""
        names = ["gateway", "goose", "ollama", "fixture", "ollama-tap", "jrv-p2-gateway", "jrv-p2-x-gateway",
                 f"jrv-p2-{MID}-gateway-old", "jrv-p2-ffffffff-goose"]
        ids = {d.add("container", n, "ffffffff" if "ffffffff" in n else None) for n in names}
        ids |= {d.add("network", n) for n in ("jrv-agent", "jrv-fixture", "jrv-p2-ffffffff-agent")}
        return ids

    # ---- gate 1: ownership
    def test_unique_mission_ids_names_and_subnets(self):
        a = G.DockerGooseRunner(self.rt, self.out)
        b = G.DockerGooseRunner(self.rt, self.out)
        self.assertNotEqual(a.mission, b.mission)
        self.assertTrue(set(a.name.values()).isdisjoint(b.name.values()))
        self.assertTrue(set(a.net.values()).isdisjoint(b.net.values()))
        with self.assertRaises(ValueError):
            G.DockerGooseRunner(self.rt, self.out, mission_id="gateway; rm")

    def test_full_lifecycle_touches_only_its_own_resources(self):
        d = FakeDocker(self.out)
        before = self.external(d)
        r = self.runner(d)
        prep = r.prepare()
        self.assertEqual(G.isolation_problems(prep), [])
        self.assertEqual(len(r.created), 7)                                 # 2 networks + 5 containers
        self.assertTrue(all(d.res[rid]["labels"] == {G.LABEL: MID} for _, rid in r.created))
        creates = [c for c in d.calls if c[1:3] == ["network", "create"]]
        self.assertEqual(len(creates), 2)
        self.assertTrue(all("--internal" in c for c in creates))             # both networks have no route out
        self.assertEqual(r.run_goose(threading.Event())["end"], "EXITED")
        removed = r.cleanup()
        self.assertEqual(len(removed), 7)
        self.assertEqual(set(d.res), before)                                # every external resource intact
        destructive = [c for c in d.calls if c[1:3] in (["rm", "-f"], ["network", "rm"])]
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", c[-1]) for c in destructive))   # by id, never by name
        self.assertFalse(any(c[1] in ("stop", "kill") and c[-1] in ("goose", "gateway") for c in d.calls))

    def test_failed_preparation_cleans_only_what_it_created(self):
        for role in ("ollama", "ollama-tap", "fixture", "gateway", "goose"):
            with self.subTest(role=role):
                d = FakeDocker(self.out, fail_role=role)
                before = self.external(d)
                r = self.runner(d, mid=f"{G.ROLES.index(role) + 1:08x}")
                with self.assertRaises(RuntimeError) as cm:
                    r.prepare()
                self.assertEqual(str(cm.exception), "DOCKER_CREATE_FAILED:container")
                self.assertEqual(len(r.created), 2 + G.ROLES.index(role))     # only successful creates recorded
                self.assertTrue(all(rid in d.res for _, rid in r.created))
                r.cleanup()
                self.assertEqual(set(d.res), before)
                mock.patch.stopall()

    def test_name_conflict_with_an_external_container_is_not_adopted(self):
        d = FakeDocker(self.out)
        squatter = d.add("container", f"jrv-p2-{MID}-gateway", MID)      # same name AND label, not created here
        r = self.runner(d)
        with self.assertRaises(RuntimeError):
            r.prepare()
        self.assertNotIn(squatter, [rid for _, rid in r.created])
        r.cleanup()
        self.assertIn(squatter, d.res)
        self.assertEqual({x["name"] for x in d.res.values()}, {f"jrv-p2-{MID}-gateway"})

    def test_cleanup_skips_a_resource_whose_label_no_longer_matches(self):
        d = FakeDocker(self.out)
        r = self.runner(d)
        r.prepare()
        kind, rid = r.created[2]
        d.res[rid]["labels"] = {G.LABEL: "ffffffff"}
        r.cleanup()
        self.assertEqual(set(d.res), {rid})

    # ---- gate 4: readiness
    def test_readiness_failure_stops_before_goose_exists(self):
        d = FakeDocker(self.out, ready=False)
        r = self.runner(d)
        clock = iter(range(0, 10_000, 5))
        with mock.patch.object(G.time, "monotonic", side_effect=lambda: next(clock)), \
                self.assertRaises(RuntimeError) as cm:
            r.prepare()
        self.assertEqual(str(cm.exception), "GATEWAY_NOT_READY")
        self.assertFalse(any(c[1] == "create" for c in d.calls))           # goose never created
        self.assertFalse(any("--rm" in c for c in d.calls))                # nor probed as if isolated
        self.assertEqual(r.run_goose(threading.Event())["end"], "START_FAILED")
        r.cleanup()
        self.assertEqual(d.res, {})

    def test_probe_is_still_mandatory_after_readiness(self):
        d = FakeDocker(self.out)
        r = self.runner(d)
        leaky = {**GOOD_PROBE["probe"], "internet": "REACHED 200"}
        with mock.patch.object(G.DockerGooseRunner, "probe", return_value=leaky):
            prep = r.prepare()
        self.assertIn("goose network reaches the internet", G.isolation_problems(prep))

    # ---- gate 2: real process outcome
    def run_with(self, **kw):
        d = FakeDocker(self.out, **kw)
        r = self.runner(d)
        r.prepare()
        return r.run_goose(threading.Event())

    def test_process_outcomes_are_collected_not_inferred(self):
        self.assertEqual(self.run_with()["exit_code"], 0)
        self.assertTrue(G.process_ok(self.run_with()))
        run = self.run_with(exit_code=1)
        self.assertEqual((run["end"], run["exit_code"], G.process_ok(run)), ("EXITED", 1, False))
        self.assertEqual(self.run_with(start_rc=1)["end"], "START_FAILED")
        self.assertEqual(self.run_with(state_rc=1)["end"], "STATE_UNKNOWN")
        run = self.run_with(running_rc=1)                 # cannot observe the process: never "exited"
        self.assertEqual((run["end"], G.process_ok(run)), ("STATE_UNKNOWN", False))
        run = self.run_with(cp_rc=1)
        self.assertEqual((run["state_copied"], G.process_ok(run)), (False, False))

    def test_timeout_and_cancel_are_explicit(self):
        d = FakeDocker(self.out, running_polls=None)                       # never exits by itself
        r = self.runner(d)
        r.prepare()
        clock = iter(range(0, 10_000, 5))
        with mock.patch.object(G.time, "monotonic", side_effect=lambda: next(clock)):
            run = r.run_goose(threading.Event(), timeout=20)
        self.assertEqual(run["end"], "TIMED_OUT")
        self.assertTrue(any(c[1] == "kill" for c in d.calls))
        ev = threading.Event()
        ev.set()
        d.res[r.created[-1][1]]["running"] = True
        self.assertEqual(r.run_goose(ev)["end"], "CANCELLED")


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class CompletionAndEvidenceR1(unittest.TestCase):
    """R1 gates 2 and 3: a complete, valid receipt set is NOT enough; the process and the evidence must be too."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def full(self):
        m = Mission(Path(tempfile.mkdtemp(dir=self.tmp)))
        m.navigate()
        m.call("submit_report", {"report": json.dumps(REPORT)})
        m.finish()
        return m.out

    def ev(self, out, run=OK_RUN):
        return G.evaluate(out, run, GOOD_PROBE, False, 1.0)

    def test_control_full_mission_with_clean_process_is_verified(self):
        self.assertEqual(self.ev(self.full()).state, CP.State.RESULTADO_VERIFICADO)

    def test_complete_receipts_never_rescue_a_failed_process(self):
        for run, state, err in (
                ({**OK_RUN, "end": "TIMED_OUT", "exit_code": 137}, CP.State.EXECUCAO_PARCIAL, "PROCESS_TIMED_OUT"),
                ({**OK_RUN, "exit_code": 1}, CP.State.EXECUCAO_FALHADA, "PROCESS_EXIT_NONZERO"),
                ({**OK_RUN, "exit_code": None, "status": None}, CP.State.EXECUCAO_FALHADA, "PROCESS_STATE_UNKNOWN"),
                ({**OK_RUN, "end": "STATE_UNKNOWN", "exit_code": None}, CP.State.EXECUCAO_FALHADA,
                 "PROCESS_STATE_UNKNOWN"),
                ({**OK_RUN, "state_copied": False}, CP.State.EXECUCAO_FALHADA, "PROCESS_STATE_UNKNOWN"),
                ({"end": "START_FAILED", "exit_code": None}, CP.State.EXECUCAO_FALHADA, "PROCESS_START_FAILED"),
                ({**OK_RUN, "end": "CANCELLED", "exit_code": 143}, CP.State.TAREFA_CANCELADA, "NONE")):
            with self.subTest(run=run):
                o = self.ev(self.full(), run)
                self.assertEqual((o.state, o.error_code, o.verified), (state, err, False))

    def test_missing_truncated_or_corrupt_evidence_is_never_verified(self):
        files = ("receipts.jsonl", "http.jsonl", "submissions.jsonl", "submission_chain.jsonl", "audit.jsonl",
                 "model_requests.jsonl")
        for name in files:
            for damage, code in (("delete", "EVIDENCE_MISSING"), ("truncate", "EVIDENCE_TRUNCATED"),
                                 ("corrupt", "EVIDENCE_CORRUPT")):
                with self.subTest(file=name, damage=damage):
                    out = self.full()
                    p = out / name
                    if damage == "delete":
                        p.unlink()
                    elif damage == "truncate":
                        p.write_text(p.read_text()[:-7] or '{"x"')
                    else:
                        p.write_text(p.read_text() + "{not json\n")
                    o = self.ev(out)
                    self.assertEqual((o.state, o.error_code, o.verified),
                                     (CP.State.RESULTADO_DESCONHECIDO, code, False))
                    rec = json.loads((out / "verification.json").read_text())
                    self.assertIn(name, rec["evidence_problem"])

    def test_goose_session_store_is_mandatory(self):
        out = self.full()
        __import__("shutil").rmtree(out / "goose_state")
        self.assertEqual(self.ev(out).error_code, "EVIDENCE_MISSING")
        out = self.full()
        (out / "goose_state" / "sessions" / "sessions.db").write_bytes(b"not a database at all, sorry")
        self.assertEqual(self.ev(out).error_code, "EVIDENCE_CORRUPT")

    def test_observed_calls_must_match_receipts(self):
        out = self.full()
        con = sqlite3.connect(out / "goose_state" / "sessions" / "sessions.db")
        con.execute("delete from messages where id = (select max(id) from messages)")   # one call unexplained
        con.commit()
        con.close()
        o = self.ev(out)
        self.assertEqual((o.state, o.error_code), (CP.State.RESULTADO_DESCONHECIDO, "EVIDENCE_INCONSISTENT"))
        self.assertIn("goose calls (6) != receipts (7)",
                      json.loads((out / "verification.json").read_text())["evidence_gaps"])

    def test_tool_inventory_is_mandatory(self):
        out = self.full()
        (out / "model_requests.jsonl").write_text("")                     # empty file: inventory not observed
        o = self.ev(out)
        self.assertEqual((o.state, o.error_code), (CP.State.RESULTADO_DESCONHECIDO, "EVIDENCE_INCONSISTENT"))

    def test_audit_must_agree_with_the_submission_chain(self):
        out = self.full()
        (out / "audit.jsonl").write_text("")                              # audit rows lost, file still present
        self.assertFalse(self.ev(out).verified)

    def test_legitimate_zero_operations_is_not_an_evidence_error(self):
        m = Mission(self.tmp)
        m.finish(forwarded=[G.EXT_PREFIX + t for t in G.GATEWAY_TOOLS], blocked=())
        o = self.ev(self.tmp)
        self.assertEqual((o.state, o.error_code, o.receipts_count), (CP.State.RESULTADO_DESCONHECIDO, "NONE", 0))

    def test_strict_reader(self):
        p = self.tmp / "x.jsonl"
        with self.assertRaises(G.EvidenceError):
            G._jsonl(p)
        p.write_text("")
        self.assertEqual(G._jsonl(p), [])
        p.write_text('[1]\n')
        with self.assertRaises(G.EvidenceError):
            G._jsonl(p)
        p.write_bytes(b'{"a": "\xff"}\n')
        with self.assertRaises(G.EvidenceError):
            G._jsonl(p)


@unittest.skipIf(CP is None, "pinned OpenJarvis venv required")
class Readiness(unittest.TestCase):
    def runner(self):
        return G.DockerGooseRunner(G.GooseRuntime(Path("/g"), Path("/o"), Path("/m")), Path("/tmp/p2-r"),
                                   mission_id=MID)

    def test_late_start_waits_for_the_gateway_startup_line_not_a_fixed_sleep(self):
        logs = iter(["", "", "", "", '{"gateway": "http://0.0.0.0:8790/mcp"}'])

        def fake_sh(args, **kw):
            if args[:2] == ["docker", "logs"]:
                self.assertEqual(args[2], f"jrv-p2-{MID}-gateway")        # this mission's Gateway only
                return mock.Mock(stdout=next(logs), stderr="", returncode=0)
            return mock.Mock(stdout="true", stderr="", returncode=0)
        with mock.patch.object(G, "sh", side_effect=fake_sh), mock.patch.object(G.time, "sleep"):
            self.assertTrue(self.runner().wait_ready(timeout=5))

    def test_gateway_that_exited_is_not_ready(self):
        def fake_sh(args, **kw):
            if args[:2] == ["docker", "logs"]:
                return mock.Mock(stdout="Traceback", stderr="", returncode=0)
            return mock.Mock(stdout="false", stderr="", returncode=0)
        with mock.patch.object(G, "sh", side_effect=fake_sh), mock.patch.object(G.time, "sleep"):
            self.assertFalse(self.runner().wait_ready(timeout=5))

    def test_readiness_timeout(self):
        clock = iter(range(0, 10_000, 7))
        with mock.patch.object(G, "sh", return_value=mock.Mock(stdout="true", stderr="", returncode=0)), \
                mock.patch.object(G.time, "sleep"), \
                mock.patch.object(G.time, "monotonic", side_effect=lambda: next(clock)):
            self.assertFalse(self.runner().wait_ready(timeout=60))


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
