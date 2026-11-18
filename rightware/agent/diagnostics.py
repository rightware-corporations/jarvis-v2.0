"""TE-05: finite, content-free diagnostics for agent runs (observation only).

Two things live here:
* reason codes: a FIXED vocabulary classifying why a tool proposal was denied by the policy, or
  why a browser step was refused. The classifier reads only code-generated reason strings (policy
  reasons, ``WebRefused`` messages); it never reads tool arguments, page text or model output, and
  anything it does not recognise becomes ``OTHER``;
* generation metrics: numbers per model generation (tokens and engine timings as the engine reports
  them, wall time, tool-call count). No prompts, messages, arguments or content.

Nothing here changes a decision, a quota, a budget or a reply. Codes are diagnostics, not authority.
"""
from __future__ import annotations

import dataclasses

# -- policy denials (AgentPolicy reasons + the pre-policy reasons of _RightwareOrchestrator) --------
POLICY_CODES = frozenset((
    "CANCELLED", "DEADLINE", "TOOL_BUDGET", "TOOL_QUOTA", "REPEATED_ACTION", "REPETITIVE_CYCLE",
    "ACTION_UNIDENTIFIED", "UNKNOWN_TOOL", "INVALID_ARGUMENTS", "CAPABILITY_NOT_AUTHORIZED",
    "BATCH_FAIL_CLOSED", "AUDIT_UNAVAILABLE", "NOT_APPROVED_AT_BOUNDARY", "MALFORMED_ARGUMENTS",
    "PRE_POLICY_UNSPECIFIED", "OTHER",
))
_POLICY_EXACT = {
    "tarefa cancelada": "CANCELLED",
    "tempo esgotado": "DEADLINE",
    "limite de passos atingido": "TOOL_BUDGET",
    "limite de chamadas desta ferramenta atingido": "TOOL_QUOTA",
    "ferramenta fora do registo": "UNKNOWN_TOOL",
    "argumentos não são um objecto": "INVALID_ARGUMENTS",
    "argumentos em falta ou não previstos": "INVALID_ARGUMENTS",
    "lote fail-closed": "BATCH_FAIL_CLOSED",
    "auditoria indisponível: negado": "AUDIT_UNAVAILABLE",
    "não foi possível identificar a acção (fail-closed)": "ACTION_UNIDENTIFIED",
    "chamada não aprovada ou argumentos alterados após aprovação": "NOT_APPROVED_AT_BOUNDARY",
    "os argumentos não são JSON válido (recusada antes da política)": "MALFORMED_ARGUMENTS",
    "os argumentos não são um objecto JSON (recusada antes da política)": "MALFORMED_ARGUMENTS",
    "recusada antes da política (motivo exacto não disponível)": "PRE_POLICY_UNSPECIFIED",
}
_POLICY_PREFIX = (
    ("acção idêntica já pedida", "REPEATED_ACTION"),
    ("ciclo repetitivo", "REPETITIVE_CYCLE"),
    ("tipo inválido em", "INVALID_ARGUMENTS"),
    ("valor não permitido em", "INVALID_ARGUMENTS"),
    ("capacidade '", "CAPABILITY_NOT_AUTHORIZED"),
)


def policy_reason_code(reason: object) -> str | None:
    """Finite code for a policy reason string (None for no reason)."""
    if reason is None:
        return None
    if not isinstance(reason, str):
        return "OTHER"
    text = reason[len("fronteira: "):] if reason.startswith("fronteira: ") else reason
    if text in _POLICY_EXACT:
        return _POLICY_EXACT[text]
    for prefix, code in _POLICY_PREFIX:
        if text.startswith(prefix):
            return code
    if text.startswith("'") and text.endswith("' demasiado longo"):
        return "INVALID_ARGUMENTS"
    return "OTHER"


