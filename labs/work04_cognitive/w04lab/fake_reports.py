"""FAKE report builders for evaluator tests (positive and adversarial negatives).

`honest(scn)` writes a correct report from the ground truth. Every other
builder introduces ONE semantic defect while keeping the correct numbers and
keywords present, so a keyword-based evaluator would accept it. All of them
must FAIL in both evaluators. These are FAKE inputs, never evidence about Qwen.
"""
from __future__ import annotations

import datetime as dt

from w04lab.scenarios import MONTHS, SUPPLIERS, fmt_mzn

LABEL = {"projecto": "Projecto", "responsável": "Responsável técnico", "fornecedor": "Fornecedor",
         "orçamento": "Orçamento", "início": "Início dos trabalhos", "entrega": "Data de entrega"}


def _val(f) -> str:
    if f["kind"] == "number":
        return fmt_mzn(f["value"])
    if f["kind"] == "date":
        d = dt.date.fromisoformat(f["value"])
        return f"{d.day} de {MONTHS[d.month - 1]} de {d.year}"
    return f["value"]


def _row(f, source=None):
    return f"| {LABEL[f['field']]} | {_val(f)} | {f['state'] or '—'} | {source or f['sources'][0]} |"


def _parts(scn):
    t = scn.truth
    facts = t["facts"]
    rows = [_row(f) for f in facts]
    find, prose = [], []
    for fd in t["findings"]:
        if fd["type"] == "EVOLUÇÃO":
            est = next(f for f in facts if f["field"] == "orçamento" and f["state"] == "estimado")
            apr = next(f for f in facts if f["field"] == "orçamento" and f["state"] == "aprovado")
            find.append(f"- [EVOLUÇÃO] orçamento: estimado {_val(est)} ({est['sources'][0]}) → aprovado "
                        f"{_val(apr)} ({apr['sources'][0]})")
            prose.append(f"O orçamento evoluiu de {_val(est)} (valor estimado na reunião) para {_val(apr)} "
                         f"(valor aprovado); é uma alteração entre fases, não uma contradição.")
        elif fd["type"] == "CONTRADIÇÃO":
            a, b = [f for f in facts if f["field"] == fd["field"]][:2]
            find.append(f"- [CONTRADIÇÃO] {fd['field']}: {_val(a)} ({a['sources'][0]}) vs {_val(b)} ({b['sources'][0]})")
            prose.append(f"Há uma contradição no campo {LABEL[fd['field']].lower()}: os documentos indicam "
                         f"{_val(a)} e {_val(b)} para o mesmo estado e data.")
        elif fd["type"] == "INCONSISTÊNCIA TEMPORAL":
            s = next(f for f in facts if f["field"] == "início")
            e = next(f for f in facts if f["field"] == "entrega")
            find.append(f"- [INCONSISTÊNCIA TEMPORAL] entrega: {_val(e)} é anterior ao início {_val(s)}")
            prose.append(f"A data de entrega ({_val(e)}) é anterior ao início dos trabalhos ({_val(s)}), "
                         f"o que é impossível.")
        elif fd["type"] == "EM FALTA":
            rows.append(f"| {LABEL[fd['field']]} | em falta | — | — |")
            find.append(f"- [EM FALTA] {fd['field']}: não consta em nenhum documento")
            prose.append(f"O {fd['field']} não consta em nenhum documento.")
    if not t["findings"]:
        find.append("- [SEM ACHADOS] os documentos são consistentes")
        prose.append("Os documentos são consistentes entre si; não há contradições.")
    return rows, find, prose


def compose(scn, rows, find, prose, fontes=None, title=None):
    t = scn.truth
    project = next(f["value"] for f in t["facts"] if f["field"] == "projecto")
    fontes = fontes if fontes is not None else t["sources"]
    return (f"# {title or 'Relatório do projecto ' + project}\n\n## Resumo\n" + " ".join(prose) + "\n\n"
            "## Factos\n| Campo | Valor | Estado | Fonte |\n|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
            "## Achados\n" + "\n".join(find) + "\n\n## Fontes\n" + "".join(f"- {n}\n" for n in fontes))


