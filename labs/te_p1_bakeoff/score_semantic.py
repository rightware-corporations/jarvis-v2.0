"""Deterministic SEMANTIC check of an agent's T1 report (complements, never replaces, score.py).

Why: the fixed T1 instruction asks for "a JSON report with the properties and sources" but, by design,
does not tell the agent the oracle's key names. ``score.py`` matches exact keys
(``recommendation``/``price_usd_month``/...), so a correct report with other key names fails there.
This checker is schema-tolerant but VALUE-strict:
* the recommended product must be TerraLens (found under a recommendation-like key);
* every product the report describes must carry the true values (Mac, CSV, offline, scheduled
  automation, price) — a single wrong value fails;
* all three products must be described, and the TerraLens source must be the factsheet mirror.

The same function is applied to every candidate. HTTP evidence (score.py) remains the independent
proof of what was fetched; this only checks the delivered report against the fixture truth.
"""
from __future__ import annotations

import json
import re
import sys

TRUTH = {
    "atlasboard": {"mac": True, "csv": True, "offline": True, "scheduled": False, "price": 0},
    "novaview": {"mac": True, "csv": True, "offline": False, "scheduled": True, "price": 9},
    "terralens": {"mac": True, "csv": True, "offline": True, "scheduled": True, "price": 12},
}
_FIELD = {
    # JRV-BP-044 fix: "mac" must start a word ("automacoes"/"automações" contain "mac" and were misread
    # as the Mac field once every occurrence was checked).
    "mac": re.compile(r"(?<![a-z])mac", re.I),
    "csv": re.compile(r"csv", re.I),
    "offline": re.compile(r"offline", re.I),
    "scheduled": re.compile(r"sched|agend|automa", re.I),
    "price": re.compile(r"pre[cç]o|price|cost|usd", re.I),
}


def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("yes", "sim", "true", "y", "✓", "✅"):
            return True
        if s in ("no", "não", "nao", "false", "n", "✗", "❌"):
            return False
    return None


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        m = re.search(r"\d+(?:\.\d+)?", v)
        return float(m.group()) if m else None
    return None


def _product_dicts(obj, out):
    """Every dict that names one of the three products (by a name-like value or as a key)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()
            if key in TRUTH and isinstance(v, dict):
                out.append((key, v))
        for k in ("name", "product", "product_name", "nome", "produto"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip().lower() in TRUTH:
                out.append((v.strip().lower(), obj))
        for v in obj.values():
            _product_dicts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _product_dicts(v, out)
    return out


def _flatten(d, prefix=""):
    flat = {}
    for k, v in d.items():
        if isinstance(v, dict):
            flat.update(_flatten(v, f"{prefix}{k}."))
        elif not isinstance(v, list):
            flat[f"{prefix}{k}"] = v
    return flat


def _recommended(obj):
    if not isinstance(obj, dict):
        return None
    for k, v in obj.items():
        # Audit fix (JRV-BP-039): the key must START with recommend/recomend ("not_recommended" is not one).
        if re.match(r"(recomend|recommend)", str(k), re.I):
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                for kk in ("product_name", "name", "product", "nome", "produto"):
                    if isinstance(v.get(kk), str):
                        return v[kk]
    for v in obj.values():
        r = _recommended(v) if isinstance(v, dict) else None
        if r:
            return r
    return None


def check(report) -> dict:
    if not isinstance(report, dict):
        return {"semantic_gate": "FAIL", "reason": "no JSON object report"}
    rec = _recommended(report)
    found, errors = {}, []
    # Audit fix (JRV-BP-039): EVERY occurrence of a value is checked; a later correct value can no
    # longer hide an earlier contradictory one.
    for name, d in _product_dicts(report, []):
        flat = _flatten(d)
        for field, pattern in _FIELD.items():
            for k, v in flat.items():
                leaf = k.rsplit(".", 1)[-1]
                if field == "price" and pattern.search(leaf) and _num(v) is not None and "max" not in leaf.lower():
                    found.setdefault(name, {}).setdefault("price", []).append(_num(v))
                elif field != "price" and pattern.search(leaf) and _bool(v) is not None:
                    found.setdefault(name, {}).setdefault(field, []).append(_bool(v))
    for name, values in found.items():
        for field, seen in values.items():
            for value in seen:
                if value != TRUTH[name][field]:
                    errors.append(f"{name}.{field}={value!r} (true {TRUTH[name][field]!r})")
    text = json.dumps(report, ensure_ascii=False)
    complete = all(set(found.get(n, {})) == set(_FIELD) for n in TRUTH)
    factsheet = "/vendors/terralens-factsheet" in text
    ok = (isinstance(rec, str) and rec.strip().lower() == "terralens" and not errors and complete and factsheet)
    return {"semantic_gate": "PASS" if ok else "FAIL", "recommended": rec, "products_found": sorted(found),
            "values_complete_for_all_three": complete, "value_errors": errors,
            "factsheet_source_cited": factsheet}


if __name__ == "__main__":
    print(json.dumps(check(json.load(open(sys.argv[1], encoding="utf-8"))), ensure_ascii=False, indent=2))
