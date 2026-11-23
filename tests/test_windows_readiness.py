"""Read-only diagnostics and the PowerShell launcher contract (no Windows needed)."""
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from rightware import diagnose, runtime

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "rightware" / "windows" / "Jarvis-Issa.ps1"


class DiagnoseTests(unittest.TestCase):
    def test_sanitize_removes_home_user_and_host(self):
        with patch.dict("os.environ", {"USERNAME": "issa", "COMPUTERNAME": "PC-ISSA"}):
            text = diagnose.sanitize(f"{Path.home()}\\x issa PC-ISSA")
        self.assertNotIn("issa", text)
        self.assertNotIn(str(Path.home()), text)
        self.assertIn("<HOME>", text)

    def test_profile_check_flags_wrong_identity_and_stale_prompt(self):
        reference = (ROOT / "configs/local.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d, patch.object(runtime, "STATE", Path(d)):
            self.assertEqual(diagnose.check_profile()[0], diagnose.WARN)   # not created
            path = Path(d) / "openjarvis" / "config.toml"
            path.parent.mkdir(parents=True)
            path.write_text(reference, encoding="utf-8")
            self.assertEqual(diagnose.check_profile()[0], diagnose.PASS)
            path.write_text(reference.replace("Responde em português.", "Responde."),
                            encoding="utf-8")
            self.assertEqual(diagnose.check_profile()[0], diagnose.WARN)
            path.write_text(reference.replace("Issa", "Utilizador"), encoding="utf-8")
            self.assertEqual(diagnose.check_profile()[0], diagnose.FAIL)

    def test_diagnose_is_read_only_and_reports_json(self):
        with tempfile.TemporaryDirectory() as d, patch.object(runtime, "STATE", Path(d)):
            with patch("builtins.print"):
                code = diagnose.main([])
            self.assertFalse((Path(d) / "openjarvis").exists())      # profile not created
            reports = list((Path(d) / "logs").glob("diagnostic-*.json"))
            self.assertEqual(len(reports), 1)
            data = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertIn(code, (0, 2))
        names = [r["check"] for r in data["results"]]
        for required in ("python", "ollama", "microphone", "portuguese_voice", "profile"):
            self.assertIn(required, names)

    def test_ollama_check_never_uses_a_proxy(self):
        with patch.dict("os.environ", {"HTTP_PROXY": "http://bad.invalid:9"}):
            status, detail = diagnose.check_ollama("qwen3.5:2b")
        self.assertIn(status, (diagnose.PASS, diagnose.FAIL))
        self.assertNotIn("bad.invalid", detail)


class PowerShellScriptContract(unittest.TestCase):
    def setUp(self):
        raw = SCRIPT.read_bytes()
        self.raw = raw
        self.text = raw[3:].decode("utf-8")

    def test_bom_and_crlf_for_windows_powershell_5(self):
        self.assertTrue(self.raw.startswith(b"\xef\xbb\xbf"), "PS 5.1 needs a BOM for accents")
        self.assertIn(b"\r\n", self.raw)

    def test_default_mode_is_read_only_check(self):
        self.assertIn("[string]$Mode = 'check'", self.text)
        check_block = self.text.split("  'check' {", 1)[1].split("}", 1)[0]
        self.assertNotIn("Invoke-Jarvis", check_block)

    def test_install_and_actions_require_typed_authorization(self):
        self.assertIn("Confirm-Word 'Autorizas a instalação", self.text)
        self.assertIn("'INSTALAR'", self.text)
        self.assertIn("'AUTORIZO'", self.text)
        self.assertIn("-ceq $Word", self.text)
        # --allow-actions appears only inside the AUTORIZO branch.
        self.assertEqual(self.text.count("--allow-actions"), 1)
        actions = self.text.split("  'actions' {", 1)[1]
        self.assertLess(actions.index("AUTORIZO"), actions.index("--allow-actions"))
        self.assertEqual(self.text.count("'setup', '--voice'"), 1)

    def test_script_never_launches_apps_or_changes_the_system_itself(self):
        lowered = self.text.lower()
        for forbidden in ("start-process", "notepad.exe", "calc.exe", "set-executionpolicy",
                          "[environment]::setenvironmentvariable", "winget", "msiexec",
                          "install-module", "invoke-expression", "iex ", "new-itemproperty",
                          "set-itemproperty", "invoke-webrequest"):
            self.assertNotIn(forbidden, lowered, forbidden)

    def test_logs_are_sanitized_and_conversation_not_captured(self):
        self.assertIn("'<USER>'", self.text)
        self.assertIn("'<HOST>'", self.text)
        self.assertIn("Add-Content -Path $LogFile -Value (Protect-Text $Text)", self.text)
        invoke = self.text.split("function Invoke-Jarvis", 1)[1].split("\n}", 1)[0]
        self.assertNotIn("Out-String", invoke)       # interactive session is not recorded
        self.assertNotIn("Tee-Object", self.text)

    def test_python_probe_has_no_double_quotes(self):
        probe = re.search(r"\$probeCode = '([^']*)'", self.text).group(1)
        self.assertNotIn('"', probe)


if __name__ == "__main__":
    unittest.main()
