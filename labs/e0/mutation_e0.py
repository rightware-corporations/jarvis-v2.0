"""E0-01 mutation check of the NEW console invariants (console.py + the runtime wiring). Each mutant is applied
to the working copy, tests/test_e0_console.py + tests/test_runtime.py run, the file is restored (never committed).
Run: vendor/openjarvis/.venv/bin/python labs/e0/mutation_e0.py"""
import hashlib, json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
CON, RT, FAC = "rightware/console.py", "rightware/runtime.py", "rightware/text_facade.py"
M = [
 ("M01 model answer labelled as verified", CON, '"RESPOSTA_DO_MODELO": "Resposta do modelo (não verificada)"', '"RESPOSTA_DO_MODELO": "Resultado verificado"'),
 ("M02 refused action shown as generic unavailability", CON, "    if result.route == Route.TASK:\n        return \"NAO_AUTORIZADO\"", "    if False:\n        return \"NAO_AUTORIZADO\""),
 ("M03 unproven execution claim not flagged", CON, "    if \"UNVERIFIED_EFFECT_CLAIM\" in diag:", "    if False:"),
 ("M04 cancellation not distinguished", CON, "    if \"CANCELLED\" in diag:", "    if False:"),
 ("M05 plan shown as plain answer", CON, "    if result.status == Status.PLAN_ONLY:\n        return \"PLANO_SEM_EXECUCAO\"", "    if False:\n        return \"PLANO_SEM_EXECUCAO\""),
 ("M06 commands matched by prefix (embedded commands obeyed)", CON, "            if stripped in COMMANDS:\n                return self.command(stripped)", "            if any(stripped.startswith(c) for c in COMMANDS):\n                return self.command(stripped.split()[0])"),
 ("M07 commands detected anywhere in the line", CON, "        if stripped.startswith(\"/\"):", "        if \"/\" in stripped and stripped.split()[-1] in COMMANDS:\n            return self.command(stripped.split()[-1])\n        if stripped.startswith(\"/\"):"),
 ("M08 unknown slash command sent to the model", CON, "            self.say(\"Comando desconhecido (não foi enviado ao modelo). Escreve /ajuda.\")\n            return True", "            pass"),
 ("M09 early Ctrl+C lost (no pending retry)", CON, "                if cancel_pending and self.cancel():\n                    cancel_pending = False", "                if cancel_pending:\n                    self.cancel()\n                    cancel_pending = False"),
 ("M10 resources not released on exit", CON, "            self.facade.close()          # closes every session and releases the local adapter", "            pass"),
 ("M11 a trusted task factory wired into the console", CON, "    return TaskEntry(TextFacade(adapter=adapter, deadline_seconds=deadline_seconds))", "    return TaskEntry(TextFacade(adapter=adapter, deadline_seconds=deadline_seconds), fixture_session_factory=lambda: None)"),
 ("M12 invalid input sent/handled as model error", CON, "            except ValueError:\n                box[\"invalid\"] = True", "            except ValueError:\n                box[\"error\"] = \"ValueError\""),
 ("M13 banner hides the unverified-facts limitation", CON, "\"As respostas são texto do modelo local e NÃO são factos verificados.\"", "\"\""),
 ("M14 /sair does not stop", CON, "        elif line == \"/sair\":\n            return False", "        elif line == \"/sair\":\n            pass"),
 ("M15 runtime drops the configured default model", RT, "            extra = [\"--model\", args.model or config[\"intelligence\"][\"default_model\"], *extra]", "            extra = [*extra]"),
 ("M17 launcher ignores SIGINT with SIG_IGN (inherited by the child)", RT, "    previous = signal.signal(signal.SIGINT, lambda signum, frame: None)", "    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)"),
 ("M18 launcher without SIGINT protection (dies on Ctrl+C)", RT, "            return call_foreground(console_command(extra), cwd=ROOT, env=voice_environment())", "            return subprocess.call(console_command(extra), cwd=ROOT, env=voice_environment())"),
 ("M19 launcher handler not restored", RT, "    finally:\n        signal.signal(signal.SIGINT, previous)", "    finally:\n        pass"),
 ("M20 'Para ...' preposition treated as stop again", FAC, r"pára\b|para(?:\s+(?:j[aá]|tudo|isso|com\s+isso))?\s*[.!]*\s*$|", r"p[aá]ra\b|"),
 ("M16 runtime runs the console outside the pinned venv", RT, "    return [str(python_executable()), \"-m\", \"rightware.console\", *extra]", "    return [sys.executable, \"-m\", \"rightware.console\", *extra]"),
]
TESTS = ["tests.test_e0_console", "tests.test_runtime", "tests.test_wp04_d01_d02"]
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
