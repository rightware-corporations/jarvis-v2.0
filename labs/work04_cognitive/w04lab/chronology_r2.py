"""WORK-04 R2: deterministic chronology check of the agent's OWN report.

Date order is computed by code, never left to the model. For each sentence
that names two dates with an explicit order relation BETWEEN them ("A ...
antes de ... B", "A é anterior a B", "A ... depois de ... B", "A posterior
a B"), the claimed order is compared with the real calendar order.

It reads only the report text the agent wrote. It never consults the hidden
scenario truth, so echoing those dates back cannot leak anything the agent
did not already write. A negated relation ("não é anterior") is skipped, not
guessed. Product use: the same function can check any generated text.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

MONTHS = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro"]
_DATE = re.compile(
    r"\b(\d{1,2})\s+de\s+(" + "|".join(MONTHS) + r")\s+(?:de\s+)?(\d{4})\b"
    r"|\b(\d{4})-(\d{2})-(\d{2})\b"
    r"|\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_BEFORE = re.compile(r"\b(?:antes\s+d[aeo]s?|anterior(?:es)?\s+[aà]o?s?|precede[ms]?)\b")
_AFTER = re.compile(r"\b(?:depois\s+d[aeo]s?|ap[o]s|posterior(?:es)?\s+[aà]o?s?)\b")
_NEGATION = re.compile(r"\b(?:nao|nunca|nem)\b")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _to_date(m: re.Match) -> dt.date | None:
    g = m.groups()
    try:
        if g[0]:
            return dt.date(int(g[2]), MONTHS.index(g[1]) + 1, int(g[0]))
        if g[3]:
            return dt.date(int(g[3]), int(g[4]), int(g[5]))
        return dt.date(int(g[8]), int(g[7]), int(g[6]))
    except ValueError:
        return None


def _display(folded_date: str) -> str:
    return folded_date.replace(" marco ", " março ")


def reversed_order_claims(text: str) -> list[dict]:
    """Sentences whose explicit before/after claim contradicts calendar order."""
    out = []
    for sentence in re.split(r"(?<=[.;!?])\s+|\n+", _fold(text)):
        found = [(m, _to_date(m)) for m in _DATE.finditer(sentence)]
        found = [(m, d) for m, d in found if d]
        if len(found) < 2:
            continue
        (m1, d1), (m2, d2) = found[0], found[1]
        between = sentence[m1.end():m2.start()]
        before, after = _BEFORE.search(between), _AFTER.search(between)
        if bool(before) == bool(after):
            continue                              # no relation, or ambiguous
        rel = before or after
        if _NEGATION.search(between[:rel.start()][-20:]):
            continue                              # negated relation: do not guess
        claim = "antes" if before else "depois"
        wrong = (claim == "antes" and d1 >= d2) or (claim == "depois" and d1 <= d2)
        if wrong:
            out.append({"first": d1.isoformat(), "second": d2.isoformat(), "claim": claim,
                        "first_text": _display(m1.group(0)), "second_text": _display(m2.group(0))})
    return out


def feedback(text: str) -> str:
    claims = reversed_order_claims(text)
    if not claims:
        return ""
    parts = []
    for c in claims[:3]:
        real = "posterior" if c["first"] > c["second"] else ("igual" if c["first"] == c["second"] else "anterior")
        said = "anterior" if c["claim"] == "antes" else "posterior"
        parts.append(f"o relatório diz que {c['first_text']} é {said} a {c['second_text']}, "
                     f"mas pelo calendário é {real}")
    return " Cronologia (calculada a partir das datas do teu próprio relatório): " + "; ".join(parts) + "."
