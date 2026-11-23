"""JRV-P1 mutation check of the NEW Control Plane invariants (rightware/control_plane.py + console task commands).
Each mutant is applied to the working copy, the P1/E0 tests run, the file is restored (never committed).
Run: vendor/openjarvis/.venv/bin/python labs/p1/mutation_p1.py"""
import hashlib, json, pathlib, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[2]
CPF, CON = "rightware/control_plane.py", "rightware/console.py"
M = [
 ("P01 any code authorises", CPF, "                or not secrets.compare_digest(code.strip().upper(), p[\"code\"]):", "                or False:"),
 ("P02 code not single-use on failure", CPF, "            p, self._pending = self._pending, None          # single use: any attempt consumes it", "            p = self._pending"),
 ("P03 expiry ignored", CPF, "        if p is None or not isinstance(code, str) or self._clock() > p[\"expires\"] \\", "        if p is None or not isinstance(code, str) \\"),
 ("P04 unknown capability accepted", CPF, "        if capability not in self.capabilities:\n            self.audit", "        if False:\n            self.audit"),
 ("P05 incomplete shown as verified", CPF, "    if op == \"COMPARISON_VERIFIED\" and result.comparison_verified:", "    if op in (\"COMPARISON_VERIFIED\", \"INCOMPLETE\"):"),
 ("P06 cancellation not distinguished", CPF, "    if cancelled or result.halt_reason_code == \"CANCELLED\":", "    if False:"),
 ("P07 failure not distinguished", CPF, "    if op == \"ERROR\":\n        return State.EXECUCAO_FALHADA", "    if False:\n        return State.EXECUCAO_FALHADA"),
 ("P08 partial not distinguished", CPF, "    if any(st == \"VERIFIED\" for _, st, _ in result.objective_states):", "    if False:"),
 ("P09 executor wired although the host did not enable it", CPF, "        factory = builder(model, self._ws, self._agent) if enable_trial_compare else None", "        factory = builder(model, self._ws, self._agent)"),
 ("P10 trial workspace not removed", CPF, "            ws.close()\n            self._ws.pop(\"ws\", None)", "            self._ws.pop(\"ws\", None)"),
 ("P11 cancel not delegated to the executor", CPF, "        self._cancelled.set()\n        agent.cancel()", "        self._cancelled.set()"),
 ("P12 capabilities enabled by default", CPF, "        self.capabilities = (TRIAL_COMPARE,) if enable_trial_compare else ()", "        self.capabilities = (TRIAL_COMPARE,)"),
 ("P13 /autorizar matched anywhere in a line", CON, "            m = _AUTH_CMD.match(stripped)", "            m = _AUTH_CMD.search(stripped)"),
 ("P14 /autorizar accepts any length", CON, "_AUTH_CMD = re.compile(r\"/autorizar ([0-9A-Fa-f]{6})\\Z\")", "_AUTH_CMD = re.compile(r\"/autorizar ([0-9A-Fa-f]+)\")"),
 ("P15 console tasks enabled without the host flag", CON, "    if args.tarefa_ensaio or session_factory_builder is not None:", "    if True:"),
 ("P16 unverified changes printed", CON, "        if outcome.verified:\n            self.say(\"Alterações", "        if True:\n            self.say(\"Alterações"),
]
TESTS = ["tests.test_p1_control_plane", "tests.test_e0_console"]
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
