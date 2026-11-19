"""Minimal MCP server (streamable HTTP, JSON responses only) exposing the RIGHTWARE Tool Gateway.

Auditable on purpose: JSON-RPC 2.0 over ``POST /mcp``; methods ``initialize``, ``ping``, ``tools/list``,
``tools/call``; notifications (``notifications/initialized``, ``notifications/cancelled``) get 202.
No SSE stream (``GET`` → 405), no resources, no prompts, no sampling: the client can do nothing but
list and call the gateway tools.

Every ``tools/call`` goes to ``Gateway.call`` (policy + receipts). Receipts are appended to
``<evidence>/receipts.jsonl`` after each call and the policy audit goes to ``<evidence>/audit.jsonl``.

Run (gateway container): python -m labs.te_p2a_gateway.mcp_http --task T1 --attempt A1 --evidence /evidence
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rightware.agent.policy import Budgets

from labs.te_p2a_gateway.fixture_transport import SYNTHETIC_HOST, fixture_fetcher
from labs.te_p2a_gateway.gateway import Gateway

PROTOCOL_FALLBACK = "2025-03-26"
SERVER_INFO = {"name": "rightware-tool-gateway", "version": "te-p2a-0.1"}
# Code-owned limits for the T1 mission (not model-controlled).
T1_BUDGETS = Budgets(max_calls=15, deadline_seconds=1700)


class McpApp:
    def __init__(self, gateway: Gateway, evidence: Path | None = None):
        self.gateway, self.evidence = gateway, evidence
        self.session_id = secrets.token_hex(16)
        self.requests: list[dict] = []

    def _dump(self):
        if self.evidence is None:
            return
        with (self.evidence / "receipts.jsonl").open("w", encoding="utf-8") as f:
            for r in self.gateway.receipts():
                f.write(json.dumps(dataclasses.asdict(r), sort_keys=True) + "\n")

    def handle(self, msg: dict) -> dict | None:
        method, rid = msg.get("method"), msg.get("id")
        self.requests.append({"method": method, "id": rid})
        if rid is None:                                   # notification
            if method == "notifications/cancelled":
                pass                                       # per-request cancel: calls are synchronous; recorded only
            return None
        if method == "initialize":
            version = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_FALLBACK
            return _ok(rid, {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                             "serverInfo": SERVER_INFO,
                             "instructions": "RIGHTWARE Tool Gateway: only these read-only browsing tools exist; "
                                             "every call is authorised and receipted by RIGHTWARE."})
        if method == "ping":
            return _ok(rid, {})
        if method == "tools/list":
            return _ok(rid, {"tools": self.gateway.tool_specs()})
        if method == "tools/call":
            params = msg.get("params") or {}
            text, is_error = self.gateway.call(params.get("name"), params.get("arguments", {}), rid)
            self._dump()
            return _ok(rid, {"content": [{"type": "text", "text": text}], "isError": is_error})
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def make_handler(app: McpApp):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body=None, extra=None):
            data = b"" if body is None else json.dumps(body).encode("utf-8")
            self.send_response(code)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Mcp-Session-Id", app.session_id)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path.rstrip("/") != "/mcp":
                return self._send(404)
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0") or 0)))
            except ValueError:
                return self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse"}})
            batch = payload if isinstance(payload, list) else [payload]
            replies = [r for r in (app.handle(m) for m in batch if isinstance(m, dict)) if r is not None]
            if not replies:
                return self._send(202)
            return self._send(200, replies if isinstance(payload, list) else replies[0])

        def do_GET(self):
            self._send(405, extra={"Allow": "POST, DELETE"})

        def do_DELETE(self):
            self._send(200)

        def log_message(self, fmt, *args):
            pass

    return Handler


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--attempt", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--upstream", default="http://fixture:8765")
    p.add_argument("--port", type=int, default=8790)
    a = p.parse_args(argv)
    a.evidence.mkdir(parents=True, exist_ok=True)
    gw = Gateway(task_id=a.task, attempt_id=a.attempt, sites=(SYNTHETIC_HOST,), fetcher=fixture_fetcher(a.upstream),
                 budgets=T1_BUDGETS, audit_path=a.evidence / "audit.jsonl")
    app = McpApp(gw, a.evidence)
    with ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(app)) as server:
        print(json.dumps({"gateway": f"http://0.0.0.0:{a.port}/mcp", "task": a.task, "attempt": a.attempt}), flush=True)
        try:
            server.serve_forever()
        finally:
            gw.close()
            app._dump()


if __name__ == "__main__":
    main()
