"""Scripted FAKE model with an Ollama/OpenAI-compatible surface (labs, deterministic).

Lets the REAL goose binary be driven by a known sequence of model outputs, so its effective dispatch
behaviour can be demonstrated without any real model: e.g. "if the model emits ``load_skill`` even though
it was never offered, does goose execute it?".

Endpoints: ``POST /api/show`` (minimal model info) and ``POST /v1/chat/completions`` (SSE stream). Each
chat request consumes the next scripted step: ``{"tool": name, "args": {...}}`` or ``{"text": "..."}``.
Every request is logged (offered tool names only) to ``--log``.
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def sse_chunks(step: dict, n: int) -> list[bytes]:
    base = {"id": f"fake-{n}", "object": "chat.completion.chunk", "created": 0, "model": "fake"}
    if "tool" in step:
        delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": f"call_{n}", "type": "function",
                                                      "function": {"name": step["tool"],
                                                                   "arguments": json.dumps(step.get("args", {}))}}]}
        finish = "tool_calls"
    else:
        delta, finish = {"role": "assistant", "content": step.get("text", "")}, "stop"
    first = {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
    last = {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
    return [f"data: {json.dumps(first)}\n\n".encode(), f"data: {json.dumps(last)}\n\n".encode(), b"data: [DONE]\n\n"]


def make_handler(script: list[dict], log: Path):
    state = {"n": 0}
    lock = threading.Lock()

    class Fake(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _json(self, code, obj):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0") or 0)) or b"{}")
            if self.path.startswith("/api/show"):
                return self._json(200, {"capabilities": ["completion", "tools"], "details": {"family": "fake"},
                                        "model_info": {"general.architecture": "fake", "fake.context_length": 65536}})
            if not self.path.startswith("/v1/chat/completions"):
                return self._json(404, {"error": "not found"})
            with lock:
                n = state["n"]
                state["n"] += 1
                step = script[n] if n < len(script) else {"text": "fim"}
                tools = [(t.get("function") or {}).get("name") for t in body.get("tools") or []]
                with log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"n": n, "offered": tools, "step": step}) + "\n")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            for chunk in sse_chunks(step, n):
                self.wfile.write(chunk)
                self.wfile.flush()

        def do_GET(self):
            self._json(200, {"version": "fake"})

        def log_message(self, fmt, *args):
            pass

    return Fake


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--script", type=Path, required=True)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--port", type=int, default=11434)
    a = p.parse_args(argv)
    script = json.loads(a.script.read_text(encoding="utf-8"))
    with ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(script, a.log)) as s:
        s.serve_forever()


if __name__ == "__main__":
    main()
