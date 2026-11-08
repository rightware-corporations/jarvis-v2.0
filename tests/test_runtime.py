import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from rightware import runtime as r


class LocalRuntimeTests(unittest.TestCase):
    def test_cloud_credentials_removed_without_changing_parent(self):
        source = {"ANTHROPIC_API_KEY": "test", "OPENAI_API_KEY": "test", "PATH": "/bin", "OLLAMA_HOST": "https://remote.invalid"}
        child = r.child_environment(source)
        self.assertNotIn("ANTHROPIC_API_KEY", child)
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertEqual(child["OLLAMA_HOST"], "http://127.0.0.1:11434")
        self.assertEqual(source["ANTHROPIC_API_KEY"], "test")

    def test_existing_config_preserved_and_cloud_rejected(self):
        with tempfile.TemporaryDirectory() as d, patch.object(r, "STATE", Path(d)):
            r.prepare_config()
            path = Path(d) / "openjarvis/config.toml"
            s = path.read_text().replace('default = "ollama"', 'default = "cloud"')
            path.write_text(s)
            with self.assertRaises(RuntimeError):
                r.prepare_config()
            self.assertEqual(path.read_text(), s)

    def test_cloud_model_rejected(self):
        with self.assertRaises(RuntimeError):
            r.chat_command("qwen:cloud")

    def test_local_model_routes_to_simple_ollama(self):
        cmd = r.chat_command("qwen3.5:2b")
        self.assertEqual(cmd[cmd.index("-e") + 1], "ollama")
        self.assertEqual(cmd[cmd.index("-a") + 1], "simple")

if __name__ == "__main__":
    unittest.main()
