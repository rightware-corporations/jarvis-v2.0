"""JRV-K01 document routes for the GUI bridge — READY BUT NOT ROUTED.

The B6 gateway (``rightware/gui/policy.py``, reserved to the B6 owner) dispatches only exact (method, path) pairs in
``ALLOW``. These handlers become reachable only after the B6 owner adds the contract in
``docs/engineering/JRV_K01_GATEWAY_CONTRACT.md`` (ALLOW entries + body limit). Until then nothing here is exposed;
the gateway is not bypassed (no upload through the chat route).

Contract:
* ``POST /v1/rightware/documents/upload`` — raw body (the file), header ``X-Rightware-Filename`` (display label only);
  max 5 MB (gateway body limit). → {status, document_id, name, kind, units, segments, injection_suspected} or
  {status: REFUSED, reason}.
* ``GET /v1/rightware/documents`` → {documents: [{id, name, kind, units, created_at}]}.
* ``POST /v1/rightware/documents/delete`` — JSON {"document_id": "d-…"} → {status}.
The owner always comes from the host (M01 identity contract), never from the request.
"""
from __future__ import annotations

import json
import re
from urllib.parse import unquote

from rightware.knowledge.library import DocumentLibrary

UPLOAD, LIST, DELETE = "/v1/rightware/documents/upload", "/v1/rightware/documents", "/v1/rightware/documents/delete"
ROUTES = {("POST", UPLOAD), ("GET", LIST), ("POST", DELETE)}
MAX_BODY = 5 * 1024 * 1024


async def _body(receive, limit: int) -> bytes | None:
    chunks, size = [], 0
    while True:
        msg = await receive()
        b = msg.get("body", b"")
        size += len(b)
        if size > limit:
            return None
        chunks.append(b)
        if not msg.get("more_body"):
            return b"".join(chunks)


async def _json(send, status: int, obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"cache-control", b"no-store")]})
    await send({"type": "http.response.body", "body": data})


async def handle(library: DocumentLibrary, scope, receive, send) -> bool:
    """Serve one of the document routes. Returns False if (method, path) is not a document route."""
    key = (scope.get("method"), scope.get("path"))
    if key not in ROUTES:
        return False
    if key == ("GET", LIST):
        docs = [{"id": d.id, "name": d.name, "kind": d.kind, "units": d.units, "created_at": d.created_at}
                for d in library.store.list(library.owner())]
        await _json(send, 200, {"documents": docs})
        return True
    body = await _body(receive, MAX_BODY)
    if body is None:
        await _json(send, 413, {"status": "REFUSED", "reason": "ficheiro acima do limite"})
        return True
    if key == ("POST", UPLOAD):
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        name = unquote(headers.get("x-rightware-filename", ""))[:255]
        r = library.upload(name, body)
        await _json(send, 200 if r["status"] in ("OK", "DUPLICATE") else 422, r)
        return True
    try:
        did = json.loads(body or b"{}").get("document_id", "")
        if not isinstance(did, str) or not re.fullmatch(r"d-(?:[0-9a-f]{8}|[0-9a-f]{32})", did):
            raise ValueError("invalid document ID")
    except (ValueError, AttributeError, TypeError):
        await _json(send, 400, {"status": "REFUSED", "reason": "pedido inválido"})
        return True
    ok = library.store.delete(library.owner(), did)
    await _json(send, 200 if ok else 404, {"status": "OK" if ok else "NOT_FOUND"})
    return True
