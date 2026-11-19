"""JRV-TE-P2B mutation check: applies each mutant to the working copy, runs the contract+gateway tests,
restores the original file (never committed). Run: vendor/openjarvis/.venv/bin/python labs/te_p2a_gateway/mutation_p2b.py"""
import hashlib, json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
RC, GW, FZ, TR = "labs/te_p2a_gateway/report_contract.py", "labs/te_p2a_gateway/gateway.py", "labs/te_p2a_gateway/frozen.py", "labs/te_p2a_gateway/te_p2b_trials.py"
M = [
 ("M01 accept unknown top-level key", RC, "    if set(obj) - set(TOP_FIELDS):", "    if False:"),
 ("M02 accept unknown product key", RC, "            if set(item) - set(PRODUCT_FIELDS):", "            if False:"),
 ("M03 boolean coercion", RC, '        return isinstance(value, bool)\n', '        return isinstance(value, bool) or value in ("true", "false", "sim", 1, 0)\n'),
 ("M04 number coercion", RC, "        return isinstance(value, (int, float)) and not isinstance(value, bool)", "        return isinstance(value, (int, float, str))"),
 ("M05 ignore missing top field", RC, '            _err(errors, f"$.{key}", "required", typ, "E_MISSING")', "            pass"),
 ("M06 ignore missing product field", RC, '                    _err(errors, path, "required", typ, "E_MISSING")', "                    pass"),
 ("M07 ignore size limit", RC, "    if size > MAX_REPORT_BYTES:", "    if False:"),
 ("M08 quota not counted", GW, "max_calls=RC.MAX_SUBMISSIONS)", "max_calls=99)"),
 ("M09 chain without linking", RC, '    prev = chain[-1]["record_sha256"] if chain else genesis(run_id)', "    prev = genesis(run_id)"),
 ("M10 checker ignores links", RC, '        if r.get("prev_record_sha256") != prev:', "        if False:"),
 ("M11 description carries scenario value", RC, '"Limite 8000 bytes UTF-8; ', '"Limite 8000 bytes UTF-8; preço típico USD 12; '),
 ("M12 feedback echoes unknown key name", RC, '        _err(errors, "$", "additional_properties", "apenas as chaves do contrato", "E_UNKNOWN_KEY")', '        _err(errors, "$." + sorted(set(obj) - set(TOP_FIELDS))[0], "additional_properties", "apenas as chaves do contrato", "E_UNKNOWN_KEY")'),
 ("M13 feedback echoes submitted value", RC, '                    _err(errors, path, "type", typ, "E_TYPE")', '                    _err(errors, path, "type", repr(item[key])[:40], "E_TYPE")'),
 ("M14 duplicates not detected", GW, "        elif digest in seen:", "        elif False:"),
 ("M15 later report replaces accepted", GW, "        if self._accepted_sequence is not None:", "        if False:"),
 ("M16 NaN/Infinity accepted", RC, "parse_constant=_nonfinite", "parse_constant=float"),
 ("M17 duplicate keys accepted", RC, "object_pairs_hook=_pairs, ", ""),
 ("M18 recommendation reference unchecked", RC, "    if isinstance(rec, str) and isinstance(products, list) and names and rec not in names:", "    if False:"),
 ("M19 decision/status mismatch ignored", RC, '        if accepted != (rec.status == "OK") or (not accepted and rec.reason_code != r.get("decision")):', "        if False:"),
 ("M20 unknown version accepted", RC, "        if version != CONTRACT_ID:", "        if False:"),
 ("M21 invalid report stored for verifier", GW, '        if decision == "ACCEPTED_FOR_VERIFICATION":\n            self._accepted_sequence = seq', '        if True:\n            self._accepted_sequence = seq'),
 ("M22 record hash not verified", RC, '        if _record_hash(r) != r.get("record_sha256"):', "        if False:"),
 ("M23 control characters accepted", RC, "    if _CONTROL.search(value):", "    if False:"),
 ("M24 URL format unchecked", RC, "    if url and not _URL.match(value):", "    if False:"),
 ("M25 price range unchecked", RC, "                    if not math.isfinite(v) or not 0 <= v <= PRICE_MAX:", "                    if False:"),
 ("M26 lone surrogate accepted in strings", RC, '        value.encode("utf-8")\n', '        value.encode("utf-8", "surrogatepass")\n'),
 ("M27 schema_valid forced true", RC, "    return ValidationResult(not out, out)", "    return ValidationResult(True, out)"),
 ("M28 frozen detector blind", FZ, "    diffs = [rel for rel, digest in base[\"files\"].items() if now.get(rel) != digest]", "    diffs = []"),
 ("M29 model failure invalidates trial", TR, "    invalid = infra_failed or receipts_inconsistent  ", "    invalid = infra_failed or receipts_inconsistent or v['verdict'] != 'TASK_VERIFIED_LIMITED'  "),
 ("M30 GO threshold lowered", TR, "    elif k >= 4:", "    elif k >= 3:"),
 ("M31 audit mismatch ignored", RC, "        if len(outcomes) != len(subs):", "        if False:"),
]
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
        r = subprocess.run([py, "-m", "unittest", "tests.test_te_p2b_report_contract", "tests.test_te_p2a_gateway"],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
        (ROOT / f).write_text(src)
        killed = r.returncode != 0
        failing = sorted({l.split("(")[1].split(")")[0].split(".")[-2] + "." + l.split(" ")[1] for l in r.stderr.splitlines()
                          if l.startswith(("FAIL:", "ERROR:")) and "(" in l})
        rows.append((name, "KILLED" if killed else "SURVIVED", ", ".join(failing[:3]) + (" …" if len(failing) > 3 else "")))
finally:
    for f in files:
        (ROOT / f).write_text(orig[f])
after = {f: hashlib.sha256((ROOT / f).read_text().encode()).hexdigest() for f in files}
print(json.dumps({"restored_identical": before == after}, indent=0))
for r in rows:
    print(" | ".join(r))
