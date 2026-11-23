"""JRV-P3A: RIGHTWARE Tool Gateway as a product runtime component. FAKE/offline (no Docker daemon, no model).

Parity with the validated TE-P2A..C lab code, no labs imports on product paths, historical aliases, image
identity/verification and build/startup failure handling. Not real-image or real-isolation evidence (that is the
build manifest and the real mission evidence under docs/evidence/p3a/).
"""
import ast
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
try:
    import httpx  # noqa: F401  (pinned venv marker)
    from rightware import goose_adapter as G
    from rightware.gateway import image as GI
except ImportError:
    G = None

HAVE_LOCK = (ROOT / "vendor/openjarvis/uv.lock").is_file()     # absent in copied-tree suites without the vendor


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@unittest.skipIf(G is None, "pinned OpenJarvis venv required")
class Parity(unittest.TestCase):
    """Before/after: each moved file is the validated original plus ONLY the declared substitutions."""

    def test_moved_files_equal_the_validated_originals_modulo_declared_changes(self):
        manifest = json.loads((ROOT / "rightware/gateway/PARITY.json").read_text())
        self.assertEqual(manifest["origin_commit"], "a1b88efc9db00f501d7c6772c31d01ce69622dff")
        self.assertEqual(len(manifest["files"]), 8)
        for new, m in manifest["files"].items():
            with self.subTest(file=new):
                text = (ROOT / new).read_text()
                self.assertTrue(text.startswith(m["header"]))
                text = text[len(m["header"]):]
                for old, replacement, *_ in reversed(m["substitutions"]):
                    self.assertEqual(text.count(replacement), 1)   # deletions are recorded with their anchor line
                    text = text.replace(replacement, old)
                self.assertEqual(git_blob(text.encode()), m["origin_blob"])

    def test_declared_changes_are_imports_and_te_p2d_fail_closed_only(self):
        manifest = json.loads((ROOT / "rightware/gateway/PARITY.json").read_text())
        allowed_reasons = {"UI-02 R-7 controlled num_thread"}          # later, separately reviewed changes
        for new, m in manifest["files"].items():
            for old, replacement, *reason in m["substitutions"]:
                with self.subTest(file=new, old=old[:40]):
                    if reason:
                        self.assertIn(reason[0], allowed_reasons)
                        self.assertEqual(new, "rightware/gateway/model_tap.py")
                    else:
                        self.assertTrue("labs." in old)
                    self.assertNotIn("labs.", replacement)

    def test_historical_names_are_the_same_module_objects(self):
        pairs = {"labs.te_p2a_gateway.gateway": "rightware.gateway.gateway",
                 "labs.te_p2a_gateway.mcp_http": "rightware.gateway.mcp_http",
                 "labs.te_p2a_gateway.model_tap": "rightware.gateway.model_tap",
                 "labs.te_p2a_gateway.report_contract": "rightware.gateway.report_contract",
                 "labs.te_p2a_gateway.verify": "rightware.gateway.verify",
                 "labs.te_p2a_gateway.fixture_transport": "rightware.gateway.synthetic.fixture_transport",
                 "labs.te_p1_bakeoff.site": "rightware.gateway.synthetic.site",
                 "labs.te_p1_bakeoff.score_semantic": "rightware.gateway.synthetic.score_semantic"}
        for old, new in pairs.items():
            with self.subTest(old=old):
                self.assertIs(importlib.import_module(old), importlib.import_module(new))
        from labs.te_p2a_gateway import report_contract as RC
        from rightware.gateway import report_contract
        self.assertIs(RC, report_contract)

    def test_unknown_contract_and_public_egress_still_fail_closed(self):
        from rightware.gateway import gateway, mcp_http
        with self.assertRaises(ValueError):
            gateway._contract_module("te-p2d.research.v1")
        with self.assertRaises(SystemExit) as cm:
            mcp_http.main(["--task", "T", "--attempt", "A", "--evidence", tempfile.mkdtemp(),
                           "--egress-socket", "/tmp/x", "--site", "docs.python.org", "--prefix", "/3/"])
        self.assertIn("not part of the RIGHTWARE product runtime", str(cm.exception))


