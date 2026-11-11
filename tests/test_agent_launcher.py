"""WORK-05: `jarvis.py agent` launcher wiring. No model, no network."""
import unittest
from unittest import mock

from rightware import runtime


class AgentLauncher(unittest.TestCase):
    def test_agent_runs_in_upstream_venv_with_capabilities_off_by_default(self):
        cmd = runtime.agent_command(["Qual é o câmbio?"])
        self.assertEqual(cmd[0], str(runtime.python_executable()))
        self.assertEqual(cmd[1:3], ["-m", "rightware.agent.cli"])
        self.assertNotIn("--allow-web", cmd)
        self.assertNotIn("--allow-actions", cmd)

    def test_agent_flags_pass_through_and_local_only_environment(self):
        with mock.patch.object(runtime, "verify_source"), mock.patch.object(runtime, "prepare_config"), \
                mock.patch.object(runtime, "python_executable") as py, \
                mock.patch.object(runtime.subprocess, "call", return_value=0) as call:
            py.return_value.is_file.return_value = True
            py.return_value.__str__.return_value = "venv-python"
            self.assertEqual(runtime.main(["agent", "lê https://example.org", "--allow-web"]), 0)
            argv, kwargs = call.call_args[0][0], call.call_args[1]
            self.assertIn("--allow-web", argv)
            self.assertNotIn("--allow-actions", argv)
            env = kwargs["env"]
            self.assertEqual(env["OLLAMA_HOST"], "http://127.0.0.1:11434")
            self.assertEqual(env["OLLAMA_NO_CLOUD"], "1")
            self.assertFalse(any(k.upper().endswith(("API_KEY", "AUTH_TOKEN")) for k in env))

    def test_other_commands_still_reject_unknown_flags(self):
        with self.assertRaises(SystemExit):
            runtime.main(["doctor", "--allow-web"])


if __name__ == "__main__":
    unittest.main()
