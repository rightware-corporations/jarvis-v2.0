"""What may change personal memory (host-side, deterministic). The model PROPOSES a memory tool call; this decides.

* **Intent from the USER's own message only.** A write (save/update) requires an explicit request to remember, learn,
  prefer or correct in the current user message; forgetting requires an explicit forget request. Text from pages,
  documents, tool results or the model's own output can never authorise a change.
* **Grounding:** saved/corrected content must come from the user's message (most of its content words appear there).
  This blocks the model from storing inventions or external content.
* **Sensitive data is refused:** credentials/secrets (OpenJarvis ``SecretScanner`` patterns + local terms), card and
  identity numbers (``PIIScanner`` critical patterns + BI/NUIT/passaporte), and instruction-like text
  (OpenJarvis ``InjectionScanner``).
"""
from __future__ import annotations

import re

from rightware.research.text import content_words, fold

SAVE = re.compile(r"\b(lembra|lembre|lembrar|memoriz|aprend|guard[ae]|regist[ae]|anota|toma nota|nao te esque[cç]as|"
                  r"prefiro|preferencia|gosto (que|de)|quero que (sempre|passes)|a partir de agora|de agora em diante|"
                  r"sempre que|remember|learn)\w*", re.I)
CORRECT = re.compile(r"\b(corrig\w*|actualiz\w*|atualiz\w*|altera\w*|muda\w*|na verdade|afinal|enganei|"
                     r"ja nao (prefiro|e|sou|gosto))\b", re.I)
FORGET = re.compile(r"\b(esquece\w*|esqueca\w*|apag\w*|elimin\w*|remov\w*|deixa de (te )?lembrar|"
                    r"nao te lembres|forget|delete)\b", re.I)
SENSITIVE_TERMS = re.compile(r"\b(password|palavra[- ]passe|senha|pin|cvv|token|chave (de )?api|api key|segredo|"
                             r"codigo (de acesso|secreto|de verificacao)|credencia\w*|nuit|bilhete de identidade|"
                             r"\bbi\b|passaporte|iban|numero de conta|cartao de credito|cartao bancario)\b", re.I)
LONG_DIGITS = re.compile(r"(?:\d[ -]?){9,}")


def intents(user_text: str) -> set[str]:
    t = fold(user_text or "")
    out = set()
    if SAVE.search(t):
        out.add("save")
    if CORRECT.search(t):
        out |= {"save", "update"}
    if FORGET.search(t):
        out.add("forget")
    return out


def _upstream_patterns():
    try:
        from openjarvis.security.scanner import PIIScanner, SecretScanner
        pats = [p for p, _, _ in SecretScanner.PATTERNS.values()]
        pats += [p for name, (p, level, _) in PIIScanner.PATTERNS.items()
                 if str(getattr(level, "value", level)).lower() in ("critical", "high")]
        return [re.compile(p) for p in pats]
    except Exception:                     # fail closed on the local rules below
        return []


_UPSTREAM = _upstream_patterns()


def sensitive_reason(content: str) -> str | None:
    folded = fold(content)
    if SENSITIVE_TERMS.search(folded):
        return "parece conter credenciais, segredos ou números de identificação"
    if LONG_DIGITS.search(content):
        return "contém uma sequência longa de dígitos (conta, cartão ou identificação)"
    if any(p.search(content) for p in _UPSTREAM):
        return "corresponde a um padrão de segredo ou dado pessoal crítico"
    from rightware.research.toolkit import INJECTION        # PT/EN instruction-like text (R02, tested)
    if INJECTION.search(content) or re.search(r"\b(apaga|elimina|esquece) (tudo|todas|a memoria)\b", folded):
        return "parece uma instrução para o assistente, não uma informação pessoal"
    try:
        from openjarvis.security.injection_scanner import InjectionScanner
        if not InjectionScanner().scan(content).is_clean:
            return "parece uma instrução para o assistente, não uma informação pessoal"
    except Exception:
        pass
    return None


META = {"utilizador", "usuario", "user", "pessoa", "cliente", "senhor", "senhora", "issa", "jarvis", "sempre",
        "preferencia", "memoria", "informacao", "guardar", "lembrar"}


def grounded(content: str, user_text: str, min_ratio: float = 0.5) -> bool:
    """Most content words of the memory (ignoring meta words such as "utilizador") must appear in the user's own
    message (prefix match tolerant to verb/plural endings)."""
    words = [w for w in content_words(content) if w not in META]
    if not words:
        return False
    toks = [t for t in re.findall(r"[a-z0-9]+", fold(user_text)) if len(t) >= 3]

    def hit(w):
        k = w[:max(3, min(5, len(w) - 3))]          # tolerate verb/plural endings: prefere/prefiro, vive/vivo
        return any(t.startswith(k) for t in toks)
    return sum(1 for w in words if hit(w)) / len(words) >= min_ratio


COMMAND = re.compile(r"(?i)^\s*(jarvis|ola jarvis|olá jarvis)\s*[,:!.-]*\s*|"
                     r"\b(por favor\s+)?(lembra-te (disto|disso|que|de que)|lembra(-te)?|memoriza( isto| isso| que)?|"
                     r"aprende (esta|esta informação|isto|que)|toma nota( disto| que)?|guarda (isto|isso|que)|"
                     r"regista (isto|que)|anota (isto|que)|não te esqueças (disto|que|de que)|"
                     r"corrige (a informação|isso|o que)( que)?( guardaste| registaste)?( anteriormente)?|"
                     r"(a )?informação( que guardaste)?( anteriormente)?)\s*[:,.-]*\s*")


def user_statement(user_text: str, max_chars: int = 400) -> str:
    """The user's own words with the memory command removed ("JARVIS, lembra-te disto: X" → "X"). Used when the
    model's paraphrase is not grounded: the host then stores what the USER said, never the model's version."""
    t = " ".join((user_text or "").split())
    t = COMMAND.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" .,:;-")
    return (t[:1].upper() + t[1:])[:max_chars] if t else ""