@unittest.skipIf(G is None, "pinned OpenJarvis venv required")
class NoLabsOnProductPaths(unittest.TestCase):
    def test_no_rightware_module_imports_labs(self):
        offenders = []
        for path in sorted((ROOT / "rightware").rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(), str(path))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                offenders += [f"{path.relative_to(ROOT)}: {n}" for n in names if n.split(".")[0] == "labs"]
        self.assertEqual(offenders, [])

    def test_image_file_list_covers_the_runtime_import_closure(self):
        code = ("import sys, json\n"
                "for m in ('rightware.gateway.mcp_http','rightware.gateway.model_tap','rightware.gateway.verify',"
                "'rightware.gateway.synthetic.site'): __import__(m)\n"
                "print(json.dumps(sorted(getattr(sys.modules[m], '__file__', '') or '' for m in sys.modules "
                "if m.split('.')[0] in ('rightware', 'labs'))))")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        files = {str(Path(f).resolve().relative_to(ROOT)) for f in json.loads(r.stdout)}
        self.assertFalse([f for f in files if f.startswith("labs")])
        self.assertEqual(files - set(GI.RUNTIME_FILES), set())


@unittest.skipIf(G is None, "pinned OpenJarvis venv required")
class ImageIdentity(unittest.TestCase):
    ID = "sha256:" + "cd" * 32

    def info(self, labels=None, user=GI.RUNTIME_USER if G else None):
        return {"Id": self.ID, "Config": {"User": user, "Labels": labels}}

    @unittest.skipIf(not HAVE_LOCK, "pinned vendor checkout required")
    def test_only_the_image_built_from_this_tree_is_accepted(self):
        good = GI.expected_labels()
        cases = ((None, "GATEWAY_IMAGE_MISSING"),
                 (self.info({}), "GATEWAY_IMAGE_UNVERIFIED"),             # e.g. the old committed jrv-gateway image
                 (self.info({**good, GI.LABEL + "source_digest": "0" * 64}), "GATEWAY_IMAGE_STALE"),
                 (self.info({**good, GI.LABEL + "vendor_pin": "0" * 40}), "GATEWAY_IMAGE_STALE"),
                 (self.info(good, user="0:0"), "GATEWAY_IMAGE_STALE"),
                 ({**self.info(good), "Id": "latest"}, "GATEWAY_IMAGE_UNVERIFIED"))
        for info, code in cases:
            with self.subTest(code=code), mock.patch.object(GI, "inspect", return_value=info):
                with self.assertRaises(GI.ImageError) as cm:
                    GI.local_image()
                self.assertEqual(str(cm.exception), code)
        with mock.patch.object(GI, "inspect", return_value=self.info(good)):
            self.assertEqual(GI.local_image(), self.ID)

    @unittest.skipIf(not HAVE_LOCK, "pinned vendor checkout required")
    def test_source_digest_tracks_every_runtime_and_build_file(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for rel in GI.RUNTIME_FILES + GI.BUILD_FILES + ("vendor/openjarvis/uv.lock",):
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, tmp / rel)
        self.assertEqual(GI.source_digest(tmp), GI.source_digest())
        for rel in ("rightware/agent/policy.py", "rightware/gateway/gateway.py", "configs/gateway/Dockerfile",
                    "vendor/openjarvis/uv.lock"):
            with self.subTest(rel=rel):
                original = (tmp / rel).read_bytes()
                (tmp / rel).write_bytes(original + b"\n")
                self.assertNotEqual(GI.source_digest(tmp), GI.source_digest())
                (tmp / rel).write_bytes(original)

    def test_hardening_flags(self):
        flags = GI.hardening_args()
        self.assertIn("--read-only", flags)
        self.assertEqual(flags[flags.index("--cap-drop") + 1], "ALL")
        self.assertIn("no-new-privileges", flags)
        self.assertTrue(GI.BASE_IMAGE.split("@")[1].startswith("sha256:"))
        self.assertEqual(G.PY_IMAGE, GI.BASE_IMAGE)
        dockerfile = (ROOT / "configs/gateway/Dockerfile").read_text()
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("uv sync --frozen --no-dev", dockerfile)
        self.assertIn("--require-hashes", dockerfile)
        self.assertNotIn("labs", dockerfile)
        self.assertIn("--hash=sha256:", (ROOT / "configs/gateway/build-requirements.txt").read_text())


def ok(stdout="", rc=0):
    return mock.Mock(returncode=rc, stdout=stdout, stderr="boom")