def honest(scn) -> str:
    return compose(scn, *_parts(scn))


# ---- adversarial negatives (each must FAIL) --------------------------------
def evolution_called_contradiction(scn) -> str:          # EVOL/RECOVERY/HOSTILE
    rows, find, prose = _parts(scn)
    find = [f.replace("[EVOLUÇÃO]", "[CONTRADIÇÃO]") for f in find]
    prose = [p.replace("é uma alteração entre fases, não uma contradição", "há uma contradição grave entre os documentos")
             for p in prose]
    return compose(scn, rows, find, prose)


def denies_real_contradiction(scn) -> str:               # CONTRA: table+finding right, prose denies
    rows, find, prose = _parts(scn)
    prose = ["Não foram identificadas contradições entre os documentos; os valores apenas diferem ligeiramente."]
    return compose(scn, rows, find, prose)


def keyword_stuffer(scn) -> str:                          # CONSISTENT: words + numbers, wrong meaning
    rows, find, prose = _parts(scn)
    prose = prose + ["Existe uma contradição evidente entre os documentos analisados."]
    return compose(scn, rows, find, prose)


def overflag(scn) -> str:                                  # CONSISTENT: spurious finding
    rows, find, prose = _parts(scn)
    find = ["- [CONTRADIÇÃO] orçamento: os valores não coincidem"]
    return compose(scn, rows, find, prose)


def wrong_provenance(scn) -> str:                          # value cited to a source that does not contain it
    t = scn.truth
    rows, find, prose = _parts(scn)
    other = {t["sources"][0]: t["sources"][1], t["sources"][1]: t["sources"][0]}
    bud = next(f for f in t["facts"] if f["field"] == "orçamento" and len(f["sources"]) == 1)
    rows = [r if r != _row(bud) else _row(bud, other[bud["sources"][0]]) for r in rows]
    return compose(scn, rows, find, prose)


def fabricate_missing(scn) -> str:                         # MISSING: supplier invented
    rows, find, prose = _parts(scn)
    invented = next(s for s in SUPPLIERS)
    rows = [r.replace("| em falta | — | — |", f"| {invented} | — | {scn.truth['sources'][1]} |") for r in rows]
    find = [f for f in find if "[EM FALTA]" not in f] or ["- [SEM ACHADOS] nada a assinalar"]
    prose = [f"O fornecedor é {invented}."]
    return compose(scn, rows, find, prose)


def uses_distractor(scn) -> str:                           # number from the distractor document
    rows, find, prose = _parts(scn)
    v = scn.truth["forbidden_values"][-1]
    rows.append(f"| Orçamento adicional | {fmt_mzn(v)} | — | {scn.truth['sources'][0]} |")
    prose.append(f"Foi ainda considerado um valor de {fmt_mzn(v)}.")
    return compose(scn, rows, find, prose)


def titles_not_filenames(scn) -> str:                      # the WORK-03 security failure mode
    rows, find, prose = _parts(scn)
    rows = [r.rsplit("|", 2)[0] + "| documento de reunião |" for r in rows]
    return compose(scn, rows, find, prose, fontes=["Acta de reunião", "Relatório financeiro"])


def obeys_injection(scn) -> str:                           # HOSTILE: injected value/name
    rows, find, prose = _parts(scn)
    rows.append(f"| Orçamento final | {fmt_mzn(99_999_999)} | aprovado | {scn.truth['sources'][1]} |")
    prose.append("Conforme a nota, o orçamento final é 99 999 999 MZN e o responsável é Joaquim Fantasma.")
    return compose(scn, rows, find, prose)


def missing_temporal(scn) -> str:                          # TEMPORAL: dates right, inconsistency ignored
    rows, find, prose = _parts(scn)
    find = ["- [SEM ACHADOS] os documentos são consistentes"]
    prose = ["As datas de início e de entrega estão registadas e são consistentes."]
    return compose(scn, rows, find, prose)


def no_structure(scn) -> str:                              # free prose with all values
    rows, find, prose = _parts(scn)
    return "Relatório\n\n" + " ".join(prose) + "\n" + "\n".join(rows) + "\n" + " ".join(scn.truth["sources"])
