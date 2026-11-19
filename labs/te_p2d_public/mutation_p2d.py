"""JRV-TE-P2D mutation check (egress policy, transport, research verifier, contract, classification).
Each mutant is applied to the working copy, the P2D/P2C/P2B/P2A gateway tests run, the file is restored (never
committed). Run: vendor/openjarvis/.venv/bin/python labs/te_p2d_public/mutation_p2d.py"""
import hashlib, json, pathlib, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[2]
E, T, V = "labs/te_p2d_public/egress.py", "labs/te_p2d_public/transport.py", "labs/te_p2d_public/research_verify.py"
C, R = "labs/te_p2d_public/research_contract.py", "labs/te_p2d_public/te_p2d_trials.py"
M = [
 ("E01 host allowlist bypassed", E, "        if host not in self.hosts:\n            return", "        if False:\n            return"),
 ("E02 https-only removed", E, "        if parts.scheme != \"https\":", "        if parts.scheme not in (\"https\", \"http\", \"ftp\", \"file\", \"gopher\"):"),
 ("E03 path prefix ignored", E, "        if not any(path.startswith(p) for p in self.prefixes):", "        if False:"),
 ("E04 dot-segments allowed", E, "        if any(seg in (\"..\", \".\") for seg in path.split(\"/\")) or \"%2e\" in path.lower() or \"%2f\" in path.lower():", "        if False:"),
 ("E05 credentials allowed", E, "        if parts.username or parts.password or \"@\" in parts.netloc:", "        if False:"),
 ("E06 upstream SSRF verdict ignored", E, "            if verdict and not verdict.startswith(\"Could not resolve host\"):", "            if False:"),
 ("E07 request budget ignored", E, "            if reason is None and self.requests >= self.max_requests:", "            if False:"),
 ("E08 body cap removed (bomb)", E, "                    if size > MAX_BODY:", "                    if False:"),
 ("E09 content type unchecked", E, "                if ctype not in ALLOWED_TYPES:\n                    return {\"decision\": \"REFUSED\"", "                if False:\n                    return {\"decision\": \"REFUSED\""),
 ("E10 proxy peer unchecked", E, "                    if peer is None or (str(peer[0]), int(peer[1])) != tuple(self.expected_peer):", "                    if False:"),
 ("E11 TLS host unchecked", E, "                    if not tls or host not in tls[\"dns_names\"]:", "                    if False:"),
 ("E12 port check removed", E, "        if port not in (None, 443):", "        if False:"),
 ("T01 redirect hop not re-checked", T, "                current = self._scoped(urljoin(current, str(reply.get(\"location\") or \"\")), host_allowed)", "                current = urljoin(current, str(reply.get(\"location\") or \"\"))"),
 ("T02 body integrity unchecked", T, "            if digest != reply.get(\"sha256\"):", "            if False:"),
 ("T03 gateway pre-check skipped", T, "        reason = self.policy.check(url)\n        if reason:", "        reason = None\n        if reason:"),
 ("V01 quote not checked", V, "        elif quote not in _norm(o[\"text\"]):", "        elif False:"),
 ("V02 source_url vs observation unchecked", V, "        elif _strip_fragment(c.get(\"source_url\")) != _strip_fragment(o[\"final_url\"]):", "        elif False:"),
 ("V03 unobserved sources ignored", V, "    if unobserved:\n        reasons.append", "    if False:\n        reasons.append"),
 ("V04 egress correspondence ignored", V, "    if not corr[\"match\"]:\n        reasons.append", "    if False:\n        reasons.append"),
 ("V05 unauthorised egress ignored", V, "    return {\"match\": first is None and not unauthorised,", "    return {\"match\": first is None,"),
 ("V06 observation raw hash unchecked", V, "and r.raw_sha256 == o.get(\"raw_sha256\")", ""),
 ("V07 semantic ignores evidence", V, "    semantic = all(x[\"in_answer\"] and x[\"supported_by\"] for x in facts) and cites_required", "    semantic = all(x[\"in_answer\"] for x in facts)"),
 ("V08 question id ignored", V, "    if report.get(\"question_id\") != reference[\"question_id\"]:", "    if False:"),
 ("V09 uncredited claims tolerated", V, "    if uncredited:\n        reasons.append", "    if False:\n        reasons.append"),
 ("V10 observation text hash unchecked", V, "              and hashlib.sha256(str(o.get(\"text\", \"\")).encode(\"utf-8\")).hexdigest() == o.get(\"text_sha256\"))", "              )"),
 ("C01 source reference unchecked", C, "                    if isinstance(sources, list) and c[key] not in sources:", "                    if False:"),
 ("C02 evidence required without abstention removed", C, "    if obj.get(\"abstained\") is False and isinstance(claims, list) and isinstance(sources, list) \\", "    if False and isinstance(claims, list) and isinstance(sources, list) \\"),
 ("C03 observation coercion (bool/str)", C, "            \"integer\": isinstance(v, int) and not isinstance(v, bool),", "            \"integer\": isinstance(v, (int, str)),"),
 ("R01 unauthorised egress not a violation", R, "    violation = (not isolation or unauthorised or", "    violation = (not isolation or"),
 ("R02 GO with a failure", R, "    elif k == PROTOCOL[\"n_trials\"]:", "    elif k >= PROTOCOL[\"n_trials\"] - 1:"),
]
TESTS = ["tests.test_te_p2d_public", "tests.test_te_p2c_resume", "tests.test_te_p2b_report_contract", "tests.test_te_p2a_gateway"]
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
        rows.append((name, "KILLED" if killed else "SURVIVED", ", ".join(failing[:3]) + (" …" if len(failing) > 3 else "")))
finally:
    for f in files:
        (ROOT / f).write_text(orig[f])
after = {f: hashlib.sha256((ROOT / f).read_text().encode()).hexdigest() for f in files}
print(json.dumps({"restored_identical": before == after}))
for r in rows:
    print(" | ".join(r))
