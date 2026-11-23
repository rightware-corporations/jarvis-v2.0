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


CONV_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")
# Capabilities that exist in the product vision but are NOT integrated: shown as such, never simulated.
PENDING_CAPABILITIES = (
    ("voz", "Voz multilingue", "NAO_INTEGRADA", "STT/TTS não instalados nem validados em hardware real."),
    ("inteligencia-financeira", "Inteligência financeira (Market Intelligence)", "NAO_INTEGRADA",
     "Exige pesquisa web autorizada (WEB-01), fontes datadas e verificador. Sem cotações nem ordens."),
    ("internet-publica", "Pesquisa na Internet pública", "BLOQUEADA",
     "Acesso de rede externo ainda não autorizado (WEB-01)."),
    ("memoria", "Memória persistente", "NAO_INTEGRADA", "Exige consentimento e armazenamento privado."),
    ("acoes-windows", "Acções locais no computador", "BLOQUEADA", "Exige companion autorizado no dispositivo."),
    ("sic", "Shared Intelligence Core", "NAO_INTEGRADA", "Repositório separado; IAM e consentimento pendentes."),
)
CAPABILITY_STATUS = {"comparar-versoes-ensaio": ("INTEGRADA", "Tarefa supervisionada P1 (catálogo sintético).",
                                                 "Comparação supervisionada de documentos (ensaio)"),
                     "pesquisa-fixture-goose": ("PARCIAL", "Missão goose em catálogo sintético isolado; "
                                                "experimental, sujeita ao desempenho do anfitrião.",
                                                "Missão de investigação goose (catálogo sintético)"),
                     "pesquisa-publica": ("PARCIAL", "WEB-01 W2: pesquisa de leitura sobre corpus FIXTURE local, com "
                                          "recibos e verificador; sem acesso à Internet (W3 exige autorização).",
                                          "Pesquisa pública de leitura (fontes fixture)")}