@unittest.skipIf(G is None, "pinned OpenJarvis venv required")
class BuildAndStartupFailures(unittest.TestCase):
    def test_vendor_must_be_the_pin(self):
        with mock.patch.object(GI, "_run", return_value=ok("160000 commit " + "0" * 40 + "\tvendor/openjarvis")):
            with self.assertRaises(GI.ImageError) as cm:
                GI.check_vendor()
        self.assertEqual(str(cm.exception), "VENDOR_GITLINK_NOT_PIN")

    def test_failed_build_is_a_code_not_an_image(self):
        with mock.patch.object(GI, "check_vendor"), mock.patch.object(GI, "stage_context"), \
                mock.patch.object(GI, "pin_epoch", return_value=1), \
                mock.patch.object(GI, "expected_labels", return_value={GI.LABEL + "source_digest": "d"}), \
                mock.patch.object(GI.subprocess, "run", return_value=ok(rc=1)), \
                mock.patch.object(GI, "local_image") as li, mock.patch("sys.stderr"):
            with self.assertRaises(GI.ImageError) as cm:
                GI.build()
        self.assertEqual(str(cm.exception), "GATEWAY_IMAGE_BUILD_FAILED")
        li.assert_not_called()

    def test_security_check_rejects_privileged_or_leaky_images(self):
        base = {"uid": 10001, "gid": 10001, "setuid_files": [], "imports_ok": True, "labs_importable": False,
                "app_writable": False}
        self.assertEqual(GI.security_checks.__name__, "security_checks")
        for patch, problem in (({"uid": 0}, "privileged"), ({"setuid_files": ["/bin/su"]}, "setuid"),
                               ({"labs_importable": True}, "labs/"), ({"app_writable": True}, "writable")):
            with self.subTest(problem=problem), \
                    mock.patch.object(GI, "_run", return_value=ok(json.dumps({**base, **patch}) + "\n")):
                self.assertTrue(any(problem in p for p in GI.security_checks("sha256:x")["problems"]))
        with mock.patch.object(GI, "_run", return_value=ok("")):
            self.assertEqual(GI.security_checks("sha256:x")["problems"], ["probe did not run"])
        with mock.patch.object(GI, "_run", return_value=ok(json.dumps(base) + "\n")):
            self.assertEqual(GI.security_checks("sha256:x")["problems"], [])

    def test_unverified_image_stops_preparation_before_any_resource(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        rt = G.GooseRuntime(Path("/g"), Path("/o"), Path("/m"))
        for code in ("GATEWAY_IMAGE_MISSING", "GATEWAY_IMAGE_STALE", "GATEWAY_IMAGE_UNVERIFIED"):
            with self.subTest(code=code), mock.patch.object(G.GI, "local_image", side_effect=GI.ImageError(code)), \
                    mock.patch.object(G, "sh") as sh:
                r = G.DockerGooseRunner(rt, out, mission_id="0a1b2c3d")
                with self.assertRaises(RuntimeError) as cm:
                    r.prepare()
                self.assertEqual(str(cm.exception), code)
                sh.assert_not_called()
                self.assertEqual(r.created, [])

    def test_mission_reports_image_failure_as_failed_without_starting(self):
        from rightware import control_plane as CP
        from rightware.text_facade import TextFacade

        class Text:
            def reply(self, text, history):
                return "x"

            def close(self):
                pass
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        rt = G.GooseRuntime(Path("/g"), Path("/o"), Path("/m"))
        mission = G.GooseMission(rt, evidence_root=root)
        cp = CP.ControlPlane(TextFacade(adapter=Text()), goose=mission)
        self.addCleanup(cp.close)
        _, code = cp.request(G.CAPABILITY)
        with mock.patch.object(G.GI, "local_image", side_effect=GI.ImageError("GATEWAY_IMAGE_STALE")), \
                mock.patch.object(G, "sh") as sh:
            o = cp.authorize_and_run(code)
        self.assertEqual((o.state, o.error_code, o.verified), (CP.State.EXECUCAO_FALHADA, "GATEWAY_IMAGE_STALE",
                                                               False))
        self.assertFalse([c for c in sh.call_args_list if c.args[0][:3] == ["docker", "start", mock.ANY]])

    def test_gateway_containers_never_run_as_root(self):
        """Root host: the evidence dir is handed to the image's user 10001. Non-root host: the containers run as
        that host user and nothing is chowned."""
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        r = G.DockerGooseRunner(G.GooseRuntime(Path("/g"), Path("/o"), Path("/m")), out, mission_id="0a1b2c3d")
        uid = getattr(os, "getuid", lambda: 0)()
        self.assertEqual(r.user, GI.RUNTIME_USER if uid == 0 else f"{uid}:{os.getgid()}")
        self.assertNotEqual(r.user.split(":")[0], "0")
        with mock.patch.object(G.GI, "local_image", return_value="sha256:" + "ab" * 32), \
                mock.patch.object(G, "sh", return_value=ok(rc=1)):
            with self.assertRaises(RuntimeError):
                r.prepare()                                    # fails at the first network create (FAKE)
        expected = 10001 if uid == 0 else uid
        self.assertEqual((out.stat().st_uid, (out / "audit.jsonl").stat().st_uid), (expected, expected))

if __name__ == "__main__":
    unittest.main()
