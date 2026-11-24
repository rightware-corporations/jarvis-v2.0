"""F01-A (EXPERIMENTAL, LAB): structured exchange-rate tool backed by the Banco de Moçambique daily bulletins.

``get_exchange_rate(base_currency, quote_currency, reference_date)`` — generic tool, NOT a canned answer:
* locates the bulletin for the requested date (or the most recent one listed) in the BM index page;
* converts the PDF to text on the host (fixed ``pdftotext`` binary) and PARSES the tables generically: country,
  currency name, unit (1 or 1000 units), buy, sell and mid ("COMPRA / VENDA / MÉDIA");
* maps rows to ISO 4217 codes with a static reference table (country + currency name), keeping CNH (China/Offshore)
  and CNY (China) apart; unknown or duplicated rows are reported as AMBIGUOUS, never guessed;
* returns a STRUCTURED record: status, pair, reference date (as printed in the bulletin), requested date, values,
  unit, rate type, document provenance (URL, sha256, bulletin number, signature line), retrieval time, and an
  explicit derivation when the value is computed (inverse, cross rate) — computations are reproducible from the
  record. Status values: OK, DERIVED, NOT_LISTED, NOT_RETRIEVED, STALE, AMBIGUOUS, UNSUPPORTED, PARSE_ERROR.
No value, date, bulletin number or question is fixed in this code. The document source is injected: here an
OFFLINE replay of the bytes collected in OP01-FX-REAL-PROXY (no network) or independent fixtures."""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import html
import re
import subprocess
import tempfile
import unicodedata
from urllib.parse import urljoin

INDEX_URL = "https://www.bancomoc.mz/pt/tabelas-de-taxas-de-cambio-de-referencia-diarias/2026-2025/"
MONTHS = {m: i for i, m in enumerate(("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
                                       "setembro", "outubro", "novembro", "dezembro"), 1)}
# Reference data (ISO 4217 by country + currency name as printed by BM). Not answers: no values, no dates.
ISO = {("estados unidos", "dolar"): "USD", ("africa do sul", "rand"): "ZAR", ("botswana", "pula"): "BWP",
       ("eswatini", "lilangueni"): "SZL", ("mauricias", "rupia"): "MUR", ("zambia", "kwacha"): "ZMW",
       ("japao", "iene"): "JPY", ("malawi", "kwacha"): "MWK", ("tanzania", "shilling"): "TZS",
       ("zimbabwe", "dolar"): "ZWG", ("brasil", "real"): "BRL", ("canada", "dolar"): "CAD",
       ("china/offshore", "renminbi"): "CNH", ("china", "renminbi"): "CNY", ("dinamarca", "coroa"): "DKK",
       ("inglaterra", "libra"): "GBP", ("noruega", "coroa"): "NOK", ("suecia", "coroa"): "SEK",
       ("suica", "franco"): "CHF", ("uniao europeia", "euro"): "EUR"}
NUM = r"(\d{1,3}(?:\.\d{3})*,\d+|\d+,\d+)"
ROW = re.compile(rf"^\s*(?P<country>[^\d]+?)(?:\(a\))?\s{{2,}}(?P<cur>[A-Za-zÀ-ÿ]+)\s+(?P<buy>{NUM})\s+(?P<sell>{NUM})\s+(?P<mid>{NUM})\s*$")


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)).strip()


def pt_number(s: str) -> float:
    """'3.629,39' → 3629.39; '63,27' → 63.27 (BM uses '.' thousands and ',' decimals)."""
    return float(s.replace(".", "").replace(",", "."))


