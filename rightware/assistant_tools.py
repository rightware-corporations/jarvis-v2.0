"""OP01: the conversational JARVIS core WITH tools, as a TextModel adapter (same ``reply/abort/close`` interface as
``LocalSimpleTextAdapter``), so TextFacade sessions, ControlPlane, cancellation and the GUI bridge stay unchanged.

Each turn runs through the EXISTING, audited ``AgentSession`` (pinned OpenJarvis OrchestratorAgent in
``function_calling`` mode = native Ollama tool calling) with:
* the host-built persona (``rightware.persona``) and the conversation history (continuity);
* ONLY the ``browse`` capability: ``web_open/web_type/web_submit/web_follow/web_find`` through ``PublicBrowser``,
  restricted to an EXACT host allowlist given by the host, GET only, SSRF guards, budgets, receipts;
* ``AgentPolicy`` deciding every call (deny-by-default) — the model only PROPOSES tools.
The model may answer directly (no tool) when its own knowledge is adequate. Search is a tool, not a pipeline.

``activity()`` reports the CURRENT phase derived from the live policy log of the running session (real events
only): A interpretar → A pesquisar (search form) / A consultar fontes (page reads) → A analisar → Resposta concluída.
No network is opened here: real hosts need a host fetcher AND a specific operator authorisation."""
from __future__ import annotations

import threading
import time

from rightware.agent.policy import Budgets

SEARCH_TOOLS = ("web_search", "web_type", "web_submit", "web_find")
READ_TOOLS = ("web_open", "web_follow", "web_read")
MAX_REPLY = 4000


ROUTER_SYSTEM = (
    "Decides se a última mensagem do utilizador precisa de ferramentas. Responde só com JSON "
    "{\"rota\": \"conversa\"} ou {\"rota\": \"ferramentas\"}. Escolhe \"ferramentas\" quando a resposta exige dados "
    "externos ou actuais (cotações, câmbio, ouro, notícias, factos que não sabes com segurança) ou um cálculo numérico "
    "exacto. Escolhe \"conversa\" para cumprimentos, perguntas sobre ti, conselhos, planos e explicações gerais que "
    "não dependem de dados externos nem de contas exactas. Ferramentas disponíveis: {tools}.")


class ModelRouter:
    """The MODEL decides whether a turn needs tools (no keyword rules). One short JSON call to the local model;
    any failure or unexpected output → "ferramentas" (fail-safe: the tool path has the policy and receipts)."""

    def __init__(self, model: str, tools_description: str, call=None):
        self.model, self.system = model, ROUTER_SYSTEM.replace("{tools}", tools_description)
        self._call = call
        self.last: dict = {}

    def __call__(self, text: str, history: tuple[tuple[str, str], ...]) -> str:
        import json as _json
        import time as _time
        t0 = _time.monotonic()
        recent = "\n".join(f"{r}: {t[:300]}" for r, t in tuple(history)[-4:])
        user = (f"Conversa recente:\n{recent}\n\n" if recent else "") + f"Última mensagem: {text}"
        try:
            raw = self._call(self.system, user) if self._call else self._ollama(user)
            route = _json.loads(raw).get("rota")
        except Exception:
            route = None
        route = route if route in ("conversa", "ferramentas") else "ferramentas"
        self.last = {"route": route, "seconds": round(_time.monotonic() - t0, 2)}
        return route

    def _ollama(self, user: str) -> str:
        import json as _json
        import urllib.request
        body = _json.dumps({"model": self.model, "stream": False, "format": "json", "think": False,
                            "messages": [{"role": "system", "content": self.system}, {"role": "user", "content": user}],
                            "options": {"temperature": 0, "num_predict": 20}}).encode()
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=60) as r:
            return _json.loads(r.read())["message"]["content"]


