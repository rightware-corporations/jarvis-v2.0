"""JRV-P2 mutation check of the NEW invariants (P1 fixes in control_plane/console + goose adapter mapping and
isolation checks). Mutants are applied to the working copy and restored (never committed).
Run: vendor/openjarvis/.venv/bin/python labs/p2/mutation_p2.py"""
import hashlib, json, pathlib, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[2]
CPF, CON, GA = "rightware/control_plane.py", "rightware/console.py", "rightware/goose_adapter.py"
M = [
 ("F01 host status lines kept in commentary", CPF, "                           model_commentary_unverified=model_text_only(result.model_commentary_unverified),", "                           model_commentary_unverified=result.model_commentary_unverified,"),
 ("F02 trial workspace not closed after the run", CPF, "            if ws is not None:\n                ws.close()\n        state = task_state", "            pass\n        state = task_state"),
 ("F03 half-prepared workspace not removed", CPF, "        except BaseException:                       # JRV-P2 fix 2: never leave a half-prepared directory\n            shutil.rmtree(self.root, ignore_errors=True)\n            raise", "        except BaseException:\n            raise"),
 ("F04 internal error shown as unauthorised", CPF, "            outcome = failure_outcome(capability, \"INTERNAL_\" + type(exc).__name__.upper()[:40],\n                                      round(self._clock() - started, 2))", "            return Refusal(State.TAREFA_NAO_AUTORIZADA, \"CODE_INVALID\")"),
 ("F05 running flag not reset", CPF, "            with self._lock:\n                self.running, self._active = False, None", "            pass"),
 ("F06 busy check removed", CPF, "            if self.running:\n                self.audit.append({\"event\": \"refused_busy\"})", "            if False:\n                self.audit.append({\"event\": \"refused_busy\"})"),
 ("F07 banner ignores active mode", CON, "        if caps:                                        # JRV-P2 fix 3: say what is REALLY active", "        if False:"),
 ("F08 console failure shown as invalid code", CON, "        if \"error\" in box or (outcome is not None and not isinstance(outcome, (TaskOutcome, Refusal))):", "        if False:"),
 ("G01 isolation probe ignored before start", GA, "            if isolation_problems(prep):                    # verified BEFORE goose starts: fail closed", "            if False:"),
 ("G02 internet reachability ignored", GA, "    if not str(p.get(\"internet\", \"\")).startswith(\"BLOCKED\"):", "    if False:"),
 ("G03 host mounts ignored", GA, "    if g.get(\"mounts\"):", "    if False:"),
 ("G04 extra networks ignored", GA, "    if g.get(\"networks\") != [AGENT_NET]:", "    if False:"),
 ("G05 non-goose client acceptance ignored", GA, "    if p.get(\"non_goose_initialize\") != \"403\":", "    if False:"),
 ("G06 non-gateway executed calls ignored", GA, "    violations += [f\"non-gateway tool executed by goose: {n}\" for n in executed if not is_gateway_tool(n)]", "    pass"),
 ("G07 non-gateway tools reaching the model ignored", GA, "    violations += [f\"non-gateway tool reached the model: {n}\" for n in forwarded if not is_gateway_tool(n)]", "    pass"),
 ("G08 verified without consistency", GA, "    elif v[\"verdict\"] == \"TASK_VERIFIED_LIMITED\" and consistent:", "    elif v[\"verdict\"] in (\"TASK_VERIFIED_LIMITED\", \"NOT_VERIFIED\"):"),
 ("G09 inconsistent evidence shown as partial", GA, "    elif not consistent:\n        state, err = State.RESULTADO_DESCONHECIDO, \"EVIDENCE_INCONSISTENT\"", "    elif False:\n        state, err = State.RESULTADO_DESCONHECIDO, \"EVIDENCE_INCONSISTENT\""),
 ("G10 cancellation not distinguished", GA, "    elif cancelled or run.get(\"end\") == \"CANCELLED\":", "    elif False:"),
 ("G11 runner not cleaned up", GA, "            self._runner = None\n            runner.cleanup()", "            self._runner = None"),
 ("G12 cancel not stopping goose", GA, "        runner.stop()\n        return True", "        return True"),
 ("G13 goose container gets a host mount", GA, "            \"goose\": [\"docker\", \"create\", \"--name\", \"goose\", \"--network\", AGENT_NET, \"--ip\", GOOSE_IP,", "            \"goose\": [\"docker\", \"create\", \"--name\", \"goose\", \"-v\", \"/:/host:ro\", \"--network\", AGENT_NET, \"--ip\", GOOSE_IP,"),
 ("G14 networks not internal", GA, "        sh([\"docker\", \"network\", \"create\", \"--internal\", FIXTURE_NET], check=True)", "        sh([\"docker\", \"network\", \"create\", FIXTURE_NET], check=True)"),
 ("G15 tap allowlist widened", GA, "                           *sum(([\"--allow-suffix\", \"__\" + t] for t in GATEWAY_TOOLS), [])],", "                           *sum(([\"--allow-suffix\", \"__\" + t] for t in GATEWAY_TOOLS + (\"skill\",)), [])],"),
]
TESTS = ["tests.test_p2_goose_integration", "tests.test_p1_control_plane", "tests.test_e0_console"]
py = str(ROOT / "vendor/openjarvis/.venv/bin/python")
files = {f for _, f, _, _ in M}
orig = {f: (ROOT / f).read_text() for f in files}
before = {f: hashlib.sha256(orig[f].encode()).hexdigest() for f in files}
rows = []
try:
    for name, f, old, new in M:
        src = orig[f]
        if src.count(old) != 1:
            rows.append((name, f"PATTERN COUNT {src.count(old)}", "")); continue
        (ROOT / f).write_text(src.replace(old, new))
        try:
            r = subprocess.run([py, "-m", "unittest", *TESTS], cwd=ROOT, capture_output=True, text=True, timeout=300)
            killed, err = r.returncode != 0, r.stderr
        except subprocess.TimeoutExpired:
            killed, err = True, "TIMEOUT"
        (ROOT / f).write_text(src)
        failing = sorted({l.split("(")[1].split(")")[0].split(".")[-2] + "." + l.split(" ")[1] for l in err.splitlines()
                          if l.startswith(("FAIL:", "ERROR:")) and "(" in l})
        rows.append((name, "KILLED" if killed else "SURVIVED", ", ".join(failing[:3]) + (" …" if len(failing) > 3 else "")))
finally:
    for f in files:
        (ROOT / f).write_text(orig[f])
after = {f: hashlib.sha256((ROOT / f).read_text().encode()).hexdigest() for f in files}
print(json.dumps({"restored_identical": before == after}))
for r in rows:
    print(" | ".join(r))
