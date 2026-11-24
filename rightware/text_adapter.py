"""WP-04/D02: opt-in, local-only SimpleAgent adapter (no tools or memory).

Imports from the pinned OpenJarvis submodule are intentionally deferred until
the first reply.  This module is not used by the existing chat/voice/agent CLI.
"""
from __future__ import annotations

from threading import RLock
from typing import Callable

from rightware.runtime import chat_command


class InvalidModelReply(ValueError):
    """The model returned no usable text or a tool/effect-shaped response."""


def abortable_client(base_url: str, timeout: float):
    """UI-02 (R-4): an httpx client whose live sockets can be shut down from another thread. Closing an httpx client
    does NOT interrupt a read already blocked in another thread (measured); shutting the socket down does, and the
    local engine (Ollama) then sees the disconnect and stops generating."""
    import socket
    import threading

    import httpcore
    import httpx

    class RecordingBackend(httpcore.SyncBackend):
        def __init__(self):
            super().__init__()
            self.streams, self.lock = [], threading.Lock()

        def connect_tcp(self, *args, **kwargs):
            stream = super().connect_tcp(*args, **kwargs)
            with self.lock:
                self.streams.append(stream)
            return stream

        def abort_all(self) -> int:
            with self.lock:
                streams, self.streams = self.streams, []
            n = 0
            for stream in streams:
                sock = getattr(stream, "_sock", None)
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                    n += 1
                except (OSError, AttributeError):
                    pass
            return n

    backend = RecordingBackend()
    transport = httpx.HTTPTransport()
    transport._pool = httpcore.ConnectionPool(network_backend=backend, max_connections=10, keepalive_expiry=5.0)
    return httpx.Client(base_url=base_url, timeout=timeout, transport=transport), backend


class LocalSimpleTextAdapter:
    """Call pinned SimpleAgent.run(text, context=AgentContext), never a tool agent.

    Factories are injectable to run deterministic fake tests without Ollama.
    Context is reconstructed for every request from caller-owned ephemeral
    (role, text) pairs. No MemoryService, bus, prompt_builder or tool catalog
    is ever supplied here.
    """

    def __init__(
        self,
        model: str = "qwen3.5:2b",
        *,
        temperature: float = 0.2,
        max_tokens: int = 256,
        num_ctx: int = 4096,
        timeout_seconds: float = 30.0,
        engine_factory: Callable | None = None,
        agent_factory: Callable | None = None,
        context_factory: Callable | None = None,
        system_prompt: str | None = None,
    ):
        chat_command(model)  # runtime's existing local-model/URL guard
        if not (0.0 <= temperature <= 2.0) or not (1 <= max_tokens <= 1024):
            raise ValueError("Invalid local generation limits")
        if not (256 <= num_ctx <= 4096) or not (0.1 <= timeout_seconds <= 300):
            raise ValueError("Invalid context or timeout limits")
        self.model, self.temperature = model, temperature
        self.max_tokens, self.num_ctx = max_tokens, num_ctx
        self.timeout_seconds = timeout_seconds
        self._engine_factory = engine_factory
        self._agent_factory = agent_factory
        self._context_factory = context_factory
        # OP01: optional host-built persona (rightware.persona). When set it is the ONLY system message; the pinned
        # SimpleAgent then does not fall back to the OpenJarvis config default prompt.
        if system_prompt is not None and (not isinstance(system_prompt, str) or not system_prompt.strip()):
            raise ValueError("Invalid system prompt")
        self.system_prompt = system_prompt
        self._engine = None
        self._agent = None
        self._lock = RLock()

    @staticmethod
    def _pinned_context(history: tuple[tuple[str, str], ...], system_prompt: str | None = None):
        from openjarvis.agents._stubs import AgentContext
        from openjarvis.core.types import Message, Role

        context = AgentContext()
        if system_prompt:
            context.conversation.add(Message(role=Role.SYSTEM, content=system_prompt))
        for role, text in history:
            if role not in ("user", "assistant") or not isinstance(text, str):
                raise ValueError("Invalid ephemeral history")
            context.conversation.add(Message(
                role=Role.USER if role == "user" else Role.ASSISTANT,
                content=text,
            ))
        # No tools/memory_results/metadata supplied.
        return context

    def _ensure_agent(self):
        if self._agent is not None:
            return self._agent
        if self._engine_factory is None:
            from openjarvis.engine.ollama import OllamaEngine

            def factory():
                engine = OllamaEngine(host="http://127.0.0.1:11434", timeout=self.timeout_seconds)
                client, self._abort_backend = abortable_client("http://127.0.0.1:11434", self.timeout_seconds)
                engine._client.close()
                engine._client = client                  # same base URL/timeout; sockets abortable (R-4)
                return engine
            self._engine_factory = factory
        if self._agent_factory is None:
            from openjarvis.agents.simple import SimpleAgent
            self._agent_factory = SimpleAgent
        self._engine = self._engine_factory()
        self._agent = self._agent_factory(
            self._engine, self.model, temperature=self.temperature,
            max_tokens=self.max_tokens, engine_options={"num_ctx": self.num_ctx},
        )
        return self._agent

    def abort(self) -> bool:
        """UI-02 (R-4): stop an in-flight generation. Closing the engine's HTTP client drops the connection, which
        makes Ollama stop generating; the running ``reply`` then fails (its result is already discarded by the
        facade as CANCELLED/TIMEOUT) and releases the lock. The next call builds a fresh engine and agent.
        Deliberately lock-free: the lock is held by the very call being aborted."""
        engine, self._engine, self._agent = self._engine, None, None
        backend, self._abort_backend = getattr(self, "_abort_backend", None), None
        if backend is not None:
            backend.abort_all()                          # interrupts the blocked read of the running request
        if engine is None:
            return False
        close = getattr(engine, "close", None)
        if callable(close):
            try:
                close()
            except Exception:                          # the request in flight may already be failing
                pass
        return True

    def reply(self, text: str, history: tuple[tuple[str, str], ...]) -> str:
        with self._lock:
            agent = self._ensure_agent()
            factory = self._context_factory or (lambda h: self._pinned_context(h, self.system_prompt))
            context = factory(history)
            result = agent.run(text, context=context)
            content = getattr(result, "content", None)
            if (not isinstance(content, str) or not content.strip()
                    or getattr(result, "tool_results", ())
                    or (getattr(result, "metadata", None) or {}).get("error")
                    or (getattr(result, "metadata", None) or {}).get("security_denied")):
                raise InvalidModelReply("No valid tool-free text answer")
            return content.strip()

    def close(self) -> None:
        with self._lock:
            engine = self._engine
            self._engine = self._agent = None
            if engine is not None:
                engine.close()