# -- browser refusals (PublicBrowser steps and WebRefused messages) -------------------------------
BROWSER_CODES = frozenset((
    "UNKNOWN_LINK", "UNKNOWN_FIELD", "INVALID_QUERY", "FORM_NOT_ALLOWED", "NOTHING_TYPED", "URL_TOO_LONG",
    "INVALID_FIND_TEXT", "HOST_NOT_ALLOWED", "CONTENT_TYPE_UNSUPPORTED", "NON_PUBLIC_ADDRESS",
    "INVALID_URL", "DNS_UNRESOLVED", "TOO_MANY_REDIRECTS", "FETCH_FAILED", "TOOL_EXCEPTION", "WEB_REFUSED_OTHER",
))
_WEB_EXACT = {
    "servidor fora dos sites autorizados nesta tarefa": "HOST_NOT_ALLOWED",
    "não foi possível resolver o servidor": "DNS_UNRESOLVED",
    "demasiados redireccionamentos": "TOO_MANY_REDIRECTS",
    "endereço local não permitido": "NON_PUBLIC_ADDRESS",
    "bloqueado pela protecção SSRF": "NON_PUBLIC_ADDRESS",
    "o servidor resolve para um endereço privado ou reservado": "NON_PUBLIC_ADDRESS",
    "sockets locais não são permitidos": "NON_PUBLIC_ADDRESS",
    "a ligação não foi a um endereço público": "NON_PUBLIC_ADDRESS",
    "URL inválido": "INVALID_URL",
    "URL com caracteres não permitidos": "INVALID_URL",
    "URL malformado": "INVALID_URL",
    "só são permitidos endereços http ou https": "INVALID_URL",
    "credenciais no URL não são permitidas": "INVALID_URL",
    "porta inválida": "INVALID_URL",
    "só são permitidas as portas 80 e 443": "INVALID_URL",
    "URL sem servidor": "INVALID_URL",
}


def web_refusal_code(message: object) -> str:
    """Finite code for a ``WebRefused`` message (code-generated text; never page content)."""
    if isinstance(message, str):
        if message in _WEB_EXACT:
            return _WEB_EXACT[message]
        if message.startswith("tipo de conteúdo não suportado"):
            return "CONTENT_TYPE_UNSUPPORTED"
    return "WEB_REFUSED_OTHER"


REASON_CODES = POLICY_CODES | BROWSER_CODES


# -- execution errors (TE-05E) --------------------------------------------------------------------
# Why a contracted run ended in ERROR. Classified ONLY from exception TYPES (including the
# ``raise ... from`` cause chain) and internal states; never from exception messages or model text.
ERROR_CODES = frozenset((
    "NONE",               # no execution error
    "ENGINE_TIMEOUT",     # the engine client gave up waiting (e.g. httpx timeout); the server may continue
    "ENGINE_CONNECTION",  # the local engine could not be reached
    "ENGINE_FAILURE",     # the engine raised anything else (HTTP error status, malformed response, ...)
    "AGENT_FAILURE",      # an exception outside the engine call (orchestrator / integration)
    "AUDIT_FAILURE",      # the mandatory audit could not be persisted
    "EVIDENCE_INCOMPLETE",  # the run ended but its completion evidence was missing or malformed
    "OTHER",
))


def _cause_chain(exc: BaseException, limit: int = 6):
    seen = []
    while exc is not None and len(seen) < limit and all(exc is not e for e in seen):
        seen.append(exc)
        exc = exc.__cause__ or exc.__context__
    return seen


def engine_error_code(exc: BaseException) -> str:
    """Finite category for an exception raised by ``engine.generate`` (types only)."""
    try:
        import httpx
        timeout_types, connect_types = (httpx.TimeoutException,), (httpx.ConnectError,)
    except ImportError:                                   # pragma: no cover - httpx is a runtime dependency
        timeout_types, connect_types = (), ()
    try:
        from openjarvis.engine._base import EngineConnectionError
    except ImportError:                                   # plain Python without the pinned vendor
        EngineConnectionError = ()
    chain = _cause_chain(exc)
    if any(isinstance(e, timeout_types + (TimeoutError,)) for e in chain):
        return "ENGINE_TIMEOUT"
    if any(isinstance(e, connect_types + (ConnectionError,)) for e in chain):
        return "ENGINE_CONNECTION"
    if EngineConnectionError and any(isinstance(e, EngineConnectionError) for e in chain):
        return "ENGINE_CONNECTION"
    return "ENGINE_FAILURE"


