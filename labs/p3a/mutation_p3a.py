"""JRV-P3A mutation check of the NEW invariants (gateway image identity/verification, hardening, adapter use of
the verified image). Mutants are applied to the working copy and restored (never committed).
Run: vendor/openjarvis/.venv/bin/python labs/p3a/mutation_p3a.py"""
import hashlib, json, pathlib, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[2]
IM, GA = "rightware/gateway/image.py", "rightware/goose_adapter.py"
M = [
 ("P01 unlabelled (unknown-build) image accepted", IM, "    if not labels.get(LABEL + \"source_digest\"):\n        raise ImageError(\"GATEWAY_IMAGE_UNVERIFIED\")", "    if False:\n        raise ImageError(\"GATEWAY_IMAGE_UNVERIFIED\")"),
 ("P02 stale image (other sources) accepted", IM, "    if label_problems(info, root):\n        raise ImageError(\"GATEWAY_IMAGE_STALE\")", "    if False:\n        raise ImageError(\"GATEWAY_IMAGE_STALE\")"),
 ("P03 image user not checked", IM, "    if (info.get(\"Config\") or {}).get(\"User\") != RUNTIME_USER:", "    if False:"),
 ("P04 uv.lock not part of the source digest", IM, "    h.update(f\"vendor_pin\\0{vendor_pin()}\\nuv.lock\\0{_sha((root / 'vendor/openjarvis/uv.lock').read_bytes())}\\n\"", "    h.update(f\"vendor_pin\\0{vendor_pin()}\\n\""),
 ("P05 read-only root fs dropped", IM, "    return [\"--read-only\", \"--cap-drop\", \"ALL\",", "    return [\"--cap-drop\", \"ALL\","),
 ("P06 capabilities not dropped", IM, "    return [\"--read-only\", \"--cap-drop\", \"ALL\", \"--security-opt\", \"no-new-privileges\",", "    return [\"--read-only\", \"--security-opt\", \"no-new-privileges\","),
 ("P07 vendor gitlink not checked against the pin", IM, "    if len(gitlink) < 3 or gitlink[2] != vendor_pin():", "    if False:"),
 ("P08 failed build not reported", IM, "        if r.returncode:\n            sys.stderr.write(r.stderr[-4000:])\n            raise ImageError(\"GATEWAY_IMAGE_BUILD_FAILED\")", "        if False:\n            raise ImageError(\"GATEWAY_IMAGE_BUILD_FAILED\")"),
 ("P09 security check ignores root user", IM, "    if (res.get(\"uid\"), res.get(\"gid\")) != (10001, 10001):", "    if False:"),
 ("P10 security check ignores setuid files", IM, "    if res.get(\"setuid_files\"):", "    if False:"),
 ("P11 security check ignores labs in the image", IM, "    if res.get(\"labs_importable\"):", "    if False:"),
 ("P12 security check ignores writable app dir", IM, "    if res.get(\"app_writable\"):", "    if False:"),
 ("P13 adapter skips image verification", GA, "            self.gw_image = GI.local_image()", "            self.gw_image = GI.IMAGE_TAG"),
 ("P14 adapter runs the mutable tag instead of the verified id", GA, "                self.gw_image or GI.IMAGE_TAG, \"python\", \"-m\"]", "                GI.IMAGE_TAG, \"python\", \"-m\"]"),
 ("P15 repository mounted into gateway containers again", GA, "        return [\"--user\", self.user, *GI.hardening_args(), \"-v\", f\"{self.out.resolve()}:/evidence\",", "        return [\"--user\", self.user, *GI.hardening_args(), \"-v\", f\"{ROOT}:/app:ro\", \"-v\", f\"{self.out.resolve()}:/evidence\","),
 ("P16 gateway containers run as root", GA, "        self.user = GI.RUNTIME_USER if uid == 0 else f\"{uid}:{os.getgid()}\"", "        self.user = \"0:0\""),
 ("P17 hardening flags not applied", GA, "        return [\"--user\", self.user, *GI.hardening_args(),", "        return [\"--user\", self.user,"),
 ("P18 unverified gateway image ignored by isolation check", GA, "    if not str(prep.get(\"gateway_image\") or \"\").startswith(\"sha256:\"):", "    if False:"),
 ("P19 evidence not handed to the unprivileged user on a root host", GA, "            for p in (self.out, *(self.out / n for n in HOST_BASELINE)):\n                os.chown(p, uid, gid)", "            pass"),
]
TESTS = ["tests.test_p3a_gateway_component", "tests.test_p2_goose_integration", "tests.test_te_p2a_gateway"]
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
