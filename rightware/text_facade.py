"""WP-04/D01: trusted, ephemeral, text-only request/result boundary.

Opt-in API; intentionally disconnected from AgentSession, OS actions, web,
durable memory, legacy CLI and A1/A2/A3 completion semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import secrets
from threading import Event, RLock, Thread
import time
from typing import Protocol

from rightware.text_adapter import InvalidModelReply, LocalSimpleTextAdapter


class Route(str, Enum):
    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    PLAN = "PLAN"
    TASK = "TASK"
    CONTROL = "CONTROL"
    MEMORY_INTENT = "MEMORY_INTENT"


class Status(str, Enum):
    ANSWER_ONLY = "ANSWER_ONLY"
    PLAN_ONLY = "PLAN_ONLY"
    WAITING_INPUT = "WAITING_INPUT"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class TextRequest:
    """Created solely inside TextFacade from host-controlled session state."""

    request_id: str
    session_id: str
    owner_id: str
    channel: str
    text: str
    context_limit_chars: int
    deadline_seconds: float
    effective_capabilities: tuple = ()


@dataclass(frozen=True)
class TextResult:
    request_id: str
    session_id: str
    owner_id: str
    text: str
    route: Route
    status: Status
    limitations: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()
    factual_verified: bool = False
    execution_receipts: tuple = ()
    effects: tuple = ()
    task_completed: bool = False
    memory_persisted: bool = False

    def __post_init__(self):
        if (self.factual_verified or self.execution_receipts or self.effects
                or self.task_completed or self.memory_persisted):
            raise ValueError("No-tool result cannot assert verified effects or persistence")


class TextModel(Protocol):
    def reply(self, text: str, history: tuple[tuple[str, str], ...]) -> str: ...


@dataclass
class _Session:
    owner_id: str
    history: list[tuple[str, str]] = field(default_factory=list)
    lock: RLock = field(default_factory=RLock)
    cancelled: Event = field(default_factory=Event)
    worker: Thread | None = None


_LIMITS = ("SEM_FERRAMENTAS", "SEM_MEMORIA_PERSISTENTE", "FACTOS_NAO_VERIFICADOS")
_TASK = re.compile(
    r"^\s*(?:(?:por favor|please)[,:]?\s+)?"
    r"(?:abre|abrir|executa|executar|envia|enviar|apaga|apagar|elimina|"
    r"cria\s+(?!um\s+plano)|criar\s+(?!um\s+plano)|lê\s+(?:este|o)\s+ficheiro|"
    r"marca\s+(?:um|uma|para)|agenda|agendar|instala|instalar|corre\s+o\s+comando)\b",
    re.IGNORECASE,
)
_COMPOUND_TASK = re.compile(
    r"\b(?:e\s+depois|depois)\s+(?:abre|envia|apaga|executa|instala)\b",
    re.IGNORECASE,
)
_MEMORY = re.compile(
    r"^\s*(?:lembra-te\s+de|memoriza\b|guarda\s+(?:na\s+mem[oó]ria|isto\s+para)|"
    r"apaga\s+(?:a\s+)?prefer[eê]ncia\b|esquece\s+(?:o\s+que|a\s+prefer[eê]ncia))",
    re.IGNORECASE,
)
_CLARIFY = re.compile(
    r"^\s*(?:faz\s+isso|e\s+isso|quando\s+foi|preciso\s+de\s+um\s+banco|"
    r"marca\s+para\s+sexta-feira)\s*[?!.]?\s*$", re.IGNORECASE
)
_CONTROL = re.compile(
    r"^\s*(?:p[aá]ra\b|cancela\b|n[aã]o\s+executes\b|"
    r"j[aá]\s+executaste\b|qual\s+[eé]\s+o\s+estado\b)",
    re.IGNORECASE,
)
_PLAN = re.compile(
    r"^\s*(?:organiza\s+o\s+meu\s+dia|planeia\b|"
    r"cria\s+um\s+plano\b|faz\s+um\s+plano\b|"
    r"explica\s+como\b|como\s+(?:fa[cç]o|posso)\b|passo\s+a\s+passo\b)",
    re.IGNORECASE,
)
_FALSE_EFFECT = re.compile(
    r"^(?:\s|[*#-])*(?:(?:j[aá]|already)\s+)?"
    r"(?:abri|enviei|executei|apaguei|guardei|gravei|agendei|"
    r"criei\s+(?:a\s+)?pasta|conclu[ií]|feito\b|done\b|"
    r"i\s+(?:sent|deleted|opened|saved|executed|completed)\b)",
    re.IGNORECASE,
)


class TextFacade:
    """One owner-bound host facade; sessions and request IDs minted locally.

    The caller may supply only a session token minted by open_session(), plain
    text and the text channel. Neither user/model text nor JSON is parsed into
    authority. The owner is a local placeholder, not an authentication claim.
    """

    def __init__(
        self,
        *,
        owner_id: str = "local",
        adapter: TextModel | None = None,
        max_sessions: int = 16,
        max_input_chars: int = 2048,
        max_history_chars: int = 6000,
        max_turns: int = 6,
        max_response_chars: int = 4096,
        deadline_seconds: float = 30.0,
    ):
        if not isinstance(owner_id, str) or not re.fullmatch(r"[\w.-]{1,64}", owner_id, re.ASCII):
            raise ValueError("Invalid local owner identifier")
        if not (1 <= max_sessions <= 64 and 1 <= max_turns <= 16):
            raise ValueError("Invalid session limits")
        if not (1 <= max_input_chars <= 8192 and 32 <= max_history_chars <= 32768
                and 1 <= max_response_chars <= 8192 and 0.05 <= deadline_seconds <= 300):
            raise ValueError("Invalid context/deadline limits")
        self.owner_id = owner_id
        self.max_sessions, self.max_input_chars = max_sessions, max_input_chars
        self.max_history_chars, self.max_turns = max_history_chars, max_turns
        self.max_response_chars, self.deadline_seconds = max_response_chars, deadline_seconds
        self._adapter = adapter
        self._adapter_init_lock = RLock()
        self._sessions: dict[str, _Session] = {}
        self._lock = RLock()

    def open_session(self) -> str:
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise RuntimeError("Ephemeral session limit reached")
            session_id = secrets.token_hex(16)
            self._sessions[session_id] = _Session(self.owner_id)
            return session_id

    def _session(self, session_id: str) -> _Session:
        if not isinstance(session_id, str):
            raise ValueError("Invalid session")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.owner_id != self.owner_id:
                raise ValueError("Unknown or foreign session")
            return session

    def cancel(self, session_id: str) -> bool:
        session = self._session(session_id)
        if session.worker is not None and session.worker.is_alive():
            session.cancelled.set()
            return True
        return False

    def close_session(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise ValueError("Unknown session")
        session.cancelled.set()
        session.history.clear()

    def history_snapshot(self, session_id: str) -> tuple[tuple[str, str], ...]:
        session = self._session(session_id)
        with session.lock:
            return tuple(session.history)

    @staticmethod
    def _route(text: str) -> Route:
        # This is a conservative no-effect guard, not a semantic intent oracle.
        if _MEMORY.search(text):
            return Route.MEMORY_INTENT
        if _CLARIFY.fullmatch(text):
            return Route.CLARIFY
        if _CONTROL.search(text):
            return Route.CONTROL
        if _COMPOUND_TASK.search(text) or _TASK.search(text):
            return Route.TASK
        if _PLAN.search(text):
            return Route.PLAN
        return Route.ANSWER

    @staticmethod
    def _result(req: TextRequest, route: Route, status: Status, text: str,
                diagnostics: tuple[str, ...] = ()) -> TextResult:
        return TextResult(req.request_id, req.session_id, req.owner_id, text, route,
                          status, _LIMITS, diagnostics)

    def submit(self, session_id: str, text: str, *, channel: str = "text") -> TextResult:
        if channel != "text":
            raise ValueError("Only the text channel is supported")
        if (not isinstance(text, str) or not text.strip()
                or len(text) > self.max_input_chars
                or any(ord(c) < 32 and c not in "\n\t\r" for c in text)):
            raise ValueError("Invalid or over-budget text request")
        session = self._session(session_id)
        with session.lock:
            request = TextRequest(
                request_id=secrets.token_hex(16),
                session_id=session_id, owner_id=session.owner_id,
                channel="text", text=text, context_limit_chars=self.max_history_chars,
                deadline_seconds=self.deadline_seconds,
            )
            if session.worker is not None and session.worker.is_alive():
                return self._result(request, Route.CONTROL, Status.UNAVAILABLE,
                                    "O pedido anterior ainda está a terminar. Não foi iniciada nova inferência.",
                                    ("MODEL_BUSY",))
            session.worker = None
            session.cancelled.clear()
            route = self._route(text)
            if route == Route.MEMORY_INTENT:
                return self._result(request, route, Status.UNAVAILABLE,
                                    "Não existe memória persistente nesta interface. Nenhuma informação foi guardada ou apagada.")
            if route == Route.TASK:
                return self._result(request, route, Status.UNAVAILABLE,
                                    "Esta interface não executa acções nem envia dados. Posso apenas explicar os passos; nada foi executado.")
            if route == Route.CONTROL:
                return self._result(request, route, Status.UNAVAILABLE,
                                    "Não há ferramentas nem tarefas executadas nesta interface. O cancelamento de inferência em curso pertence ao host.")
            if route == Route.CLARIFY:
                return self._result(request, route, Status.WAITING_INPUT,
                                    "Podes esclarecer a que te referes? Não vou assumir detalhes em falta.")

            history = tuple(session.history)
            box: dict = {}
            def work():
                try:
                    with self._adapter_init_lock:
                        if self._adapter is None:
                            self._adapter = LocalSimpleTextAdapter(
                                timeout_seconds=self.deadline_seconds)
                        adapter = self._adapter
                    box["value"] = adapter.reply(request.text, history)
                except BaseException as exc:
                    box["error"] = exc

            worker = Thread(target=work, daemon=True, name="jarvis-wp04-text")
            session.worker = worker
            worker.start()
            end = time.monotonic() + self.deadline_seconds
            while worker.is_alive():
                worker.join(min(0.05, max(0.0, end - time.monotonic())))
                if session.cancelled.is_set():
                    return self._result(request, route, Status.UNAVAILABLE,
                                        "Pedido cancelado. Nenhuma acção foi executada.",
                                        ("CANCELLED",))
                if time.monotonic() >= end and worker.is_alive():
                    return self._result(request, route, Status.ERROR,
                                        "O modelo local excedeu o tempo permitido. Nenhuma acção foi executada.",
                                        ("TIMEOUT",))
            session.worker = None
            if session.cancelled.is_set():
                return self._result(request, route, Status.UNAVAILABLE,
                                    "Pedido cancelado. Nenhuma acção foi executada.",
                                    ("CANCELLED",))
            if "error" in box:
                error = box["error"]
                code = ("INVALID_MODEL_REPLY" if isinstance(error, InvalidModelReply)
                        else "TIMEOUT" if isinstance(error, TimeoutError)
                        else "MODEL_UNAVAILABLE" if isinstance(error, (ConnectionError, OSError))
                        or "Connection" in type(error).__name__
                        else "MODEL_ERROR")
                return self._result(request, route, Status.ERROR,
                                    "Não foi possível obter uma resposta válida do modelo local. Confirma o Ollama e o modelo instalado.",
                                    (code,))
            answer = box.get("value")
            if not isinstance(answer, str) or not answer.strip():
                return self._result(request, route, Status.ERROR,
                                    "O modelo devolveu uma resposta inválida.", ("INVALID_MODEL_REPLY",))
            if len(answer) > self.max_response_chars:
                return self._result(request, route, Status.ERROR,
                                    "A resposta ultrapassou o limite do contexto.", ("RESPONSE_LIMIT",))
            if _FALSE_EFFECT.search(answer) or re.search(
                    r"\\b(?:j[aá]\\s+|sim[, ]+|claro[, ]+)(?:enviei|abri|executei|apaguei|guardei|gravei|agendei)\\b",
                    answer, re.IGNORECASE):
                return self._result(request, route, Status.UNAVAILABLE,
                                    "O modelo afirmou uma execução que esta interface não pode comprovar. Nenhuma ferramenta foi chamada.",
                                    ("UNVERIFIED_EFFECT_CLAIM",))
            session.history.extend((("user", request.text), ("assistant", answer)))
            while (len(session.history) > 2 * self.max_turns
                   or sum(len(t) for _, t in session.history) > self.max_history_chars):
                del session.history[:2]
            return self._result(request, route,
                                Status.PLAN_ONLY if route == Route.PLAN else Status.ANSWER_ONLY,
                                answer)

    def close(self) -> None:
        with self._lock:
            sessions = list(self._sessions.items())
        active = any(s.worker is not None and s.worker.is_alive() for _, s in sessions)
        for token, _ in sessions:
            self.close_session(token)
        # Never wait forever for a cancelled/timed-out inference thread.
        if self._adapter is not None and not active:
            close = getattr(self._adapter, "close", None)
            if callable(close):
                close()
