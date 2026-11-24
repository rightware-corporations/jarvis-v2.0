"""WEB-01 W3.1: intent routing and the research planner.

Intent routing (host decides; the model may only PROPOSE):
* ``RESEARCH_EXPLICIT`` — the operator wrote ``/pesquisar <pergunta>`` (command, host rule);
* ``OUT_OF_SCOPE`` — host rules for things JARVIS cannot do (financial operations, quotes, local actions, messages,
  credentials); answered with the real capability status, nothing executed;
* ``RESEARCH_SUGGESTED`` — a question the local model PROPOSES needs external facts, and only if the host enabled a
  research capability; it yields a PLAN and an authorisation request, never a network call;
* ``CHAT`` — everything else (the existing tool-free conversation).

Planner: the local model returns ONE JSON object; the host validates it strictly (exact keys, types, lengths, no URLs,
no search operators) and keeps the ORIGINAL question from the host, not from the model. The plan cannot carry
domains, budgets, policy or verdicts — unknown keys are a validation failure. One retry; then a deterministic host
fallback plan (labelled as such)."""
from __future__ import annotations

import dataclasses
import json
import re
import unicodedata

CHAT, RESEARCH_SUGGESTED, RESEARCH_EXPLICIT, OUT_OF_SCOPE = "CHAT", "RESEARCH_SUGGESTED", "RESEARCH_EXPLICIT", "OUT_OF_SCOPE"
MAX_QUESTION = 300
OUT_OF_SCOPE_RULES = (
    (r"\b(compr[ae]r?|vend[ae]r?|investir|transferi[rd]|pagar|ordem de (compra|venda)|aplicar dinheiro)\b",
     "Operações financeiras não são executadas pelo JARVIS."),
    (r"\b(cota[çc][ãa]o|cota[çc][õo]es|pre[çc]o d[ae]s? a[çc][ãa]o|bolsa de valores|taxa de c[âa]mbio hoje)\b",
     "Cotações e dados de mercado não estão integrados (WEB-01 W4 não iniciado)."),
    (r"\b(apag[ae]r?|elimin[ae]r?|execut[ae]r?|instal[ae]r?|abr[ei]r? o programa|correr o comando)\b.{0,40}"
     r"\b(ficheiro|arquivo|comando|programa|aplica[çc][ãa]o|pasta)\b",
     "Acções no computador estão BLOQUEADAS (exigem companion autorizado)."),
    (r"\b(envi[ae]r?|mand[ae]r?)\b.{0,30}\b(e-?mail|mensagem|sms|whatsapp)\b", "Envio de mensagens não está integrado."),
    (r"\b(palavra-passe|password|senha|credencia(l|is)|token)\b", "O JARVIS não pede nem usa credenciais."),
)
INTERROGATIVE = re.compile(r"^\s*(qual|quais|quem|quando|onde|quanto|quantos|quantas|como|porque|por que|o que|"
                           r"what|who|when|where|which|how many|how much)\b", re.I)


@dataclasses.dataclass(frozen=True)
class Intent:
    kind: str
    question: str
    reason: str
    decided_by: str            # "host" | "host (proposta do modelo)"


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def route(text: str, *, research_enabled: bool, propose=None) -> Intent:
    """``propose(text) -> 'chat'|'research'|None`` is the model's proposal (optional, validated here)."""
    t = " ".join((text or "").split())
    if t.lower().startswith("/pesquisar"):
        q = t[len("/pesquisar"):].strip()
        if not research_enabled:
            return Intent(OUT_OF_SCOPE, q, "A pesquisa livre não foi activada pelo anfitrião.", "host")
        if not 3 <= len(q) <= MAX_QUESTION:
            return Intent(OUT_OF_SCOPE, q, f"Pergunta vazia ou longa demais (máx. {MAX_QUESTION}).", "host")
        return Intent(RESEARCH_EXPLICIT, q, "Pedido explícito do operador.", "host")
    for rx, why in OUT_OF_SCOPE_RULES:
        if re.search(rx, t, re.I):
            return Intent(OUT_OF_SCOPE, t, why, "host")
    if research_enabled and propose is not None and (t.endswith("?") or INTERROGATIVE.match(t)) \
            and len(t) <= MAX_QUESTION:
        try:
            proposal = propose(t)
        except Exception:                       # the model failing never blocks the chat
            proposal = None
        if proposal == "research":
            return Intent(RESEARCH_SUGGESTED, t, "O modelo propôs pesquisa externa; o anfitrião exige plano e código.",
                          "host (proposta do modelo)")
    return Intent(CHAT, t, "Conversa normal.", "host")


INTENT_SYSTEM = ("Classifica a mensagem do utilizador. Responde só com JSON {\"intent\": \"chat\" ou \"research\"}. "
                 "Usa \"research\" para QUALQUER pergunta factual sobre o mundo real (pessoas, países, lugares, datas, "
                 "organizações, moedas, números, acontecimentos), mesmo que penses saber a resposta, porque o JARVIS "
                 "tem de responder com fontes. Usa \"chat\" para cumprimentos, conversa, opiniões, escrita criativa, "
                 "tradução, cálculo ou perguntas sobre o próprio JARVIS. Exemplos: \"Qual é a capital de Angola?\" -> "
                 "research; \"Quem escreveu Os Lusíadas?\" -> research; \"Bom dia!\" -> chat; \"Escreve um "
                 "haiku\" -> chat; \"Quanto é 12*7?\" -> chat.")


