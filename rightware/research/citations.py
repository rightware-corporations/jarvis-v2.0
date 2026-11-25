"""Host-side validation of citations: does the CITED source actually SUPPORT the statement?

A citation existing is not support. For each statement of the answer:
* ``SUPPORTED``: one PASSAGE (a few adjacent sentences) of a cited, actually read source contains every number of the
  statement (equal value, or the source value rounded to the statement's precision) AND enough of its content words;
  a statement without numbers needs a strong word overlap in one passage.
* ``DERIVED``: a number is not printed in the source but is reproduced by simple arithmetic from numbers of the same
  supporting passage(s) or of the question (difference, % change, ratio, product) — shown as computed, not quoted.
* ``NUMBERS_OUT_OF_CONTEXT``: the numbers exist somewhere in the source, but never together with the statement's
  context (the "number appears somewhere in the document" case is explicitly NOT verification).
* ``UNSUPPORTED``: the cited source does not contain it. ``INVALID_CITATION``: cites a source that was not read.
* ``UNCITED``: a factual statement (with numbers) without citation and NOT supported by any source read;
  ``SUPPORTED_UNCITED`` / ``DERIVED_UNCITED``: no explicit citation, but a read source supports it (attribution missing).
Contradictions: other read sources with a passage about the same thing but different numbers are reported.
This is lexical/numeric evidence checking, not semantic proof; ``answer_factually_verified`` stays False.
"""
from __future__ import annotations

import dataclasses
import re

from rightware.research.text import content_words, decimals, fold, numbers, sentences

CITE = re.compile(r"[\[(]\s*((?:S\d{1,2}\s*[,;e/]?\s*)+)[\])]|\bfonte\s+(S\d{1,2})\b", re.I)
SRC_ID = re.compile(r"S(\d{1,2})", re.I)
YEARLIKE = range(1900, 2101)
DATE_DAY = re.compile(r"\b\d{1,2}(?=\s+de\s+(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|"
                      r"outubro|novembro|dezembro)\b)", re.I)


@dataclasses.dataclass
class Verdict:
    statement: str
    cited: list[str]
    status: str
    source: str | None = None
    detail: str = ""
    conflicts: list[str] = dataclasses.field(default_factory=list)


def _passages(text: str, width: int = 2) -> list[str]:
    sents = sentences(text)
    if not sents:
        return []
    return [" ".join(sents[i:i + width]) for i in range(max(1, len(sents) - width + 1))]


def _matches(claim_tok: str, claim_v: float, src: list[tuple[str, float]]) -> bool:
    d = decimals(claim_tok)
    for _, v in src:
        if abs(v - claim_v) < 1e-9 or round(v, d) == round(claim_v, d) and d < decimals_of(v):
            return True
    return False


def decimals_of(v: float) -> int:
    s = f"{v:.6f}".rstrip("0").split(".")
    return len(s[1]) if len(s) > 1 else 0


def _key(w: str) -> str:
    return w[:4] if len(w) <= 5 else w[:5]       # light prefix match: taxa/taxas, publicado/publicação


def _word_ratio(words: list[str], passage_fold: str) -> float:
    if not words:
        return 0.0
    toks = [t for t in re.findall(r"[a-z0-9]+", passage_fold) if len(t) >= 3]
    return sum(1 for w in words if any(t.startswith(_key(w)) for t in toks)) / len(words)


def _derived(target: float, d: int, pool: list[float]) -> str | None:
    pool = [p for p in pool if p not in YEARLIKE or p != int(p)][:30]
    for i, a in enumerate(pool):
        for b in pool[i + 1:] + pool[:i]:
            cands = {"diferença": b - a, "soma": a + b, "produto": a * b}
            if a:
                cands["variação %"] = (b - a) / a * 100
                cands["razão %"] = b / a * 100
                cands["razão"] = b / a
            for name, v in cands.items():
                if round(abs(v), d) == round(abs(target), d):
                    return name
    return None


def _strip_citations(s: str) -> str:
    return CITE.sub(" ", s)