def pdf_text(raw: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as t:
        t.write(raw)
        t.flush()
        out = subprocess.run(["/usr/bin/pdftotext", "-layout", "-nopgbrk", "-enc", "UTF-8", t.name, "-"],
                             capture_output=True, timeout=10, check=False)
    if out.returncode != 0:
        raise ValueError("PDF ilegível")
    return out.stdout.decode("utf-8", errors="replace")


# ----------------------------------------------------------------------------------------------- parsing
def parse_index(markup: str, base: str = INDEX_URL) -> list[dict]:
    """[{date: 'YYYY-MM-DD', url}] for every daily-bulletin link, newest first. Date from the link text
    (dd-mm-yyyy) or, failing that, from the file name (…do-dia-DDMMYYYY.pdf)."""
    out = []
    for href, text in re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', markup, re.S | re.I):
        t = html.unescape(re.sub(r"<[^>]+>", " ", text))
        m = re.search(r"\b(\d{2})-(\d{2})-(\d{4})\b", t) or re.search(r"dia-(\d{2})(\d{2})(\d{4})\.pdf", html.unescape(href))
        if not m or "dia" not in fold(t + href):
            continue
        try:
            d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        out.append({"date": d.isoformat(), "url": urljoin(base, html.unescape(href))})
    return sorted({o["date"]: o for o in out}.values(), key=lambda o: o["date"], reverse=True)


def parse_bulletin(text: str) -> dict:
    """Generic table parser. Returns reference date, bulletin number, signature line, rows and parse issues."""
    issues = []
    m = re.search(r"DO DIA\s+(\d{1,2})\s+([A-Za-zçÇ]+)\s*(?:de)?\s*(\d{4})", " ".join(text.split()), re.I)
    ref = None
    if m and fold(m.group(2)) in MONTHS:
        ref = dt.date(int(m.group(3)), MONTHS[fold(m.group(2))], int(m.group(1))).isoformat()
    else:
        issues.append("data de referência não encontrada")
    num = re.search(r"BOLETIM\s+N[ºo°]?\s*([\d/]+)", text, re.I)
    sig = re.search(r"([A-Z][a-zà-ÿ]+),\s*(\d{2})\.(\d{2})\.(\d{4})", text)
    rows, unit = [], 1
    for line in text.splitlines():
        lf = fold(line)
        if "por 1000 unidades" in lf:
            unit = 1000
        elif "por unidade" in lf:
            unit = 1
        r = ROW.match(line)
        if not r:
            continue
        country, cur = fold(r.group("country")).replace("(a)", "").strip(), fold(r.group("cur"))
        rows.append({"country": r.group("country").strip(), "currency": r.group("cur"), "iso": ISO.get((country, cur)),
                     "unit": unit, "buy": pt_number(r.group("buy")), "sell": pt_number(r.group("sell")),
                     "mid": pt_number(r.group("mid")),
                     "raw": {"buy": r.group("buy"), "sell": r.group("sell"), "mid": r.group("mid")}})
    for r in rows:
        if r["iso"] is None:
            issues.append(f"moeda sem código ISO conhecido: {r['country']} / {r['currency']}")
        elif not (r["buy"] <= r["mid"] <= r["sell"]):
            issues.append(f"{r['iso']}: compra/média/venda fora de ordem")
    return {"reference_date": ref, "bulletin": num.group(1) if num else None,
            "signature": {"place": sig.group(1), "date": f"{sig.group(4)}-{sig.group(3)}-{sig.group(2)}"} if sig else None,
            "rows": rows, "issues": issues,
            "rate_type": "taxas de câmbio médias de referência do mercado cambial (compra/venda/média), em meticais"}


# ------------------------------------------------------------------------------------------------- tool
@dataclasses.dataclass
class Source:
    """Document source. ``get(url) -> (bytes, content_type, retrieved_at) | None``; None = not retrieved."""
    get: callable
    label: str


TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "get_exchange_rate",
        "description": ("Taxas de câmbio oficiais do Banco de Moçambique (meticais por moeda estrangeira): compra, "
                        "venda e média de um boletim diário, com data e fonte. Usa para qualquer pergunta sobre "
                        "câmbio com o metical."),
        "parameters": {"type": "object", "properties": {
            "base_currency": {"type": "string", "description": "código ISO da moeda estrangeira, ex.: USD, EUR, ZAR"},
            "quote_currency": {"type": "string", "description": "código ISO da moeda de cotação; normalmente MZN"},
            "reference_date": {"type": "string", "description": "data AAAA-MM-DD, ou 'latest' para a mais recente"}},
            "required": ["base_currency", "quote_currency"]}}}


