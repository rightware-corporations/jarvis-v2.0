"""WORK-04 R2-A: deterministic lint of the `## Achados` lines of the agent's OWN report.

Run 43066548100: facts and the EVOLUÇÃO finding were right, ORACLE PASS, but
V2 failed R1/R5 because the finding line was written `- EVOLUÇÃO: …` instead
of `- [EVOLUÇÃO] campo: descrição`. The verify feedback only said «estrutura
incompleta», so the model repeated the same shape.

This lint:
* reads ONLY the report text (never truth, sources, V2 or ORACLE internals);
* quotes the offending lines (sanitised, length-bounded) and states the
  required shape;
* never rewrites the report and never changes any verdict: V2 and ORACLE are
  untouched and still decide PASS/FAIL.
The accepted shape mirrors what V2 parses (`- [TIPO] campo: descrição`), so a
line the lint accepts is a line V2 can read; it does not imply V2 PASS.
"""
from __future__ import annotations

import re
import unicodedata

TYPES = ("CONTRADIÇÃO", "EVOLUÇÃO", "INCONSISTÊNCIA TEMPORAL", "EM FALTA", "SEM ACHADOS")
REQUIRED = "- [TIPO] campo: descrição"
MAX_QUOTE = 100
MAX_ISSUES = 4
_CTRL = re.compile(r"[\x00-\x1f\x7f​-‏ -‮⁠-⁤﻿]")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).upper().strip()


_FOLDED_TYPES = {_fold(t): t for t in TYPES}
_TYPE_START = re.compile(r"^\s*(?:[-*+]\s*)?[(*_<{]*\s*(" + "|".join(
    re.escape(k) for k in sorted(_FOLDED_TYPES, key=len, reverse=True)) + r")\b")
_VALID = re.compile(r"^\s*[-*]\s*\[([^\]]+)\]\s*(.*)$")


def _quote(line: str) -> str:
    clean = _CTRL.sub("", line).strip().replace("«", "\"").replace("»", "\"")
    return "«" + (clean[:MAX_QUOTE] + "…" if len(clean) > MAX_QUOTE else clean) + "»"


def _achados_lines(report: str) -> list[str] | None:
    lines, inside, found = [], False, False
    for raw in (report or "").splitlines():
        m = re.match(r"^\s*##\s+(.+?)\s*$", raw)
        if m:
            inside = _fold(m.group(1)).startswith("ACHADO")
            found = found or inside
            continue
        if inside and raw.strip():
            lines.append(raw)
    return lines if found else None


def lint_findings(report: str) -> list[dict]:
    """Problems in the `## Achados` section, as {line, problem}; [] when well formed."""
    lines = _achados_lines(report)
    if lines is None:
        return [{"line": None, "problem": "falta a secção '## Achados'"}]
    issues, valid = [], 0
    for line in lines:
        m = _VALID.match(line)
        if m:
            typ = _FOLDED_TYPES.get(_fold(m.group(1)))
            rest = m.group(2).strip()
            if typ is None:
                issues.append({"line": line, "problem": "TIPO entre parênteses rectos não é um dos tipos permitidos"})
            elif typ != "SEM ACHADOS" and (":" not in rest or not rest.split(":", 1)[0].strip()):
                issues.append({"line": line, "problem": "falta 'campo:' depois de [TIPO]"})
            else:
                valid += 1
            continue
        folded = _fold(line)
        if _TYPE_START.match(folded):
            issues.append({"line": line, "problem": "o TIPO não está entre parênteses rectos"})
        elif re.match(r"^\s*[-*+]\s", line):
            issues.append({"line": line, "problem": "linha de lista sem '[TIPO]' no início"})
        # other non-list prose inside Achados is narrative; V2 reads it as such
    if not valid and not issues:
        issues.append({"line": None, "problem": "nenhuma linha de achado no formato exigido"})
    return issues


def feedback(report: str) -> str:
    issues = lint_findings(report)
    if not issues:
        return ""
    shown = []
    for it in issues[:MAX_ISSUES]:
        shown.append((_quote(it["line"]) + ": " if it["line"] is not None else "") + it["problem"])
    more = f" (+{len(issues) - MAX_ISSUES} outras)" if len(issues) > MAX_ISSUES else ""
    return (" Formato dos achados (verificado só no texto do teu relatório): " + "; ".join(shown) + more +
            f". Cada achado tem de ser exactamente '{REQUIRED}', com TIPO ∈ {', '.join(TYPES)} "
            "entre parênteses rectos.")