def model_proposer(call):
    def propose(text: str):
        raw, _ = call(INTENT_SYSTEM, text)
        try:
            v = json.loads(raw).get("intent")
        except (ValueError, AttributeError):
            return None
        return v if v in ("chat", "research") else None
    return propose


# ------------------------------------------------------------------------------------------------------ planner
PLAN_KEYS = {"objective": str, "subquestions": list, "queries": list, "relevance_criteria": list, "missing_info": list}
LIMITS = {"objective": 300, "subquestions": (3, 200), "queries": (4, 100), "relevance_criteria": (4, 160),
          "missing_info": (4, 160)}
FORBIDDEN_IN_QUERY = re.compile(r"(https?://|www\.|\bsite:|\binurl:|\bintitle:|\bfiletype:|[<>{}\[\]\\|`])", re.I)

PLAN_SYSTEM = (
    "És o planeador de pesquisa do JARVIS. Recebes uma pergunta e devolves UM objecto JSON com exactamente estas "
    "chaves: objective (texto curto), subquestions (lista, 0 a 3 textos), queries (lista, 1 a 4 consultas curtas de "
    "pesquisa em português, sem URLs nem operadores), relevance_criteria (lista, 1 a 4 critérios), missing_info "
    "(lista, 0 a 4 itens que a pergunta não define). Não respondas à pergunta. Não incluas domínios, sites, "
    "orçamentos nem conclusões.")


@dataclasses.dataclass(frozen=True)
class Plan:
    question: str
    objective: str
    subquestions: tuple[str, ...]
    queries: tuple[str, ...]
    relevance_criteria: tuple[str, ...]
    missing_info: tuple[str, ...]
    source: str                 # "modelo:<nome>" | "anfitrião (fallback)"

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


class PlanError(ValueError):
    pass


def _strings(v, n_max: int, l_max: int, key: str, n_min: int = 0) -> tuple[str, ...]:
    if not isinstance(v, list) or not n_min <= len(v) <= n_max or not all(isinstance(x, str) for x in v):
        raise PlanError(f"{key}: lista de {n_min}..{n_max} textos")
    out = []
    for x in v:
        x = " ".join(x.split())
        if not x or len(x) > l_max:
            raise PlanError(f"{key}: item vazio ou longo demais")
        if x not in out:
            out.append(x)
    return tuple(out)


def validate_plan(raw: str, question: str, source: str) -> Plan:
    try:
        d = json.loads(raw)
    except ValueError:
        raise PlanError("não é JSON") from None
    if not isinstance(d, dict) or set(d) != set(PLAN_KEYS):
        raise PlanError(f"chaves inválidas: {sorted(d) if isinstance(d, dict) else type(d).__name__}")
    objective = d["objective"]
    if not isinstance(objective, str) or not 3 <= len(objective.strip()) <= LIMITS["objective"]:
        raise PlanError("objective inválido")
    queries = _strings(d["queries"], *LIMITS["queries"], "queries", n_min=1)
    for q in queries:
        if FORBIDDEN_IN_QUERY.search(q) or len(q) < 3:
            raise PlanError(f"consulta proibida: {q[:40]!r}")
    return Plan(question, " ".join(objective.split()), _strings(d["subquestions"], *LIMITS["subquestions"], "subquestions"),
                queries, _strings(d["relevance_criteria"], *LIMITS["relevance_criteria"], "relevance_criteria", n_min=1),
                _strings(d["missing_info"], *LIMITS["missing_info"], "missing_info"), source)


STOP = set(_fold("a o os as um uma de do da dos das em no na nos nas por para com sem que qual quais quem quando onde "
                 "como e é foi são ser ao à aos às se sua seu suas seus isto isso the of in on for and is are was "
                 "what who when where which how qual é diz-me diga me explica quanto quantos quantas").split())


def content_terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]{3,}", _fold(text)) if w not in STOP]


def fallback_plan(question: str) -> Plan:
    terms = content_terms(question)
    q = " ".join(dict.fromkeys(terms))[:100] or question[:100]
    return Plan(question, "Responder à pergunta com fontes da allowlist.", (), (q,), ("A fonte trata o tema da pergunta",),
                (), "anfitrião (fallback)")


def make_plan(question: str, call, model_name: str, retries: int = 1) -> tuple[Plan, dict]:
    """(plan, meta). meta: attempts, errors, seconds, valid_model_plan."""
    meta = {"attempts": 0, "errors": [], "seconds": 0.0, "valid_model_plan": False, "model": model_name}
    for _ in range(1 + retries):
        meta["attempts"] += 1
        try:
            raw, secs = call(PLAN_SYSTEM, f"Pergunta: {question}")
            meta["seconds"] += secs
            plan = validate_plan(raw, question, f"modelo:{model_name}")
            meta["valid_model_plan"] = True
            return plan, meta
        except Exception as exc:                 # invalid JSON/schema or model failure → retry, then fallback
            meta["errors"].append(f"{type(exc).__name__}: {str(exc)[:120]}")
    return fallback_plan(question), meta