class ExchangeRateTool:
    def __init__(self, source: Source, *, today: str, index_url: str = INDEX_URL, stale_days: int = 4):
        self.source, self.today, self.index_url, self.stale_days = source, today, index_url, stale_days
        self.records: list[dict] = []                # every structured result returned (for the integrity gate)

    def _bulletin(self, date: str | None) -> tuple[dict | None, dict]:
        got = self.source.get(self.index_url)
        if got is None:
            return None, {"status": "NOT_RETRIEVED", "detail": "índice de boletins não disponível"}
        markup, _, _ = got
        listed = parse_index(markup.decode("utf-8", errors="replace"), self.index_url)
        if not listed:
            return None, {"status": "PARSE_ERROR", "detail": "nenhum boletim diário reconhecido no índice"}
        entry = listed[0] if date in (None, "", "latest") else next((x for x in listed if x["date"] == date), None)
        if entry is None:
            return None, {"status": "NOT_LISTED", "detail": f"sem boletim publicado para {date} no índice consultado",
                          "nearest_listed": [x["date"] for x in listed[:3]]}
        doc = self.source.get(entry["url"])
        if doc is None:
            return None, {"status": "NOT_RETRIEVED", "detail": f"boletim de {entry['date']} listado mas não obtido",
                          "document_url": entry["url"]}
        raw, ctype, retrieved = doc
        text = pdf_text(raw) if "pdf" in ctype else raw.decode("utf-8", errors="replace")
        b = parse_bulletin(text)
        b.update(document_url=entry["url"], sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=retrieved,
                 listed_date=entry["date"])
        return b, {}

    def __call__(self, base_currency: str, quote_currency: str = "MZN", reference_date: str | None = None) -> dict:
        base, quote = (base_currency or "").strip().upper(), (quote_currency or "MZN").strip().upper()
        out = {"tool": "get_exchange_rate", "source": self.source.label, "requested": {
            "base": base, "quote": quote, "reference_date": reference_date or "latest"}}
        if not re.fullmatch(r"[A-Z]{3}", base) or not re.fullmatch(r"[A-Z]{3}", quote) or base == quote:
            out.update(status="UNSUPPORTED", detail="códigos ISO de 3 letras e diferentes são obrigatórios")
            return self._keep(out)
        b, err = self._bulletin(reference_date)
        if b is None:
            out.update(err)
            return self._keep(out)
        prov = {"document_url": b["document_url"], "sha256": b["sha256"], "bulletin": b["bulletin"],
                "signature": b["signature"], "retrieved_at": b["retrieved_at"], "listed_date": b["listed_date"]}
        out.update(reference_date=b["reference_date"], rate_type=b["rate_type"], provenance=prov,
                   parse_issues=b["issues"])
        if b["reference_date"] and b["reference_date"] != b["listed_date"]:
            out["parse_issues"] = out["parse_issues"] + ["data no documento difere da data do índice"]

        def row(code):
            hits = [r for r in b["rows"] if r["iso"] == code]
            return hits
        if "MZN" not in (base, quote):
            hb, hq = row(base), row(quote)
            if len(hb) != 1 or len(hq) != 1:
                out.update(status="AMBIGUOUS" if len(hb) > 1 or len(hq) > 1 else "UNSUPPORTED",
                           detail="taxa cruzada exige exactamente uma linha de cada moeda no boletim")
                return self._keep(out)
            v = (hb[0]["mid"] / hb[0]["unit"]) / (hq[0]["mid"] / hq[0]["unit"])
            out.update(status="DERIVED", value=round(v, 6), measure="média", unit=f"{quote} por 1 {base}",
                       derivation=f"({hb[0]['mid']} MZN/{hb[0]['unit']} {base}) ÷ ({hq[0]['mid']} MZN/{hq[0]['unit']} {quote})")
            return self._keep(self._age(out))
        foreign = base if quote == "MZN" else quote
        hits = row(foreign)
        if not hits:
            out.update(status="UNSUPPORTED", detail=f"{foreign} não consta do boletim")
            return self._keep(out)
        if len(hits) > 1:
            out.update(status="AMBIGUOUS", detail=f"{len(hits)} linhas para {foreign}")
            return self._keep(out)
        r = hits[0]
        out.update(status="OK", country=r["country"], currency_name=r["currency"],
                   unit=f"MZN por {r['unit']} {foreign}", buy=r["buy"], sell=r["sell"], mid=r["mid"],
                   printed=r["raw"])
        if base == "MZN":                                  # inverse: computed, reproducible, labelled
            out.update(status="DERIVED", inverse={"value": round(r["unit"] / r["mid"], 8), "measure": "média",
                                                   "unit": f"{foreign} por 1 MZN",
                                                   "derivation": f"{r['unit']} ÷ {r['mid']}"})
        return self._keep(self._age(out))

    def _age(self, out: dict) -> dict:
        ref = out.get("reference_date")
        if ref and (dt.date.fromisoformat(self.today) - dt.date.fromisoformat(ref)).days > self.stale_days:
            out["status_note"] = "STALE: dados com mais de {} dias".format(self.stale_days)
        out["consulted_on"] = self.today
        return out

    def _keep(self, out: dict) -> dict:
        self.records.append(out)
        return out