class _RecordingControl:
    """Transparent view of the SAME ControlPlane that records the structured outcome of runs started by the
    bridge (the Console renders the text; the HUD needs the data). No behaviour is changed."""

    def __init__(self, control, sink):
        self._control, self._sink = control, sink

    def __getattr__(self, name):
        return getattr(self._control, name)

    def authorize_and_run(self, code, on_start=None):
        def started():
            self._sink("started", getattr(self._control, "_active", None))
            if on_start:
                on_start()
        outcome = self._control.authorize_and_run(code, started)
        self._sink("finished", outcome)
        return outcome


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
        self.task_capability: str | None = None
        self.task_outcome = None                             # last TaskOutcome / Refusal (structured, for the HUD)
        self._conv: OrderedDict[tuple, tuple[str, str]] = OrderedDict()   # (auth session, conv id) → (model, sid)
        self._inflight: dict[str, tuple] = {}               # request id → (entry, facade session)
        self._inflight_lock = threading.Lock()
        self._engine_cache: tuple[float, set | None] = (0.0, None)

    # ------------------------------------------------------------------ ASGI
    async def __call__(self, scope, receive, send):
        if scope["path"] == "/v1/models":
            models = await asyncio.to_thread(self.models)
            return await send_json(send, 200, {"object": "list", "data": [
                {"id": m, "object": "model", "owned_by": "rightware"} for m in models]})
        if scope["path"] == "/v1/analytics/identity":
            return await send_json(send, 200, ANALYTICS_OFF)
        if scope["path"] == "/v1/rightware/state":
            return await send_json(send, 200, await asyncio.to_thread(self.state))
        body, too_big = b"", False
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return None
            if not too_big:                                     # never buffer beyond the limit (drain only)
                body += msg.get("body", b"")
                if len(body) > MAX_BODY:
                    too_big, body = True, b""
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
        if scope["path"].startswith("/v1/rightware/tasks/"):
            status, payload = await asyncio.to_thread(self.task_api, scope["path"].rsplit("/", 1)[1], req)
            self.audit.record("http", "POST", scope["path"], "TASK_API", payload.get("state", payload.get("error", "")))
            return await send_json(send, status, payload)
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
        conv = dict((bytes(k).lower(), bytes(v)) for k, v in scope.get("headers") or []).get(b"x-rightware-conversation")
        conv = conv.decode("ascii", "replace") if conv else None
        conv_key = (scope.get("rightware.session") or "-", conv) if conv and CONV_RE.fullmatch(conv) else None
        t0 = time.monotonic()
        if stream:
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/event-stream; charset=utf-8"),
                                    (b"x-rightware-request-id", rid.encode()), *SECURITY_HEADERS]})
            await self._event(send, "inference_start", {"id": rid})
        task = asyncio.ensure_future(asyncio.to_thread(self.respond, model, turns, rid, conv_key))
        disconnect = asyncio.ensure_future(receive())       # completes only when the client goes away (R-4)
        gone = False
        while True:
            done, _ = await asyncio.wait({task, disconnect}, timeout=KEEPALIVE_SECONDS,
                                         return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                break
            if disconnect in done and not gone:
                gone = disconnect.result().get("type") == "http.disconnect"
                if gone:
                    await asyncio.to_thread(self.cancel_inflight, rid)
                    continue
            if stream and not gone:
                await send({"type": "http.response.body", "body": b": keep-alive\n\n", "more_body": True})
        if not disconnect.done():
            disconnect.cancel()
        kind, text, meta = task.result()
        if gone:
            self.audit.record("http", "POST", scope["path"], "CANCELLED_BY_CLIENT", kind, request_id=rid,
                              seconds=round(time.monotonic() - t0, 3))
            return None
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

    def respond(self, model: str, turns: list[tuple[str, str]], rid: str = "",
                conv_key: tuple | None = None) -> tuple[str, str, dict]:
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
            return self.chat(model, turns, tag, rid, conv_key)
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

    def _conv_session(self, model: str, conv_key: tuple) -> str:
        """R-5: explicit conversation id (sent by the HUD), bound to the authenticated local session."""
        entry = self.entries[model]
        key = (*conv_key, model)
        with self._sessions_lock:
            hit = self._conv.pop(key, None)
            if hit is not None:
                self._conv[key] = hit
                return hit[1]
            while len(self._conv) >= self.max_sessions:
                _, (m_old, sid_old) = self._conv.popitem(last=False)
                try:
                    self.entries[m_old].text_facade.close_session(sid_old)
                except ValueError:
                    pass
            sid = entry.text_facade.open_session()
            self._conv[key] = (model, sid)
            return sid

    def cancel_inflight(self, rid: str) -> bool:
        """R-4: client went away → cancel the facade request AND stop the generation in the local engine."""
        with self._inflight_lock:
            item = self._inflight.get(rid)
        if item is None:
            return False
        entry, sid = item
        try:
            entry.text_facade.cancel(sid)
        except ValueError:
            pass
        self._abort_adapter(entry)
        return True

    @staticmethod
    def _abort_adapter(entry) -> None:
        abort = getattr(getattr(entry.text_facade, "_adapter", None), "abort", None)
        if callable(abort):
            abort()

    def chat(self, model: str, turns: list[tuple[str, str]], tag: str = "", rid: str = "",
             conv_key: tuple | None = None) -> tuple[str, str, dict]:
        from rightware.console import STATES, classify
        entry = self.entries[model]
        sid = self._conv_session(model, conv_key) if conv_key else self._session_for(model, turns[:-1])
        text = turns[-1][1]
        with self._inflight_lock:
            self._inflight[rid] = (entry, sid)
        try:
            result = entry.submit_text(sid, text)
        except ValueError:
            out = "**[Entrada inválida]**\n\nO texto está vazio, é demasiado longo ou tem caracteres de controlo.\n"
            return "INVALID", out + tag, {}
        finally:
            with self._inflight_lock:
                self._inflight.pop(rid, None)
        if any(d in ("TIMEOUT", "CANCELLED") for d in result.diagnostics):
            self._abort_adapter(entry)                      # never leave an orphan generation holding the model
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
        facade = entry.text_facade
        prior = turns[:-1]
        if len(prior) > 2 * facade.max_turns or sum(len(t) for _, t in prior) > facade.max_history_chars:
            out += (f"\n\n_Contexto: o modelo só considera as últimas {facade.max_turns} trocas "
                    f"(máx. {facade.max_history_chars} caracteres) desta conversa._")
        out = out + "\n" + tag
        if not conv_key:
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
            console = self.console_cls(self.control.entry, self.default_model, buf,
                                       _RecordingControl(self.control, self._task_event))
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

    # ------------------------------------------------------------------ UI-02 HUD API (same ControlPlane)
    def _task_event(self, kind, value) -> None:
        if kind == "started":
            self.task_capability = value
        else:
            self.task_outcome = value

    def engine_models(self) -> set | None:
        t, cached = self._engine_cache
        if time.monotonic() - t < 5.0:
            return cached
        installed = self.installed_models()
        self._engine_cache = (time.monotonic(), installed)
        return installed

    def capabilities(self) -> list[dict]:
        caps = [{"id": "conversa", "label": "Conversa com o modelo local", "status": "INTEGRADA",
                 "reason": "Sem ferramentas; respostas do modelo NÃO verificadas."}]
        for c in (self.control.capabilities if self.control is not None else ()):
            status, reason, label = CAPABILITY_STATUS.get(c, ("INTEGRADA", "", c))
            caps.append({"id": c, "label": label, "description": self.control.describe(c), "status": status,
                         "reason": reason, "mission": True})
        caps += [{"id": i, "label": label, "status": st, "reason": why} for i, label, st, why in PENDING_CAPABILITIES]
        return caps

    @staticmethod
    def outcome_dict(outcome) -> dict | None:
        from rightware.control_plane import LABELS, Refusal
        if outcome is None:
            return None
        if isinstance(outcome, Refusal):
            return {"state": outcome.state.value, "label": LABELS[outcome.state], "verified": False,
                    "refusal": outcome.reason}
        return {"state": outcome.state.value, "label": LABELS[outcome.state], "verified": bool(outcome.verified),
                "capability": outcome.capability, "operational_state": outcome.operational_state,
                "receipts": [{"seq": q, "tool": t, "status": st} for q, t, st in outcome.receipt_events],
                "objectives": [{"id": o, "status": st, "receipt": seq} for o, st, seq in outcome.objectives],
                "changes": [str(c) for c in (outcome.changes or ())] if outcome.verified else [],
                "commentary_unverified": outcome.model_commentary_unverified or "",
                "seconds": outcome.seconds, "error_code": outcome.error_code, "halt": outcome.halt_reason_code,
                "findings": list(getattr(outcome, "findings", ()) or ()),
                "sources": [dict(s) for s in (getattr(outcome, "sources", ()) or ())]}

    def state(self) -> dict:
        """Everything the HUD shows comes from here (ControlPlane + facade + engine). Never the operator code."""
        installed = self.engine_models()
        control = self.control
        pending = getattr(control, "_pending", None) if control is not None else None
        running = bool(control is not None and control.running)
        with self._inflight_lock:
            busy = len(self._inflight)
        return {
            "engine": {"healthy": installed is not None, "models": self.models() if installed is not None else [],
                       "default_model": self.default_model},
            "model_busy": busy,
            "capabilities": self.capabilities(),
            "pending": ({"capability": pending["capability"],
                         "expires_in": max(0, round(pending["expires"] - control._clock()))} if pending else None),
            "task": {"running": running, "capability": self.task_capability if running else None,
                     "elapsed": round(time.monotonic() - self.task_started, 1)
                     if running and self.task_started else None},
            "last": self.outcome_dict(self.task_outcome) if not running else None,
        }

    def task_api(self, action: str, req) -> tuple[int, dict]:
        from rightware.control_plane import LABELS, State
        if self.control is None:
            return 409, {"error": "SEM_TAREFAS_ACTIVADAS"}
        req = req if isinstance(req, dict) else {}
        if action == "request":
            cap = req.get("capability")
            if not isinstance(cap, str):
                return 400, {"error": "PEDIDO_INVALIDO"}
            state, code = self.control.request(cap)
            out = {"state": state.value, "label": LABELS[state]}
            if state == State.AUTORIZACAO_NECESSARIA:
                # Local single-operator mode (operator decision): the code is shown to be TYPED by the operator.
                out.update(code=code, description=self.control.describe(cap), expires_in=120)
            return 200, out
        if action == "authorize":
            code = req.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[0-9A-Fa-f]{6}", code.strip()):
                return 400, {"error": "CODIGO_EM_FALTA_OU_INVALIDO", "state": "TAREFA_NAO_AUTORIZADA"}
            text = self.authorize(code.strip())
            return 200, {"state": "SUBMETIDO", "text": text, "hud": self.state()}
        if action == "cancel":
            return 200, {"state": "CANCELAMENTO_PEDIDO" if self.control.cancel() else "SEM_TAREFA_EM_CURSO"}
        return 404, {"error": "ACCAO_DESCONHECIDA"}