def validate(answer: str, sources: dict[str, dict], question: str = "") -> list[Verdict]:
    """``sources``: {"S1": {"text": ..., "url": ...}} (only sources actually read in this question)."""
    q_nums = [v for _, v in numbers(question)]
    src_pass = {sid: [(p, fold(p), numbers(p)) for p in _passages(s.get("text", ""))] for sid, s in sources.items()}
    out: list[Verdict] = []
    for st in sentences(answer):
        cited = []
        for m in CITE.finditer(st):
            cited += [f"S{int(x)}" for x in SRC_ID.findall(m.group(1) or m.group(2) or "")]
        body = _strip_citations(st).replace("**", "").replace("__", "")
        # numbers already in the QUESTION (dates, amounts the user gave) are not new factual claims
        nums = [(t, v) for t, v in numbers(DATE_DAY.sub(" ", body)) if not any(abs(v - q) < 1e-9 for q in q_nums)]
        words = content_words(body)
        implicit = False
        if not cited:
            if not (nums and sources and len(words) >= 2):
                continue
            cited, implicit = list(sources), True          # check against every source actually read
        bad = [c for c in cited if c not in sources]
        if bad and len(bad) == len(cited):
            out.append(Verdict(st, cited, "INVALID_CITATION", detail="cita fonte não lida: " + ", ".join(bad)))
            continue
        best: tuple[float, str, str, list] | None = None
        status, detail = "UNSUPPORTED", "a fonte citada não contém esta afirmação"
        anywhere = False
        for sid in [c for c in cited if c in sources]:
            all_src_nums = [x for _, _, ns in src_pass[sid] for x in ns]
            if nums and all(_matches(t, v, all_src_nums) for t, v in nums):
                anywhere = True
            for p, pf, pn in src_pass[sid]:
                ratio = _word_ratio(words, pf)
                hit = [(t, v) for t, v in nums if _matches(t, v, pn)]
                score = ratio + len(hit)
                if best is None or score > best[0]:
                    best = (score, sid, p, pn)
                if nums:
                    if len(hit) == len(nums) and ratio >= 0.33:
                        status, detail = "SUPPORTED", ""
                        break
                elif len(words) >= 3 and ratio >= 0.6:
                    status, detail = "SUPPORTED", ""
                    break
            if status == "SUPPORTED":
                break
        sid = best[1] if best else None
        if status != "SUPPORTED" and nums and best is not None:
            missing = [(t, v) for t, v in nums if not _matches(t, v, best[3])]
            pool = [v for _, v in best[3]] + q_nums
            how = [_derived(v, decimals(t), pool) for t, v in missing]
            ctx_ok = _word_ratio(words, fold(best[2])) >= 0.33
            if ctx_ok and missing and all(how):
                status, detail = "DERIVED", "calculado a partir da fonte (" + ", ".join(sorted(set(how))) + ")"
            elif anywhere:
                status, detail = "NUMBERS_OUT_OF_CONTEXT", "os números existem na fonte mas não neste contexto"
        if implicit:
            if status == "SUPPORTED":
                status, detail = "SUPPORTED_UNCITED", f"sem citação explícita; suportada por {sid}"
            elif status == "DERIVED":
                status, detail = "DERIVED_UNCITED", f"sem citação explícita; calculada a partir de {sid}"
            else:
                status, detail, sid = "UNCITED", "afirmação com números sem citação e sem suporte nas fontes lidas", None
            cited = []
        v = Verdict(st, cited, status, sid, detail)
        if status.startswith(("SUPPORTED", "DERIVED")) and nums:
            v.conflicts = _conflicts(words, [x for _, x in nums], sid, src_pass)
        out.append(v)
    return out


def _conflicts(words: list[str], claim_vals: list[float], sid: str | None, src_pass: dict) -> list[str]:
    found = []
    for other, passages in src_pass.items():
        if other == sid:
            continue
        for p, pf, pn in passages:
            if _word_ratio(words, pf) < 0.5:
                continue
            vals = [v for _, v in pn if v not in YEARLIKE]
            diff = [v for v in vals if all(v != c for c in claim_vals)
                    and any(c and 0.5 <= v / c <= 2 for c in claim_vals if c not in YEARLIKE)]
            same = any(v in claim_vals for v in vals)
            if diff and not same:
                found.append(f"{other}: {_fmt(diff[0])}")
                break
    return found


def _fmt(v: float) -> str:
    s = f"{v:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
    return s


def summary(verdicts: list[Verdict]) -> dict:
    c: dict[str, int] = {}
    for v in verdicts:
        c[v.status] = c.get(v.status, 0) + 1
    return {"statements_checked": len(verdicts), **{k.lower(): n for k, n in sorted(c.items())},
            "conflicts": sum(1 for v in verdicts if v.conflicts)}


PROBLEM = ("UNSUPPORTED", "INVALID_CITATION", "NUMBERS_OUT_OF_CONTEXT", "UNCITED")


def host_lines(verdicts: list[Verdict]) -> list[str]:
    """Annotation lines (host-owned; the voice filter never reads them). ⚠ only when a statement is not supported."""
    if not verdicts:
        return []
    s = summary(verdicts)
    bad = [v for v in verdicts if v.status in PROBLEM]
    mark = "⚠" if bad else "✓"
    sup = s.get("supported", 0) + s.get("supported_uncited", 0)
    der = s.get("derived", 0) + s.get("derived_uncited", 0)
    head = (f"{mark} Verificação do anfitrião (citações): {sup} suportada(s), {der} calculada(s), {len(bad)} sem "
            f"suporte, em {s['statements_checked']} afirmação(ões)"
            + (f"; {s.get('supported_uncited', 0) + s.get('derived_uncited', 0)} sem citação explícita"
               if s.get("supported_uncited") or s.get("derived_uncited") else "") + ".")
    lines = [head]
    labels = {"UNSUPPORTED": "sem suporte na fonte citada", "INVALID_CITATION": "cita fonte não lida",
              "NUMBERS_OUT_OF_CONTEXT": "números fora de contexto", "UNCITED": "sem citação"}
    for v in bad[:4]:
        lines.append(f"✓ Verificação do anfitrião (citações): «{v.statement[:90]}» — {labels[v.status]}.")
    for v in [v for v in verdicts if v.conflicts][:3]:
        lines.append(f"✓ Verificação do anfitrião (divergência): outra fonte indica valor diferente "
                     f"({'; '.join(v.conflicts)}) para «{v.statement[:70]}».")
    return lines
