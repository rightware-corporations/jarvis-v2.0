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


class ToolChatAdapter:
    def __init__(self, model: str, *, sites: tuple[str, ...], persona: str, browser_fetcher=None,
                 start_url: str | None = None, search_template: str | None = None,
                 engine_factory=None, budgets: Budgets | None = None, max_turns: int = 6, timeout_seconds: float = 180.0,
                 audit_path=None, clock=time.monotonic):
        if not sites:
            raise ValueError("ToolChatAdapter exige sites autorizados (allowlist exacta)")
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
            session = AgentSession(self._engine(), self.model, allow={"browse"}, confirm=lambda q: None,
                                   sites=self.sites, browser_fetcher=self.browser_fetcher, budgets=self.budgets,
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
