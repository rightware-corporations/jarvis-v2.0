"""UI-01: RIGHTWARE runtime behind the original OpenJarvis chat API (pure ASGI; no new frontend/backend logic).

``POST /v1/chat/completions`` (the route the original GUI already uses) is answered by the EXISTING RIGHTWARE
stack instead of an OpenJarvis agent:

* plain messages → ``TaskEntry``/``TextFacade`` (the same tool-free path as ``python jarvis.py console``): no tool
  is ever offered to the model; a request that carries ``tools``/``functions``/``tool_choice`` is refused;
* lines starting with ``/`` → the SAME console command handling over the SAME ``ControlPlane``
  (``/tarefas``, ``/tarefa ID``, ``/autorizar CODE``, ``/estado``, ``/cancelar``, ``/ajuda``, ``/capacidades``).
  Authorization is ONLY the operator's single-use code validated by the Control Plane; there is no click path.
  ``/autorizar`` starts the run in the background; ``/estado`` shows progress and the final, verifier-decided
  result; ``/cancelar`` cancels it through the Control Plane.

Conversation continuity: the facade (host) owns the history. Each GUI transcript is mapped to a facade session by
a hash of the exact transcript the bridge itself produced, so the client cannot inject a fabricated history; an
unknown or edited transcript starts a fresh session (isolation between conversations).
Responses are rendered as Markdown with explicit labels: model text is "NÃO verificada"; Control Plane output keeps
the console's state labels ("Resultado verificado por evidência…", "Comentário do modelo (NÃO verificado)").
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import secrets
import threading
import time
from collections import OrderedDict

from rightware.gui.policy import SECURITY_HEADERS, AuditLog, send_json

MAX_BODY = 256 * 1024
MAX_MESSAGES = 64
KEEPALIVE_SECONDS = 10.0
TOOL_KEYS = ("tools", "functions", "tool_choice", "function_call")
ANALYTICS_OFF = {"enabled": False, "anon_id": "", "host": "", "key": "", "choice_recorded": True}
MODEL_FOOTER = "_RIGHTWARE · resposta do modelo local `{model}` — **NÃO verificada** · sem ferramentas · " \
               "sem memória persistente_"


def transcript_key(model: str, turns: list[tuple[str, str]]) -> str:
    h = hashlib.sha256(model.encode())
    for role, text in turns:
        h.update(b"\x00" + role.encode() + b"\x01" + text.encode("utf-8"))
    return h.hexdigest()


def md_console(text: str) -> str:
    """Console output → Markdown, keeping verified and NOT verified parts visually distinct."""
    out, unverified = [], False
    for line in text.replace("(Ctrl+C cancela)", "(/cancelar cancela)").splitlines():
        if line.startswith("Comentário do modelo (NÃO verificado)"):
            unverified = True
            out.append("> ⚠️ **Comentário do modelo — NÃO verificado** (não é evidência)")
            continue
        if unverified:
            out.append("> " + line.strip())
            continue
        m = re.fullmatch(r"\[(.+)\](.*)", line)
        out.append(f"**[{m.group(1)}]**{m.group(2)}" if m else line)
        out.append("") if m else None
    return "\n".join(x for x in out if x is not None).strip() + "\n"


class ChatBridge:
    """ASGI app for the bridge routes. ``entries`` maps allowed model → TaskEntry (default model first)."""

    def __init__(self, *, entries: dict, default_model: str, control=None, audit: AuditLog,
                 console_cls=None, max_sessions: int = 12, ollama_tags_url: str = "http://127.0.0.1:11434/api/tags"):
        if default_model not in entries:
            raise ValueError("default model must have an entry")
        from rightware.console import Console
        self.entries, self.default_model, self.control, self.audit = dict(entries), default_model, control, audit
        self.console_cls = console_cls or Console
        self.ollama_tags_url = ollama_tags_url
        entry = control.entry if control is not None else entries[default_model]
        self._console = self.console_cls(entry, default_model, io.StringIO(), control)
        self._console_lock = threading.Lock()
        self._sessions: OrderedDict[str, tuple[str, str]] = OrderedDict()   # key → (model, facade session id)
        self._sessions_lock = threading.Lock()
        self.max_sessions = max_sessions
        self.task_out: io.StringIO | None = None
        self.task_thread: threading.Thread | None = None
        self.task_started: float | None = None

    # ------------------------------------------------------------------ ASGI
    async def __call__(self, scope, receive, send):
        if scope["path"] == "/v1/models":
            models = await asyncio.to_thread(self.models)
            return await send_json(send, 200, {"object": "list", "data": [
                {"id": m, "object": "model", "owned_by": "rightware"} for m in models]})
        if scope["path"] == "/v1/analytics/identity":
            return await send_json(send, 200, ANALYTICS_OFF)
        body, too_big = b"", False
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return None
            body += msg.get("body", b"")
            if len(body) > MAX_BODY:
                too_big = True
            if not msg.get("more_body"):
                break
        if too_big:
            return await self._refuse(send, 413, "BODY_TOO_LARGE")
        try:
            req = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return await self._refuse(send, 400, "INVALID_JSON")
        if scope["path"] == "/v1/analytics/preference":       # "Continue without sharing": accepted, no effect
            if isinstance(req, dict) and req.get("enabled") is False:
                return await send_json(send, 200, ANALYTICS_OFF)
            return await self._refuse(send, 403, "ANALYTICS_DISABLED_BY_POLICY", scope["path"])
        if not isinstance(req, dict):
            return await self._refuse(send, 400, "INVALID_REQUEST")
        if any(req.get(k) for k in TOOL_KEYS):
            return await self._refuse(send, 403, "TOOLS_NOT_ALLOWED")
        msgs = req.get("messages")
        if (not isinstance(msgs, list) or not msgs or len(msgs) > MAX_MESSAGES
                or not all(isinstance(m, dict) and isinstance(m.get("role"), str)
                           and isinstance(m.get("content"), str) for m in msgs)):
            return await self._refuse(send, 400, "INVALID_MESSAGES")
        turns = [(m["role"], m["content"]) for m in msgs if m["role"] in ("user", "assistant")]
        if not turns or turns[-1][0] != "user":
            return await self._refuse(send, 400, "LAST_MESSAGE_NOT_USER")
        model = req.get("model") or self.default_model
        stream = bool(req.get("stream"))
        rid = "rw-" + secrets.token_hex(8)
        t0 = time.monotonic()
        if stream:
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/event-stream; charset=utf-8"),
                                    (b"x-rightware-request-id", rid.encode()), *SECURITY_HEADERS]})
            await self._event(send, "inference_start", {"id": rid})
        task = asyncio.ensure_future(asyncio.to_thread(self.respond, model, turns, rid))
        while True:
            done, _ = await asyncio.wait({task}, timeout=KEEPALIVE_SECONDS)
            if done:
                break
            if stream:
                await send({"type": "http.response.body", "body": b": keep-alive\n\n", "more_body": True})
        kind, text, meta = task.result()
        seconds = round(time.monotonic() - t0, 3)
        self.audit.record("http", "POST", scope["path"], "ANSWER", kind, request_id=rid, model=model,
                          seconds=seconds, **meta)
        if not stream:
            return await send_json(send, 200, {
                "id": rid, "object": "chat.completion", "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                             "finish_reason": "stop"}]}, [(b"x-rightware-request-id", rid.encode())])
        chunk = {"id": rid, "object": "chat.completion.chunk", "model": model,
                 "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}]}
        await self._data(send, chunk)
        await self._data(send, {"id": rid, "object": "chat.completion.chunk", "model": model,
                                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
        await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})
        return None

    async def _refuse(self, send, status, reason, path="/v1/chat/completions"):
        self.audit.record("http", "POST", path, "DENY", reason)
        return await send_json(send, status, {"error": "BLOQUEADO_PELA_POLITICA_RIGHTWARE", "reason": reason})

    @staticmethod
    async def _event(send, name, data):
        await send({"type": "http.response.body", "more_body": True,
                    "body": f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()})

    @staticmethod
    async def _data(send, obj):
        await send({"type": "http.response.body", "more_body": True,
                    "body": ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")})

    # ------------------------------------------------------------------ synchronous core
    def models(self) -> list[str]:
        """Host-allowed models, in host order. When the local engine answers, only those installed; when it does
        not, the allowlist itself, so that a message produces the explicit inference error instead of a silent
        model-less interface (the engine state is reported by /health)."""
        installed = self.installed_models()
        allowed = list(self.entries)
        return allowed if installed is None else [m for m in allowed if m in installed]

    def installed_models(self) -> set[str] | None:
        import urllib.request
        try:
            with urllib.request.urlopen(self.ollama_tags_url, timeout=2.0) as r:
                return {m.get("name") for m in json.loads(r.read().decode()).get("models", [])}
        except (OSError, ValueError):
            return None

    def respond(self, model: str, turns: list[tuple[str, str]], rid: str = "") -> tuple[str, str, dict]:
        """(kind, markdown, audit meta). Never raises: internal errors are shown as failures. Every reply ends
        with the request id, which also appears in the audit log (GUI ↔ server correlation)."""
        text = turns[-1][1].strip()
        tag = f"\n`{rid}`\n" if rid else ""
        try:
            if text.startswith("/"):
                return "COMMAND", self.command(text) + tag, {"command": text.split()[0][:16]}
            if model not in self.entries:
                return "REFUSED", ("**[Modelo não permitido]**\n\nO modelo pedido não está na lista configurada "
                                   "pelo anfitrião: " + ", ".join(f"`{m}`" for m in self.entries) + ".\n" + tag), {}
            return self.chat(model, turns, tag)
        except Exception as exc:                                   # never a fabricated answer
            return "ERROR", (f"**[Erro interno do JARVIS]**\n\nNada foi executado. (código: {type(exc).__name__})\n"
                             + tag), {}

    def _session_for(self, model: str, prior: list[tuple[str, str]]) -> str:
        entry = self.entries[model]
        key = transcript_key(model, prior)
        with self._sessions_lock:
            hit = self._sessions.pop(key, None)
            if hit is not None:
                return hit[1]
            while len(self._sessions) >= self.max_sessions:
                _, (m_old, sid_old) = self._sessions.popitem(last=False)
                try:
                    self.entries[m_old].text_facade.close_session(sid_old)
                except ValueError:
                    pass
            return entry.text_facade.open_session()

    def chat(self, model: str, turns: list[tuple[str, str]], tag: str = "") -> tuple[str, str, dict]:
        from rightware.console import STATES, classify
        entry = self.entries[model]
        sid = self._session_for(model, turns[:-1])
        text = turns[-1][1]
        try:
            result = entry.submit_text(sid, text)
        except ValueError:
            out = "**[Entrada inválida]**\n\nO texto está vazio, é demasiado longo ou tem caracteres de controlo.\n"
            return "INVALID", out + tag, {}
        state = classify(result)
        if state == "RESPOSTA_DO_MODELO":
            out = result.text.strip() + "\n\n---\n" + MODEL_FOOTER.format(model=model)
        elif state == "PLANO_SEM_EXECUCAO":
            out = (f"**[{STATES[state]}]**\n\n" + result.text.strip() + "\n\n---\n"
                   + MODEL_FOOTER.format(model=model))
        else:
            out = f"**[{STATES.get(state, state)}]**\n\n{result.text}"
            if result.diagnostics:
                out += f"\n\n(código: {', '.join(result.diagnostics)})"
            if any(d in ("MODEL_UNAVAILABLE", "TIMEOUT", "MODEL_ERROR") for d in result.diagnostics):
                out += ("\n\n**Acção:** confirme que o Ollama está a correr em `127.0.0.1:11434` com o modelo "
                        f"`{model}` instalado e tente de novo. Nenhuma resposta foi gerada.")
        out = out + "\n" + tag
        with self._sessions_lock:
            self._sessions[transcript_key(model, [*turns, ("assistant", out)])] = (model, sid)
        return state, out, {"status": result.status.value, "diag": ",".join(result.diagnostics),
                            "facade_request_id": result.request_id}

    def command(self, line: str) -> str:
        line = line.strip()
        m = re.fullmatch(r"/autorizar\s+(\S+)", line)
        if m:
            return self.authorize(m.group(1))
        if line == "/autorizar":
            return ("**[Tarefa não autorizada]**\n\nFalta o código do operador. A autorização exige "
                    "`/autorizar CÓDIGO` com o código de uso único mostrado pelo anfitrião. Nada foi executado.\n")
        if line == "/sair":
            return "Na interface gráfica a sessão termina ao fechar o separador. Nada é guardado.\n"
        if line == "/estado":
            return self.status()
        buf = io.StringIO()
        with self._console_lock:
            self._console.out = buf
            self._console.handle(line)
        return md_console(buf.getvalue())

    def authorize(self, code: str) -> str:
        if self.control is None:
            return "**[Tarefa não autorizada]**\n\nNenhuma tarefa supervisionada foi activada pelo anfitrião.\n"
        with self._console_lock:
            if self.task_thread is not None and self.task_thread.is_alive():
                return ("**[Tarefa não autorizada]**\n\nJá há uma tarefa em execução. Nada foi iniciado. "
                        "Use `/estado` ou `/cancelar`.\n")
            buf = io.StringIO()
            console = self.console_cls(self.control.entry, self.default_model, buf, self.control)
            thread = threading.Thread(target=console.task_authorize, args=(code,), daemon=True,
                                      name="jarvis-gui-task")
            self.task_out, self.task_thread, self.task_started = buf, thread, time.monotonic()
            thread.start()
        thread.join(3.0)                                    # refusals (bad code) come back immediately
        text = md_console(buf.getvalue())
        if thread.is_alive():
            text += "\nA tarefa continua em execução. Use `/estado` para acompanhar e `/cancelar` para cancelar.\n"
        return text

    def status(self) -> str:
        buf = io.StringIO()
        with self._console_lock:
            self._console.out = buf
            self._console.handle("/estado")
        out = "```text\n" + buf.getvalue().strip() + "\n```\n"
        if self.task_out is not None:
            alive = self.task_thread is not None and self.task_thread.is_alive()
            secs = time.monotonic() - (self.task_started or time.monotonic())
            out += ("\n**Última tarefa supervisionada** (" + ("em execução" if alive else "terminada")
                    + f", {secs:.0f} s desde a autorização):\n\n" + md_console(self.task_out.getvalue()))
        return out
