"""WEB-01 W3.1: structured calls to the LOCAL model (Ollama on loopback only). The model gets text and returns
JSON; it has no tools, no network and no way to change policy. Every output is validated by the host."""
from __future__ import annotations

import json
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434"          # loopback only, as rightware.runtime requires


class ModelError(RuntimeError):
    pass


def ollama_json(model: str, system: str, user: str, *, timeout: float = 180.0, num_ctx: int = 8192,
                num_predict: int = 900) -> tuple[str, float]:
    """(raw text, seconds). JSON mode, temperature 0, thinking off. Raises ModelError on transport failure."""
    body = json.dumps({"model": model, "stream": False, "format": "json", "think": False,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       "options": {"temperature": 0, "num_ctx": num_ctx, "num_predict": num_predict}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never through a proxy
    t0 = time.monotonic()
    try:
        with opener.open(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelError(f"modelo local indisponível ({type(exc).__name__})") from None
    return str(data.get("message", {}).get("content", "")), round(time.monotonic() - t0, 2)


def local_model(model: str):
    """Callable (system, user) -> (raw, seconds) bound to one local model; injectable in tests."""
    return lambda system, user: ollama_json(model, system, user)
