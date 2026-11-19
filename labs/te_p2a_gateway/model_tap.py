"""Transparent model tap between the executor and Ollama (evidence only, labs).

For every request it records — NOT the prompt content — the endpoint, the model, the number of
messages, the NAMES of the tools offered to the model and any context-size option, then forwards the
request unchanged and streams the response back unchanged. This is the independent proof of the
executor's real tool inventory (what the model could actually call).

Run: python -m labs.te_p2a_gateway.model_tap --upstream http://ollama:11434 --log /evidence/model_requests.jsonl
"""
from __future__ import annotations

import argparse
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def summarise(path: str, body: bytes) -> dict:
    out = {"path": path, "t": round(time.time(), 3)}
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        return {**out, "parse": "not-json"}
    tools = data.get("tools") or []
    names = []
    for t in tools:
        fn = t.get("function", t) if isinstance(t, dict) else {}
        names.append(fn.get("name"))
    out.update(model=data.get("model"), messages=len(data.get("messages") or []), tool_names=names,
               stream=data.get("stream"), options={k: v for k, v in (data.get("options") or {}).items()
                                                   if k in ("num_ctx", "temperature", "num_predict")},
               max_tokens=data.get("max_tokens"), temperature=data.get("temperature"))
    return out


def filter_tools(body: bytes, allowed_suffixes: tuple[str, ...]) -> tuple[bytes, list]:
    """RIGHTWARE allowlist at the model boundary: keep only tools whose name ends with an allowed gateway
    tool name. Returns the (possibly rewritten) body and the names actually forwarded to the model."""
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        return body, []
    tools = data.get("tools")
    if not allowed_suffixes or not isinstance(tools, list):
        return body, [((t.get("function", t) if isinstance(t, dict) else {}).get("name")) for t in tools or []]
    kept = [t for t in tools if isinstance(t, dict)
            and str((t.get("function", t)).get("name", "")).endswith(allowed_suffixes)]
    data["tools"] = kept
    return json.dumps(data).encode("utf-8"), [(t.get("function", t)).get("name") for t in kept]


class ResponseToolFilter:
    """RIGHTWARE allowlist on the MODEL OUTPUT (JRV-BP-043). The executor (goose v1.60.1) dispatches any tool
    the model names that it knows internally — e.g. ``load_skill`` — even when that tool was never offered
    to the model. So filtering the request is not enough: every streamed SSE event is parsed and any
    ``tool_calls`` entry whose name is not allowlisted is REMOVED before the executor sees it. If a response
    asked only for blocked tools, its ``finish_reason`` becomes ``stop`` (fail-closed: nothing executes).
    Unparseable events are passed through unchanged only if they carry no tool call text."""

    def __init__(self, allowed_suffixes: tuple[str, ...]):
        self.allowed = allowed_suffixes
        self.blocked_index: set[int] = set()
        self.allowed_seen = False
        self.blocked: list[str] = []
        self._buffer = b""

    def _ok(self, name: str) -> bool:
        return bool(name) and name.endswith(self.allowed)

    def _event(self, line: bytes) -> bytes | None:
        if not line.startswith(b"data:"):
            return line
        payload = line[5:].strip()
        if payload == b"[DONE]":
            return line
        try:
            data = json.loads(payload)
        except ValueError:
            return None if b"tool_calls" in payload else line          # fail closed on opaque tool data
        for choice in data.get("choices") or []:
            delta = choice.get("delta") or choice.get("message") or {}
            calls = delta.get("tool_calls")
            if isinstance(calls, list):
                kept = []
                for i, call in enumerate(calls):
                    idx = call.get("index", i)
                    name = (call.get("function") or {}).get("name")
                    if name is not None:
                        if self._ok(name):
                            self.allowed_seen = True
                            self.blocked_index.discard(idx)
                        else:
                            self.blocked_index.add(idx)
                            self.blocked.append(name)
                    if idx not in self.blocked_index:
                        kept.append(call)
                if kept:
                    delta["tool_calls"] = kept
                else:
                    delta.pop("tool_calls", None)
            if choice.get("finish_reason") == "tool_calls" and not self.allowed_seen and self.blocked:
                choice["finish_reason"] = "stop"
        return b"data: " + json.dumps(data).encode("utf-8")

    def feed(self, chunk: bytes) -> bytes:
        self._buffer += chunk
        out = []
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            line = line.rstrip(b"\r")
            ev = self._event(line)
            if ev is not None:
                out.append(ev + b"\n")
        return b"".join(out)

    def flush(self) -> bytes:
        rest, self._buffer = self._buffer, b""
        ev = self._event(rest) if rest else None
        return ev or b""

    def filter_json(self, body: bytes) -> bytes:
        """Non-streaming responses (Ollama /api/chat or OpenAI JSON)."""
        try:
            data = json.loads(body)
        except ValueError:
            return body
        targets = [c.get("message") or {} for c in data.get("choices") or []] + [data.get("message") or {}]
        for msg in targets:
            calls = msg.get("tool_calls")
            if isinstance(calls, list):
                keep = [c for c in calls if self._ok((c.get("function") or {}).get("name"))]
                self.blocked += [(c.get("function") or {}).get("name") for c in calls if c not in keep]
                msg["tool_calls"] = keep
        return json.dumps(data).encode("utf-8")


def make_handler(upstream: str, log: Path, lock: threading.Lock, allowed_suffixes: tuple[str, ...] = ()):
    u = urlsplit(upstream)

    class Tap(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _forward(self, method):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
            if method == "POST":
                row = summarise(self.path, body)
                body, forwarded = filter_tools(body, allowed_suffixes)
                row["forwarded_tool_names"] = forwarded
                with lock, log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
            conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=1800)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")}
            conn.request(method, self.path, body=body if method == "POST" else None, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding", "content-length", "connection"):
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            flt = ResponseToolFilter(allowed_suffixes) if allowed_suffixes and method == "POST" else None
            streaming = "event-stream" in (resp.getheader("Content-Type") or "")
            whole = b""
            while True:
                chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
                if not chunk:
                    break
                if flt is not None and not streaming:
                    whole += chunk
                    continue
                if flt is not None:
                    chunk = flt.feed(chunk)
                    if not chunk:
                        continue
                self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
            tail = (flt.filter_json(whole) if not streaming else flt.flush()) if flt is not None else b""
            if tail:
                self.wfile.write(f"{len(tail):X}\r\n".encode() + tail + b"\r\n")
            if flt is not None and flt.blocked:
                with lock, log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"path": self.path, "blocked_tool_calls_in_model_output": flt.blocked}) + "\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            conn.close()

        def do_POST(self):
            self._forward("POST")

        def do_GET(self):
            self._forward("GET")

        def log_message(self, fmt, *args):
            pass

    return Tap


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--upstream", required=True)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--port", type=int, default=11434)
    p.add_argument("--allow-suffix", action="append", default=[],
                   help="only tools whose name ends with one of these reach the model (RIGHTWARE allowlist)")
    a = p.parse_args(argv)
    a.log.parent.mkdir(parents=True, exist_ok=True)
    with ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(a.upstream, a.log, threading.Lock(),
                                                                tuple(a.allow_suffix))) as s:
        s.serve_forever()


if __name__ == "__main__":
    main()
