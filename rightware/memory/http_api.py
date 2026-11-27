"""INT01: minimal personal-memory screen routes (only routed when the host enabled memory; see gui/policy.py
``MEMORY_ALLOW``). The owner is the authenticated session's server-declared owner, never the request.

* ``GET  /v1/rightware/memory``          → {memories: [{id, category, topic, content, updated_at}]}
* ``POST /v1/rightware/memory/correct``  JSON {"memory_id": "m-…", "text": "<words typed by the user>"} — the typed
  text IS the user's authorised wording (screened for secrets/ID numbers/instructions); stored as is.
* ``POST /v1/rightware/memory/delete``   JSON {"memory_id": "m-…"}
No automatic learning: nothing here creates memories from conversations or documents.
"""
from __future__ import annotations

import json
import re

from rightware.knowledge.http_api import _body, _json
from rightware.memory import policy as P
from rightware.memory.personal import PersonalMemory

LIST, CORRECT, DELETE = "/v1/rightware/memory", "/v1/rightware/memory/correct", "/v1/rightware/memory/delete"
ROUTES = {("GET", LIST), ("POST", CORRECT), ("POST", DELETE)}


async def handle(memory: PersonalMemory, scope, receive, send) -> bool:
    key = (scope.get("method"), scope.get("path"))
    if key not in ROUTES:
        return False
    owner = memory.owner()
    if owner is None:
        await _json(send, 403, {"status": "REFUSED", "reason": "sessão sem identidade: memória indisponível"})
        return True
    if key == ("GET", LIST):
        await _json(send, 200, {"memories": [{"id": m.id, "category": m.category, "topic": m.topic,
                                              "content": m.content, "updated_at": m.updated_at}
                                             for m in memory.store.active(owner)]})
        return True
    raw = await _body(receive, 2048)
    try:
        req = json.loads(raw or b"{}")
        mid = req.get("memory_id", "")
        if not isinstance(mid, str) or not re.fullmatch(r"m-(?:[0-9a-f]{8}|[0-9a-f]{32})", mid):
            raise ValueError("invalid memory ID")
    except (ValueError, AttributeError, TypeError):
        await _json(send, 400, {"status": "REFUSED", "reason": "pedido inválido"})
        return True
    if key == ("POST", DELETE):
        ok = memory.store.delete(owner, mid)
        await _json(send, 200 if ok else 404, {"status": "OK" if ok else "NOT_FOUND"})
        return True
    text = " ".join(str(req.get("text", "")).split())[:400]
    why = P.sensitive_reason(text) if text else "texto vazio"
    if why:
        await _json(send, 422, {"status": "REFUSED", "reason": why})
        return True
    import hashlib
    m = memory.store.update(owner, mid, text, {"source": "ecrã de memória", "content_from": "palavras do utilizador",
                                               "message_sha256": hashlib.sha256(text.encode()).hexdigest()[:16]})
    await _json(send, 200 if m else 404, {"status": "OK" if m else "NOT_FOUND"} | ({"content": m.content} if m else {}))
    return True
