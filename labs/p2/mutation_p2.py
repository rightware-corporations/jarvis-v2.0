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
 ("F09 verified result assumed to carry changes (real-run crash)", CON, "        if outcome.verified and outcome.changes:      # only executors that produce code-computed changes (P1)", "        if outcome.verified:"),
 ("G01 isolation probe ignored before start", GA, "            if isolation_problems(prep):                    # verified BEFORE goose starts: fail closed", "            if False:"),
 ("G02 internet reachability ignored", GA, "    if not str(p.get(\"internet\", \"\")).startswith(\"BLOCKED\"):", "    if False:"),
 ("G03 host mounts ignored", GA, "    if g.get(\"mounts\"):", "    if False:"),
 ("G04 extra networks ignored", GA, "    if not prep.get(\"agent_network\") or g.get(\"networks\") != [prep[\"agent_network\"]]:", "    if False:"),
 ("G05 non-goose client acceptance ignored", GA, "    if p.get(\"non_goose_initialize\") != \"403\":", "    if False:"),
 ("G06 non-gateway executed calls ignored", GA, "    violations += [f\"non-gateway tool executed by goose: {n}\" for n in executed if not is_gateway_tool(n)]", "    pass"),
 ("G07 non-gateway tools reaching the model ignored", GA, "    violations += [f\"non-gateway tool reached the model: {n}\" for n in forwarded if not is_gateway_tool(n)]", "    pass"),
 ("G08 verified without consistency", GA, "    elif not consistent:\n        state, err = State.RESULTADO_DESCONHECIDO, \"EVIDENCE_INCONSISTENT\"\n    elif v[\"verdict\"] == \"TASK_VERIFIED_LIMITED\" and process_ok(run):", "    elif v[\"verdict\"] == \"TASK_VERIFIED_LIMITED\":"),
 ("G09 inconsistent evidence shown as partial", GA, "    elif not consistent:\n        state, err = State.RESULTADO_DESCONHECIDO, \"EVIDENCE_INCONSISTENT\"", "    elif False:\n        state, err = State.RESULTADO_DESCONHECIDO, \"EVIDENCE_INCONSISTENT\""),
 ("G10 cancellation not distinguished", GA, "    elif cancelled or end == \"CANCELLED\":", "    elif False:"),
 ("G11 runner not cleaned up", GA, "            self._runner = None\n            runner.cleanup()", "            self._runner = None"),
 ("G12 cancel not stopping goose", GA, "        runner.stop()\n        return True", "        return True"),
 ("G13 goose container gets a host mount", GA, "            \"goose\": [\"docker\", \"create\", \"--name\", N[\"goose\"], *self._label(), \"--network\", A, \"--ip\", self.goose_ip,", "            \"goose\": [\"docker\", \"create\", \"--name\", N[\"goose\"], *self._label(), \"-v\", \"/:/host:ro\", \"--network\", A, \"--ip\", self.goose_ip,"),
 ("G14 networks not internal", GA, "        self._create(\"network\", [\"docker\", \"network\", \"create\", \"--internal\", *self._label(), self.net[\"fixture\"]])", "        self._create(\"network\", [\"docker\", \"network\", \"create\", *self._label(), self.net[\"fixture\"]])"),
 ("G15 tap allowlist widened", GA, "                           *sum(([\"--allow-suffix\", \"__\" + t] for t in GATEWAY_TOOLS), []),", "                           *sum(([\"--allow-suffix\", \"__\" + t] for t in GATEWAY_TOOLS + (\"skill\",)), []),"),
 # ---- R1: the four audit findings
 ("R1-1a cleanup by fixed global names (pre-R1 behaviour)", GA, "        for kind, rid in reversed(self.created):\n            if not self._owned(kind, rid):\n                continue", "        for kind, rid in [(\"container\", n) for n in (\"gateway\", \"goose\", \"ollama\", \"fixture\", \"ollama-tap\")] + list(reversed(self.created)):\n            if False:\n                continue"),
 ("R1-1b ownership label not checked before removal", GA, "            if not self._owned(kind, rid):\n                continue", "            if False:\n                continue"),
 ("R1-1c failed create still recorded as owned", GA, "        if r.returncode != 0 or not re.fullmatch(r\"[0-9a-f]{12,64}\", rid):\n            raise RuntimeError(f\"DOCKER_CREATE_FAILED:{kind}\")", "        if r.returncode != 0 or not re.fullmatch(r\"[0-9a-f]{12,64}\", rid):\n            self.created.append((kind, args[args.index(\"--name\") + 1] if \"--name\" in args else args[-1]))\n            raise RuntimeError(f\"DOCKER_CREATE_FAILED:{kind}\")"),
 ("R1-1d resources not labelled", GA, "        return [\"--label\", f\"{LABEL}={self.mission}\"]", "        return []"),
 ("R1-2a exit code ignored", GA, "    return run.get(\"end\") == \"EXITED\" and run.get(\"exit_code\") == 0 and run.get(\"status\") == \"exited\" \\\n        and run.get(\"state_copied\") is True", "    return run.get(\"end\") == \"EXITED\""),
 ("R1-2b process failure not mapped to failed", GA, "    elif end in (\"START_FAILED\", \"STATE_UNKNOWN\") or (end == \"EXITED\" and not process_ok(run)):", "    elif False:"),
 ("R1-2c verified without operational success", GA, "    elif v[\"verdict\"] == \"TASK_VERIFIED_LIMITED\" and process_ok(run):", "    elif v[\"verdict\"] == \"TASK_VERIFIED_LIMITED\":"),
 ("R1-2d start failure ignored", GA, "        if not self.goose_ready or sh([\"docker\", \"start\", name]).returncode != 0:", "        if False:"),
 ("R1-2e unreadable process state treated as exited", GA, "            if running.returncode != 0:\n                end = \"STATE_UNKNOWN\"\n                break", "            if running.returncode != 0:\n                break"),
 ("R1-3a lenient reader (empty list on missing file)", GA, "    if not path.is_file():\n        raise EvidenceError(path.name, \"MISSING\")", "    if not path.is_file():\n        return []"),
 ("R1-3b corrupt lines skipped", GA, "        except ValueError:\n            raise EvidenceError(path.name, \"CORRUPT\") from None\n        if not isinstance(row, dict):", "        except ValueError:\n            continue\n        if not isinstance(row, dict):"),
 ("R1-3c truncation accepted", GA, "    if data and not data.endswith(\"\\n\"):\n        raise EvidenceError(path.name, \"TRUNCATED\")", "    if False:\n        raise EvidenceError(path.name, \"TRUNCATED\")"),
 ("R1-3d missing goose session store treated as no calls", GA, "    if not dbs:\n        raise EvidenceError(\"goose sessions.db\", \"MISSING\")", "    if not dbs:\n        return []"),
 ("R1-3e observed calls not matched with receipts", GA, "    calls_match = len(gateway_calls) == len(receipts)", "    calls_match = True"),
 ("R1-3f tool inventory not required", GA, "    if (executed or receipts) and not (inventory_seen and forwarded):", "    if False:"),
 ("R1-3g audit not cross-checked with the chain", GA, "    chain_check = RC.check_chain(chain, receipts, subs, audit)", "    chain_check = RC.check_chain(chain, receipts, subs)"),
 ("R1-3h gateway evidence baseline ignored", GA, "    problems += [f\"evidence baseline: {b}\" for b in prep.get(\"baseline\") or ()]", "    pass"),
 ("R1-4a readiness result ignored", GA, "        if not self.wait_ready():                          # R1 gate 4: never create goose without a ready Gateway\n            raise RuntimeError(\"GATEWAY_NOT_READY\")", "        self.wait_ready()"),
 ("R1-4b readiness skipped", GA, "        if not self.wait_ready():                          # R1 gate 4: never create goose without a ready Gateway\n            raise RuntimeError(\"GATEWAY_NOT_READY\")", ""),
 ("R1-4c exited gateway reported ready", GA, "                return False                        # exited, or not inspectable: never \"ready\"", "                return True"),
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
