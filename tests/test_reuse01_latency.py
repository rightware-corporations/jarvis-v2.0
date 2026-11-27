"""REUSE01-B (UNIT/FAKE): every local call on the shared model uses ONE num_ctx, so Ollama never reloads the runner
between router, direct conversation and tool path. Not a latency measurement (see docs/evidence/reuse01/)."""
import io
import json
import os
import unittest
from unittest import mock

from rightware.assistant_tools import ModelRouter, shared_num_ctx
from rightware.text_adapter import LocalSimpleTextAdapter


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SharedNumCtx(unittest.TestCase):
    def test_matches_pinned_openjarvis_engine_default(self):
        from openjarvis.engine.ollama import _default_num_ctx
        self.assertEqual(shared_num_ctx(), _default_num_ctx())
        with mock.patch.dict(os.environ, {"JARVIS_NUM_CTX": "8192"}):
            self.assertEqual(shared_num_ctx(), 8192)

    def test_router_sends_the_shared_num_ctx(self):
        sent = {}

        class Opener:
            def open(self, req, timeout):
                sent.update(json.loads(req.data))
                return _Resp(json.dumps({"message": {"content": '{"rota": "conversa"}'}}).encode())

        with mock.patch("urllib.request.build_opener", return_value=Opener()):
            route = ModelRouter("qwen3.5:2b", "calculadora")("olá", ())
        self.assertEqual(route, "conversa")
        self.assertEqual(sent["options"]["num_ctx"], shared_num_ctx())
        self.assertIs(sent["think"], False)

    def test_direct_adapter_accepts_the_shared_value_and_keeps_bounds(self):
        a = LocalSimpleTextAdapter("qwen3.5:2b", num_ctx=shared_num_ctx())
        self.assertEqual(a.num_ctx, shared_num_ctx())
        self.assertEqual(LocalSimpleTextAdapter("qwen3.5:2b").num_ctx, 4096)   # plain-GUI default unchanged
        with self.assertRaises(ValueError):
            LocalSimpleTextAdapter("qwen3.5:2b", num_ctx=65536)


if __name__ == "__main__":
    unittest.main()