class ToolChatAdapter:
    def __init__(self, model: str, *, sites: tuple[str, ...], persona: str, browser_fetcher=None,
                 start_url: str | None = None, search_template: str | None = None,
                 allow: tuple[str, ...] = ("browse",), extra_tools_factory=None, post_check=None,
                 router=None, direct=None,
                 engine_factory=None, budgets: Budgets | None = None, max_turns: int = 6, timeout_seconds: float = 180.0,
                 audit_path=None, clock=time.monotonic):
        if "browse" in allow and not sites:
            raise ValueError("ToolChatAdapter exige sites autorizados (allowlist exacta)")
        self.allow, self.extra_tools_factory, self.post_check = tuple(allow), extra_tools_factory, post_check
        self.router, self.direct = router, direct    # optional: model-decided direct conversation (no tools)
        self.model, self.sites, self.persona = model, tuple(sites), persona
        self.start_url = start_url                 # host-declared search/entry page (https, inside the allowlist)
        self.search_template = search_template     # host-declared search URL with {q} → model tool web_search(query)
        self.browser_fetcher, self.budgets, self.max_turns = browser_fetcher, budgets, max_turns
        self.timeout_seconds, self.audit_path, self._clock = timeout_seconds, audit_path, clock
        self._engine_factory = engine_factory
        self._lock = threading.RLock()
        self._session = None
        self._abort_backend = None
        self._phase, self._since, self._last = "Pronto", clock(), None

    # -- engine (same loopback Ollama + abortable sockets as the tool-free adapter) ------------------------------
    def _engine(self):
        if self._engine_factory is not None:
            return self._engine_factory()
        from openjarvis.engine.ollama import OllamaEngine
        from rightware.text_adapter import abortable_client
        engine = OllamaEngine(host="http://127.0.0.1:11434", timeout=self.timeout_seconds)
        client, self._abort_backend = abortable_client("http://127.0.0.1:11434", self.timeout_seconds)
        engine._client.close()
        engine._client = client
        return engine

    def reply(self, text: str, history: tuple[tuple[str, str], ...]) -> str:
        from rightware.agent.session import AgentSession
        with self._lock:
            self._phase, self._since = "A interpretar", self._clock()
            if self.router is not None and self.direct is not None and self.router(text, tuple(history)) == "conversa":
                out = self.direct.reply(text, tuple(history))          # same persona, no tools, no receipts
                self._last = {"completion": "ANSWERED_DIRECT", "sources": [], "tools": [], "halted": None, "flags": [],
                              "tool_calls": 0, "route": "conversa"}
                self._phase, self._since = "Resposta concluída", self._clock()
                return out
            begin = getattr(self.browser_fetcher, "begin_question", None)
            if callable(begin):                       # per-question HTTP budget (experimental proxy transport)
                begin()
            extra, records = (self.extra_tools_factory() if self.extra_tools_factory else (None, lambda: []))
            session = AgentSession(self._engine(), self.model, allow=set(self.allow), confirm=lambda q: None,
                                   sites=self.sites, browser_fetcher=self.browser_fetcher, budgets=self.budgets,
                                   extra_tools=extra,
                                   max_turns=self.max_turns, audit_path=self.audit_path, receipts=True,
                                   persona=self.persona, start_url=self.start_url,
                                   search_template=self.search_template)
            self._session = session
            try:
                result = session.run(text, history=tuple(history))
            finally:
                self._session = None
            log = list(getattr(getattr(session, "_policy", None), "log", []) or [])
            self._last = {"completion": result.completion, "sources": [s.get("final_url") for s in result.sources],
                          "tools": [o.tool for o in result.outcomes], "halted": result.halted, "flags": result.flags,
                          "tool_calls": len(log)}
            self._phase, self._since = "Resposta concluída", self._clock()
            out = result.text.strip()
            if self.post_check is not None:              # host annotations (sources, integrity) from tool records
                out += self.post_check(out, records(), text)
            return out if len(out) <= MAX_REPLY else out[:MAX_REPLY] + "\n(resposta truncada pelo limite da interface)"

    def activity(self) -> dict:
        """Real phase of the running turn, from the live AgentPolicy log (no simulation)."""
        session = self._session
        phase = self._phase
        policy = getattr(session, "_policy", None) if session is not None else None
        log = list(getattr(policy, "log", []) or [])
        if session is not None and log:
            last = log[-1]
            if not last.get("allowed"):
                phase = "A analisar"                    # refused call: the model is told and continues
            elif "outcome" not in last:
                phase = "A pesquisar" if last["tool"] in SEARCH_TOOLS else "A consultar fontes"
            else:
                phase = "A analisar"
        calls = len(log) if session is not None else (self._last or {}).get("tool_calls", 0)
        return {"phase": phase, "since": self._since, "tool_calls": calls,
                "sources": [e.get("args", {}).get("url") for e in log if e.get("allowed") and e["tool"] in READ_TOOLS
                            and isinstance(e.get("args"), dict)][:6],
                "last": self._last}

    def abort(self) -> bool:
        session = self._session
        if session is not None:
            session.cancel()
        backend, self._abort_backend = self._abort_backend, None
        if backend is not None:
            backend.abort_all()
        return session is not None

    def close(self) -> None:
        self.abort()