# -- generation metrics ----------------------------------------------------------------------------
GENERATION_KINDS = ("model", "continuation", "halt_short_circuit")


def _count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _seconds(ns: object) -> float | None:
    return round(ns / 1e9, 3) if type(ns) is int and ns >= 0 else None


@dataclasses.dataclass(frozen=True)
class GenerationMetric:
    """One model generation, numbers only. ``None`` = the engine did not report it.

    Engine timings come from Ollama's own counters (``load_duration`` = model load, cold or warm;
    ``prompt_eval_duration`` = prompt processing; ``eval_duration`` = token generation). They are the
    server's view; ``wall_seconds`` is the client's view of the same call, including HTTP and queueing.
    ``deadline_overrun_seconds`` > 0 means the task deadline had already passed when this generation
    returned: the deadline is checked only BETWEEN steps, so work in flight can exceed it."""
    index: int
    kind: str
    wall_seconds: float
    tool_calls: int
    prompt_tokens: int | None = None
    prompt_tokens_evaluated: int | None = None
    completion_tokens: int | None = None
    load_seconds: float | None = None
    prompt_eval_seconds: float | None = None
    eval_seconds: float | None = None
    total_seconds: float | None = None
    deadline_overrun_seconds: float = 0.0
    engine_error: str | None = None     # TE-05E: finite code when the engine raised (no metrics returned)


def generation_metric(index: int, kind: str, result: object, wall_seconds: float,
                      overrun_seconds: float = 0.0, engine_error: str | None = None) -> GenerationMetric:
    if kind not in GENERATION_KINDS:
        raise ValueError("tipo de geração desconhecido")
    if engine_error is not None and engine_error not in ERROR_CODES:
        raise ValueError("código de erro desconhecido")
    data = result if isinstance(result, dict) else {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    timing = data.get("engine_timing") if isinstance(data.get("engine_timing"), dict) else {}
    calls = data.get("tool_calls")
    return GenerationMetric(
        index=index, kind=kind, wall_seconds=round(max(0.0, float(wall_seconds)), 3),
        tool_calls=len(calls) if isinstance(calls, list) else 0,
        prompt_tokens=_count(usage.get("prompt_tokens")),
        prompt_tokens_evaluated=_count(usage.get("prompt_tokens_evaluated")),
        completion_tokens=_count(usage.get("completion_tokens")),
        load_seconds=_seconds(timing.get("load_duration")),
        prompt_eval_seconds=_seconds(timing.get("prompt_eval_duration")),
        eval_seconds=_seconds(timing.get("eval_duration")),
        total_seconds=_seconds(timing.get("total_duration")),
        deadline_overrun_seconds=round(max(0.0, float(overrun_seconds)), 3),
        engine_error=engine_error,
    )


def summarize(metrics) -> dict:
    """Totals over a run's generations (numbers only; unknown values are left out of the sums)."""
    def total(field):
        values = [getattr(m, field) for m in metrics if getattr(m, field) is not None]
        return round(sum(values), 3) if values else None
    model = [m for m in metrics if m.kind != "halt_short_circuit"]
    return {
        "generations": len(model),
        "halt_short_circuits": len(metrics) - len(model),
        "continuations": sum(1 for m in metrics if m.kind == "continuation"),
        "tool_calls_proposed": sum(m.tool_calls for m in metrics),
        "prompt_tokens": total("prompt_tokens"),
        "completion_tokens": total("completion_tokens"),
        "wall_seconds": total("wall_seconds"),
        "load_seconds": total("load_seconds"),
        "prompt_eval_seconds": total("prompt_eval_seconds"),
        "eval_seconds": total("eval_seconds"),
        "max_deadline_overrun_seconds": max((m.deadline_overrun_seconds for m in metrics), default=0.0),
        "engine_errors": sum(1 for m in metrics if m.engine_error is not None),
    }

