"""JRV-TE-P2C mutation check of identity, anti-replay, de-duplication and receipts guarantees.

Applies each mutant to the working copy, runs the P2C + P2B + P2A gateway tests, restores the file (never
committed). Run: vendor/openjarvis/.venv/bin/python labs/te_p2a_gateway/mutation_p2c.py"""
import hashlib, json, pathlib, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[2]
MCP, GW, RUN = "labs/te_p2a_gateway/mcp_http.py", "labs/te_p2a_gateway/gateway.py", "labs/te_p2a_gateway/te_p2c_resume.py"
M = [
 ("P01 re-initialize without a grant", MCP, "            if self.suspended and self.grant is not None:\n                if self._clock()",
  "            if True:\n                if self.grant and self._clock()"),
 ("P02 grant not consumed", MCP, "                    self.grant, self.suspended = None, False", "                    self.suspended = False"),
 ("P03 grant expiry ignored (admission)", MCP, "                if self._clock() > self.grant[\"expires\"]:", "                if False:"),
 ("P04 summary check removed", MCP, "            mismatch = [k for k in SUMMARY_KEYS if body.get(k) != snap[k]]", "            mismatch = []"),
 ("P05 loopback check removed", MCP, "        if client_ip != \"127.0.0.1\" or not isinstance(token, str) or \\", "        if not isinstance(token, str) or \\"),
 ("P06 token check removed", MCP, "                not hmac.compare_digest(token.encode(), self._control_token.encode()):", "                False:"),
 ("P07 old session usable while suspended", MCP, "        if self.suspended:\n            return (400, \"missing session id\") if not session_header else (404, \"session terminated\")\n", ""),
 ("P08 session id not rotated on re-bind", MCP, "                    self.session_id = secrets.token_hex(16)\n                    self.control_log", "                    self.session_id = self.session_id or 'x'\n                    self.control_log"),
 ("P09 in-flight check removed", MCP, "            if snap[\"in_flight\"]:\n                return 409", "            if False:\n                return 409"),
 ("P10 suspend does not terminate session", MCP, "                self.suspended, self.grant, self.session_id = True, None, None", "                self.suspended, self.grant = True, None"),
 ("P11 replay disabled", GW, "        if self.generation == 0 or tool not in READ_REPLAY + EFFECT_REPLAY:", "        if True:"),
 ("P12 effects replayed like reads (re-executed later)", GW, "            if not effect and (rec.status != \"OK\" or op[\"replays\"] >= 1):", "            if rec.status != \"OK\" or op[\"replays\"] >= 1:"),
 ("P13 effect replay limit ignored", GW, "            if effect and op[\"replays\"] >= EFFECT_REPLAY_LIMIT:", "            if False:"),
 ("P14 reads replayed without limit", GW, "or op[\"replays\"] >= 1):", "):"),
 ("P15 failed reads replayed", GW, "(rec.status != \"OK\" or op[\"replays\"]", "(False or op[\"replays\"]"),
 ("P16 same-generation replay", GW, "            if op[\"generation\"] >= self.generation or op[\"sig\"] != sig", "            if op[\"sig\"] != sig"),
 ("P17 generation missing from call id", GW, "            gen = f\"g{self.generation}:\" if self.generation else \"\"", "            gen = \"\""),
 ("P18 cancellations leak across generations", GW, "            self.cancelled_requests.clear()", "            pass"),
 ("P19 generation may jump", GW, "            if generation != self.generation + 1:", "            if False:"),
 ("P20 replay receipt marked executed-equivalent (no reason code)", GW, "            r.reason_code = \"REPLAYED_FROM_RECEIPT\"", "            pass"),
 ("P21 replay consumes no receipt", GW, "            r = self.ledger.decide(call_id, tool, args_json, False, reason)\n            r.reason_code = \"REPLAYED_FROM_RECEIPT\"\n            self.replays.append({\"sequence\": r.sequence,",
  "            r = type('R', (), {'sequence': 0})()\n            self.replays.append({\"sequence\": r.sequence,"),
 ("P22 snapshot ignores in-flight", GW, "                    \"in_flight\": bool(self._stuck is not None and self._stuck.is_alive()),", "                    \"in_flight\": False,"),
 ("P23 duplicate effect counts refused repeats", RUN, "    accepted = [s[\"report_sha256\"] for s in subs if s[\"decision\"] == \"ACCEPTED_FOR_VERIFICATION\"]", "    accepted = [s[\"report_sha256\"] for s in subs]"),
 ("P24 duplicate effect not critical", RUN, "            \"critical_stop\": violation or dup_effect,", "            \"critical_stop\": violation,"),
 ("P25 repeated read not a failure", RUN, "    elif dup_read:\n        cat = \"LEITURA_REPETIDA\"", "    elif False:\n        cat = \"LEITURA_REPETIDA\""),
 ("P26 GO without continuity", RUN, "    elif len(ok) == PROTOCOL[\"n_trials\"]:", "    elif len(valid) == PROTOCOL[\"n_trials\"]:"),
]
TESTS = ["tests.test_te_p2c_resume", "tests.test_te_p2b_report_contract", "tests.test_te_p2a_gateway"]
py = str(ROOT / "vendor/openjarvis/.venv/bin/python")
files = {f for _, f, _, _ in M}
orig = {f: (ROOT / f).read_text() for f in files}
before = {f: hashlib.sha256(orig[f].encode()).hexdigest() for f in files}
rows = []
try:
    for name, f, old, new in M:
        src = orig[f]
        n = src.count(old)
        if n != 1:
            rows.append((name, f"PATTERN COUNT {n}", "")); continue
        (ROOT / f).write_text(src.replace(old, new))
        try:
            r = subprocess.run([py, "-m", "unittest", *TESTS], cwd=ROOT, capture_output=True, text=True, timeout=300)
            killed, err = r.returncode != 0, r.stderr
        except subprocess.TimeoutExpired:
            killed, err = True, "TIMEOUT"
        (ROOT / f).write_text(src)
        failing = sorted({l.split("(")[1].split(")")[0].split(".")[-2] + "." + l.split(" ")[1] for l in err.splitlines()
                          if l.startswith(("FAIL:", "ERROR:")) and "(" in l})
        rows.append((name, "KILLED" if killed else "SURVIVED", ", ".join(failing[:3]) + (" …" if len(failing) > 3 else "") or err[-80:]))
finally:
    for f in files:
        (ROOT / f).write_text(orig[f])
after = {f: hashlib.sha256((ROOT / f).read_text().encode()).hexdigest() for f in files}
print(json.dumps({"restored_identical": before == after}))
for r in rows:
    print(" | ".join(r))
