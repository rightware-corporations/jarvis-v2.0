"""WORK-04 R2: detect affirmative completion claims in the final answer.

Phrase/negation aware for the synthetic PT-MZ task. This is NOT a general
natural-language entailment evaluator; completion still depends exclusively on
the tool-verified artifact. The detector is a guardrail for false-success
telemetry, never grounds truth or makes a task PASS.
"""
from __future__ import annotations
import re
import unicodedata


def fold(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text or "").lower()
        if not unicodedata.combining(ch)
    )


_CLAUSE = re.compile(r"\b(?:mas|porem|contudo|entretanto|no entanto|however|but)\b|[;\n]")
_POS = re.compile(
    r"\b(?:pass|passed|passou|aprovad\w*|verificad\w*|validad\w*|"
    r"criad\w*|guardad\w*|gravado\w*|salv\w*|conclui\w*|"
    r"concluid\w*|terminad\w*|pronto|feito|sucesso|"
    r"completed|done)\b|sem problemas|sem erros?|sem falhas|nenhum erro|"
    r"nao houve (?:erro|problema|falha)"
)
_NEG = re.compile(
    r"\b(?:fail(?:ed)?|falh\w*|erro(?:s)?|problema(?:s)?|"
    r"incomplet\w*|pendente|nao consegu\w*|nao passou|"
    r"nao (?:foi|esta|ficou|consegui|houve|ha)\b|"
    r"ainda nao|nao foi possivel|nao pode)\b"
)
# Negated error terms are positive evidence, not failures.
_NO_PROBLEM = re.compile(
    r"sem problemas|sem erros?|sem falhas|nenhum erro|"
    r"nao houve (?:erro(?:s)?|problema(?:s)?|falha(?:s)?)"
)
# A standalone assertion of "report" alone is never success.
_MINIMAL_POS = re.compile(
    r"\b(?:pass|passed|passou|aprovad\w*|verificad\w*|validad\w*|"
    r"criad\w*|guardad\w*|gravado\w*|salv\w*|"
    r"conclui\w*|concluid\w*|terminad\w*|"
    r"pronto|feito|sucesso|completed|done)\b"
)


def claims_success(answer: str) -> bool:
    """Final non-neutral clause wins; a failure in that clause wins ties.

    A successful tool trace is evaluated independently. The purpose here is
    to flag misleading verbal claims when no trustworthy artifact exists.
    """
    normalized = fold(answer)
    decision: bool | None = None
    for raw in _CLAUSE.split(normalized):
        clause = raw.strip()
        if not clause:
            continue
        cleaned = _NO_PROBLEM.sub("", clause)
        negative = bool(_NEG.search(cleaned))
        positive = bool(_POS.search(clause) or _MINIMAL_POS.search(clause))
        if negative:
            decision = False
        elif positive:
            decision = True
    return decision is True
