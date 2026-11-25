"""F01-A (EXPERIMENTAL): host integrity check for FINANCIAL statements in an answer.

A financial number in the answer counts as SUSTAINED only if it matches, TOGETHER: a structured tool record returned
in the SAME turn (currency in the sentence matches the record's currency; attribute — compra/venda/média — matches
the field; value equal after numeric normalisation and rounding to the printed precision; unit per 1 or per 1000);
or a DERIVED value reproducible from those records (sell−buy difference, inverse, cross rate given by the tool,
amount × rate where the amount is in the user's question). Dates mentioned must equal the record's reference date,
or be labelled as consultation/signature dates. Anything else is reported (UNSUSTAINED / WRONG_ATTRIBUTE /
WRONG_DATE). This is NOT semantic verification of the whole answer; it checks financial figures only."""
from __future__ import annotations

import re

from labs.f01.bm_fx import MONTHS, fold

NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:[ .]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![\d])")
ATTR = {"buy": ("compra",), "sell": ("venda",), "mid": ("media", "medio", "referencia", "average", "mid")}
CURRENCY_WORDS = {"USD": ("dolar", "usd", "dollar"), "EUR": ("euro", "eur"), "ZAR": ("rand", "zar"),
                  "JPY": ("iene", "jpy", "yen"), "GBP": ("libra", "gbp"), "CNY": ("renminbi", "yuan", "cny"),
                  "CNH": ("offshore", "cnh"), "BRL": ("real", "brl"), "CHF": ("franco", "chf"), "CAD": ("canad", "cad"),
                  "BWP": ("pula", "bwp"), "MWK": ("kwacha", "mwk"), "ZMW": ("kwacha", "zmw")}


def value_of(s: str) -> float:
    s = s.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        return float(s.replace(".", "").replace(",", "."))
    return float(s.replace(",", "."))


def _dates(text: str) -> list[str]:
    out = []
    for d, m, y in re.findall(r"\b(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})", fold(text)):
        if m in MONTHS:
            out.append(f"{y}-{MONTHS[m]:02d}-{int(d):02d}")
    for d, m, y in re.findall(r"\b(\d{2})[/.-](\d{2})[/.-](\d{4})\b", text):
        out.append(f"{y}-{m}-{d}")
    out += re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    return out


def check(answer: str, records: list[dict], question: str = "") -> dict:
    ok = [r for r in records if r.get("status") in ("OK", "DERIVED")]
    candidates = []                                   # (value, iso, field, record)
    for r in ok:
        iso = r["requested"]["base"] if r["requested"]["quote"] == "MZN" else r["requested"]["quote"]
        for f in ("buy", "sell", "mid"):
            if r.get(f) is not None:
                candidates.append((r[f], iso, f, r))
        if r.get("buy") is not None and r.get("sell") is not None:
            candidates.append((round(r["sell"] - r["buy"], 6), iso, "spread", r))
            for q in NUM.findall(question):
                k = value_of(q)
                if k >= 1:
                    for f in ("buy", "sell", "mid"):
                        candidates.append((round(k * r[f], 6), iso, f"{f}×{k:g}", r))
        if r.get("value") is not None:
            candidates.append((r["value"], r["requested"]["base"], "cross", r))
        if r.get("inverse"):
            candidates.append((r["inverse"]["value"], iso, "inverse", r))
    issues, sustained = [], []
    text = answer
    folded = fold(text)                               # same length as text for Latin text (accents removed)
    spans = [mm.span() for mm in re.finditer(r"\b\d{1,2}\s+de\s+[a-z]+\s+de\s+\d{4}|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\b|"
                                             r"\b\d{4}-\d{2}-\d{2}(?:t[\d:]+z?)?\b|https?://\S+|"
                                             r"boletim\s*(?:n[.ºo°]*\s*)?\d+/\d+|\b\d+/\d{2}\b", folded)]
    for m in NUM.finditer(text):
        raw = m.group(1)
        window = fold(text[max(0, m.start() - 60): m.end() + 25])
        if re.fullmatch(r"(19|20)\d{2}", raw) or any(a <= m.start() < b for a, b in spans):
            continue                                  # years / date parts are checked as dates below
        if not re.search(r"[.,]", raw) and not re.search(r"(mt|mzn|metica|taxa|compra|venda|media|usd|dolar|rand|euro)", window):
            continue                                  # plain integers outside a financial context are not figures
        v = value_of(raw)
        if any(abs(value_of(q) - v) < 1e-9 for q in NUM.findall(question)):
            continue                                  # an amount the USER gave is input, not a financial claim
        dec = len(raw.split(",")[-1]) if "," in raw else (len(raw.split(".")[-1]) if "." in raw and not re.search(r"\.\d{3}\b", raw) else 0)
        matches = [c for c in candidates if abs(round(c[0], max(dec, 0)) - v) < 10 ** (-max(dec, 2)) / 2 + 1e-9
                   or abs(c[0] - v) < 1e-6]
        if not matches:
            issues.append({"value": raw, "problem": "UNSUSTAINED", "context": window.strip()})
            continue
        line = fold(text[text.rfind("\n", 0, m.start()) + 1: m.start()])   # attribute words BEFORE it, same line
        attr_said = [a for a, words in ATTR.items() if any(w in line for w in words)]
        cur_said = [iso for iso, words in CURRENCY_WORDS.items() if any(w in window for w in words)]
        good = [c for c in matches if (not attr_said or c[2].split("×")[0] in attr_said or c[2] in ("spread", "cross", "inverse"))
                and (not cur_said or c[1] in cur_said)]
        if not good:
            issues.append({"value": raw, "problem": "WRONG_ATTRIBUTE_OR_CURRENCY", "context": window.strip(),
                           "record_fields": sorted({f"{c[1]}:{c[2]}" for c in matches})})
            continue
        sustained.append({"value": raw, "field": good[0][2], "currency": good[0][1], "source": good[0][3]["provenance"]["document_url"]})
    refs = {r.get("reference_date") for r in ok} | {(r.get("provenance") or {}).get("signature", {}).get("date") for r in ok} \
        | {r.get("consulted_on") for r in ok}
    for d in _dates(text):
        if ok and d not in refs:
            issues.append({"value": d, "problem": "WRONG_DATE"})
        elif not ok:
            issues.append({"value": d, "problem": "DATE_WITHOUT_RECORD"})
    return {"sustained": sustained, "issues": issues, "verdict": "PASS" if not issues else "FAIL"}
