"""JRV-TE-P2B report contract ``te-p2b.report.v1``: pre-registered format of ``submit_report``.

What this module is
-------------------
* A minimal, versioned report SCHEMA derived from what the RIGHTWARE verifier actually consumes
  (``score_semantic.check``: a recommendation, per-product Mac/CSV/offline/scheduled/price values, and
  the consulted sources). It names fields, types and structure only — never a scenario value.
* ``validate_report``: a PURE, deterministic pre-filter (no I/O, no network, no tool call, no clock).
  Same input → same output. It decides FORMAT conformance only; it never judges content. A conformant
  report still goes to the unchanged RIGHTWARE verifier, which alone decides the verdict.
* Structured feedback made only of schema-defined paths, rule names, expected TYPES/constraints and fixed
  message codes. It never echoes submitted text (unknown keys are reported at the parent path, without
  the key name) and never states an expected VALUE.
* A hash-chained submission record (``chain_record``/``check_chain``) binding every submission to its
  ExecutionReceipt, the contract hash and the validation result, verifiable offline.

Strictness (pre-registered, see docs/research/TE_P2B_PREREGISTRATION.md): unknown keys rejected, missing
keys rejected, wrong types rejected (no coercion: "true" is not a boolean, "12" is not a number, a
boolean is not a number), duplicate keys rejected, NaN/Infinity rejected, invalid UTF-8 (lone
surrogates) rejected, control characters in strings rejected, no Unicode normalisation applied
(strings are compared exactly as sent).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re

CONTRACT_ID = "te-p2b.report.v1"
MAX_REPORT_BYTES = 8000            # UTF-8 bytes of the whole report text
MAX_SUBMISSIONS = 3                # policy approvals of submit_report per task attempt (pre-registered)
MAX_ERRORS_RETURNED = 20
NAME_MAX, URL_MAX = 80, 300
PRODUCTS_ITEMS, SOURCES_ITEMS = (1, 10), (1, 20)
PRICE_MAX = 100000

PRODUCT_FIELDS = {          # field -> JSON type (order = order of checks)
    "name": "string", "mac_support": "boolean", "csv_support": "boolean", "offline": "boolean",
    "scheduled_automation": "boolean", "price_usd_month": "number",
}
TOP_FIELDS = {"report_schema_version": "string", "recommendation": "string", "products": "array",
              "sources": "array"}

# The schema as data (its canonical JSON hash identifies the contract in every receipt record).
SCHEMA = {
    "contract": CONTRACT_ID, "type": "object", "additionalProperties": False, "required": list(TOP_FIELDS),
    "properties": {
        "report_schema_version": {"type": "string", "const": CONTRACT_ID},
        "recommendation": {"type": "string", "minLength": 1, "maxLength": NAME_MAX,
                           "x-reference": "must equal products[*].name of one item"},
        "products": {"type": "array", "minItems": PRODUCTS_ITEMS[0], "maxItems": PRODUCTS_ITEMS[1],
                     "x-unique": "name",
                     "items": {"type": "object", "additionalProperties": False, "required": list(PRODUCT_FIELDS),
                               "properties": {
                                   "name": {"type": "string", "minLength": 1, "maxLength": NAME_MAX},
                                   "mac_support": {"type": "boolean"}, "csv_support": {"type": "boolean"},
                                   "offline": {"type": "boolean"}, "scheduled_automation": {"type": "boolean"},
                                   "price_usd_month": {"type": "number", "minimum": 0, "maximum": PRICE_MAX}}}},
        "sources": {"type": "array", "minItems": SOURCES_ITEMS[0], "maxItems": SOURCES_ITEMS[1], "uniqueItems": True,
                    "items": {"type": "string", "maxLength": URL_MAX, "format": "http(s) URL"}},
    },
    "limits": {"max_report_bytes_utf8": MAX_REPORT_BYTES, "max_submissions": MAX_SUBMISSIONS},
}
SCHEMA_SHA256 = hashlib.sha256(json.dumps(SCHEMA, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

# Fixed messages per code: no interpolation of submitted content, ever.
MESSAGES = {
    "E_NOT_STRING": "o argumento report tem de ser texto",
    "E_ENCODING": "texto com codificação inválida (UTF-8)",
    "E_SIZE": "relatório acima do limite de tamanho",
    "E_JSON": "o texto não é JSON válido",
    "E_DUPLICATE_KEY": "chave repetida no mesmo objecto",
    "E_NONFINITE": "NaN e Infinity não são permitidos",
    "E_ROOT_TYPE": "a raiz tem de ser um objecto JSON",
    "E_VERSION": "report_schema_version desconhecida",
    "E_MISSING": "campo obrigatório em falta",
    "E_UNKNOWN_KEY": "chave não prevista no contrato (nome omitido)",
    "E_TYPE": "tipo errado",
    "E_LENGTH": "texto vazio ou acima do comprimento máximo",
    "E_CHARS": "caracteres de controlo não permitidos",
    "E_ITEMS": "número de itens fora do intervalo permitido",
    "E_FORMAT": "formato inválido",
    "E_RANGE": "número fora do intervalo permitido",
    "E_DUPLICATE_ITEM": "item repetido",
    "E_REFERENCE": "recommendation tem de ser igual ao name de um item de products",
}
DECISIONS = ("ACCEPTED_FOR_VERIFICATION", "REJECTED_SCHEMA", "DUPLICATE_SUBMISSION", "ALREADY_ACCEPTED")

EXAMPLE = ('{"report_schema_version":"te-p2b.report.v1","recommendation":"Exemplo Alfa","products":[{"name":'
           '"Exemplo Alfa","mac_support":true,"csv_support":false,"offline":false,"scheduled_automation":true,'
           '"price_usd_month":42.5}],"sources":["https://example.invalid/alfa"]}')

TOOL_DESCRIPTION = (
    "Entrega à RIGHTWARE o relatório final (contrato te-p2b.report.v1). O argumento report é o TEXTO de um único "
    "objecto JSON com EXACTAMENTE estas chaves (chaves não previstas são recusadas; não há conversão de tipos): "
    "report_schema_version: string, exactamente \"te-p2b.report.v1\"; "
    "recommendation: string (1 a 80 caracteres), igual ao name de um dos itens de products; "
    "products: lista de 1 a 10 objectos, cada um com EXACTAMENTE name (string 1 a 80, sem repetidos), "
    "mac_support (boolean), csv_support (boolean), offline (boolean: funciona sem ligação), "
    "scheduled_automation (boolean: automações agendadas), price_usd_month (número não negativo: preço mensal em USD); "
    "sources: lista de 1 a 20 URLs http(s) distintos que consultaste (string até 300 caracteres). "
    "Limite 8000 bytes UTF-8; sem NaN/Infinity; sem chaves repetidas. "
    "Exemplo APENAS estrutural, com valores fictícios que não pertencem à tarefa: " + EXAMPLE + ". "
    "No máximo 3 submissões por tarefa. Um relatório fora do contrato é recusado com os erros de formato "
    "(caminho, regra, código) e pode ser corrigido e reenviado; um texto idêntico a um já enviado é recusado; "
    "o primeiro relatório conforme é o final e as submissões seguintes são recusadas. Estar conforme não "
    "significa estar correcto: a conclusão é verificada pela RIGHTWARE a partir das execuções registadas."
)


@dataclasses.dataclass(frozen=True)
class ValidationResult:
    schema_valid: bool
    errors: tuple            # tuple of dicts {path, rule, expected, code}
    contract_id: str = CONTRACT_ID
    schema_sha256: str = SCHEMA_SHA256


class _DuplicateKey(Exception):
    pass


class _NonFinite(Exception):
    pass


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise _DuplicateKey()
        out[k] = v
    return out


def _nonfinite(_token):
    raise _NonFinite()


def _type_ok(value, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "number":           # a boolean is NOT a number (no coercion)
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


_URL = re.compile(r"https?://[^\s/?#]+[^\s]*\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _err(errors: list, path: str, rule: str, expected: str, code: str) -> None:
    errors.append({"path": path, "rule": rule, "expected": expected, "code": code})


def _string(errors, path, value, max_len, url=False) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return _err(errors, path, "encoding", "UTF-8", "E_ENCODING")
    if not 1 <= len(value) <= max_len:
        return _err(errors, path, "length", f"1..{max_len} caracteres", "E_LENGTH")
    if _CONTROL.search(value):
        return _err(errors, path, "characters", "sem caracteres de controlo", "E_CHARS")
    if url and not _URL.match(value):
        _err(errors, path, "format", "http(s) URL", "E_FORMAT")


def _finish(errors: list) -> ValidationResult:
    unique = sorted({tuple(sorted(e.items())) for e in errors})
    out = tuple(dict(e) for e in unique)[:MAX_ERRORS_RETURNED]
    return ValidationResult(not out, out)


def validate_report(text) -> ValidationResult:
    """Pure format validation of the submitted report text (see module docstring)."""
    errors: list = []
    if not isinstance(text, str):
        _err(errors, "$", "type", "string", "E_NOT_STRING")
        return _finish(errors)
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        _err(errors, "$", "encoding", "UTF-8", "E_ENCODING")
        return _finish(errors)
    if size > MAX_REPORT_BYTES:
        _err(errors, "$", "size", f"<= {MAX_REPORT_BYTES} bytes", "E_SIZE")
        return _finish(errors)
    try:
        obj = json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except _DuplicateKey:
        _err(errors, "$", "duplicate_key", "chaves únicas", "E_DUPLICATE_KEY")
        return _finish(errors)
    except _NonFinite:
        _err(errors, "$", "finite_number", "número finito", "E_NONFINITE")
        return _finish(errors)
    except (ValueError, RecursionError):
        _err(errors, "$", "json", "JSON", "E_JSON")
        return _finish(errors)
    if not isinstance(obj, dict):
        _err(errors, "$", "type", "object", "E_ROOT_TYPE")
        return _finish(errors)

    version = obj.get("report_schema_version", None)
    if "report_schema_version" in obj:
        if not isinstance(version, str):
            _err(errors, "$.report_schema_version", "type", "string", "E_TYPE")
            return _finish(errors)
        if version != CONTRACT_ID:            # unknown contract: nothing else can be validated (fail closed)
            _err(errors, "$.report_schema_version", "const", "versão de contrato suportada", "E_VERSION")
            return _finish(errors)
    if set(obj) - set(TOP_FIELDS):
        _err(errors, "$", "additional_properties", "apenas as chaves do contrato", "E_UNKNOWN_KEY")
    for key, typ in TOP_FIELDS.items():
        if key not in obj:
            _err(errors, f"$.{key}", "required", typ, "E_MISSING")
        elif not _type_ok(obj[key], typ):
            _err(errors, f"$.{key}", "type", typ, "E_TYPE")

    rec = obj.get("recommendation")
    if isinstance(rec, str):
        _string(errors, "$.recommendation", rec, NAME_MAX)

    names = []
    products = obj.get("products")
    if isinstance(products, list):
        if not PRODUCTS_ITEMS[0] <= len(products) <= PRODUCTS_ITEMS[1]:
            _err(errors, "$.products", "items", f"{PRODUCTS_ITEMS[0]}..{PRODUCTS_ITEMS[1]} itens", "E_ITEMS")
        for i, item in enumerate(products[:PRODUCTS_ITEMS[1]]):
            base = f"$.products[{i}]"
            if not isinstance(item, dict):
                _err(errors, base, "type", "object", "E_TYPE")
                continue
            if set(item) - set(PRODUCT_FIELDS):
                _err(errors, base, "additional_properties", "apenas as chaves do contrato", "E_UNKNOWN_KEY")
            for key, typ in PRODUCT_FIELDS.items():
                path = f"{base}.{key}"
                if key not in item:
                    _err(errors, path, "required", typ, "E_MISSING")
                elif not _type_ok(item[key], typ):
                    _err(errors, path, "type", typ, "E_TYPE")
                elif typ == "number":
                    v = item[key]
                    if not math.isfinite(v) or not 0 <= v <= PRICE_MAX:
                        _err(errors, path, "range", "número não negativo dentro do limite", "E_RANGE")
                elif typ == "string":
                    _string(errors, path, item[key], NAME_MAX)
            name = item.get("name")
            if isinstance(name, str):
                if name in names:
                    _err(errors, f"{base}.name", "unique", "name único", "E_DUPLICATE_ITEM")
                names.append(name)

    sources = obj.get("sources")
    if isinstance(sources, list):
        if not SOURCES_ITEMS[0] <= len(sources) <= SOURCES_ITEMS[1]:
            _err(errors, "$.sources", "items", f"{SOURCES_ITEMS[0]}..{SOURCES_ITEMS[1]} itens", "E_ITEMS")
        seen = []
        for i, s in enumerate(sources[:SOURCES_ITEMS[1]]):
            path = f"$.sources[{i}]"
            if not isinstance(s, str):
                _err(errors, path, "type", "string", "E_TYPE")
                continue
            _string(errors, path, s, URL_MAX, url=True)
            if s in seen:
                _err(errors, path, "unique", "URL único", "E_DUPLICATE_ITEM")
            seen.append(s)

    if isinstance(rec, str) and isinstance(products, list) and names and rec not in names:
        _err(errors, "$.recommendation", "reference", "name de um item de products", "E_REFERENCE")
    return _finish(errors)


def feedback(result: ValidationResult, decision: str, remaining: int) -> str:
    """Text returned to the model: decision + structural errors with fixed messages. No submitted content,
    no expected values, no judgement of correctness."""
    body = {"contract": CONTRACT_ID, "decision": decision, "schema_valid": result.schema_valid,
            "submissions_remaining": max(0, remaining)}
    if decision == "REJECTED_SCHEMA":
        body["errors"] = [{**e, "message": MESSAGES[e["code"]]} for e in result.errors]
    elif decision == "DUPLICATE_SUBMISSION":
        body["message"] = "texto idêntico a uma submissão anterior; não foi reavaliado"
    elif decision == "ALREADY_ACCEPTED":
        body["message"] = "já existe um relatório conforme; é esse o relatório final"
    else:
        body["message"] = ("relatório conforme recebido; o resultado será verificado pela RIGHTWARE a partir das "
                           "execuções registadas")
    return json.dumps(body, ensure_ascii=False, sort_keys=True)


# -- hash-chained submission records -------------------------------------------------------------------
def genesis(run_id: str) -> str:
    return hashlib.sha256(f"te-p2b-genesis:{run_id}".encode()).hexdigest()


def _record_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def chain_record(chain: list, *, kind: str, run_id: str, **fields) -> dict:
    prev = chain[-1]["record_sha256"] if chain else genesis(run_id)
    record = {"index": len(chain), "kind": kind, "run_id": run_id, "contract_id": CONTRACT_ID,
              "schema_sha256": SCHEMA_SHA256, "prev_record_sha256": prev, **fields}
    record["record_sha256"] = _record_hash(record)
    chain.append(record)
    return record


def check_chain(chain: list, receipts, submissions: list, audit_rows: list | None = None) -> dict:
    """Offline consistency: chain links/hashes, chain ↔ submit_report receipts (1:1, decision ↔ status),
    accepted record ↔ stored submission (hash), and (optionally) ↔ policy audit outcomes."""
    problems: list[str] = []
    run_ids = {r.get("run_id") for r in chain}
    if len(run_ids) > 1:
        problems.append("mixed run ids")
    prev = genesis(next(iter(run_ids))) if run_ids else None
    for i, r in enumerate(chain):
        if r.get("index") != i:
            problems.append(f"index {i}: out of order")
        if r.get("prev_record_sha256") != prev:
            problems.append(f"index {i}: broken link")
        if _record_hash(r) != r.get("record_sha256"):
            problems.append(f"index {i}: record hash mismatch")
        if r.get("contract_id") != CONTRACT_ID or r.get("schema_sha256") != SCHEMA_SHA256:
            problems.append(f"index {i}: contract mismatch")
        prev = r.get("record_sha256")
    subs = [r for r in chain if r.get("kind") == "submission"]
    kinds = [c.get("kind") for c in chain]
    if "verdict" in kinds and ("submission" in kinds[kinds.index("verdict"):] or kinds.count("verdict") > 1):
        problems.append("record after verdict")
    if set(kinds) - {"submission", "verdict"}:
        problems.append("unknown record kind")
    receipts_by_seq = {r.sequence: r for r in receipts if r.tool == "submit_report" and r.executed}
    seqs = [r.get("receipt_sequence") for r in subs]
    if len(seqs) != len(set(seqs)):
        problems.append("duplicate receipt reference in chain")
    if set(seqs) != set(receipts_by_seq):
        problems.append("chain records and executed submit_report receipts differ")
    for r in subs:
        rec = receipts_by_seq.get(r.get("receipt_sequence"))
        if rec is None:
            continue
        if rec.binding != "BOUND" or rec.call_id_status != "SUPPLIED" or rec.call_id != r.get("call_id"):
            problems.append(f"receipt {rec.sequence}: binding/call id mismatch")
        accepted = r.get("decision") == "ACCEPTED_FOR_VERIFICATION"
        if accepted != (rec.status == "OK") or (not accepted and rec.reason_code != r.get("decision")):
            problems.append(f"receipt {rec.sequence}: decision/status mismatch")
        if r.get("decision") not in DECISIONS:
            problems.append(f"receipt {rec.sequence}: unknown decision")
    accepted = [r for r in subs if r.get("decision") == "ACCEPTED_FOR_VERIFICATION"]
    if len(accepted) > 1:
        problems.append("more than one accepted submission")
    stored = [(s.get("sequence"), s.get("sha256")) for s in submissions or []]
    want = [(r["receipt_sequence"], r["report_sha256"]) for r in accepted]
    if stored != want:
        problems.append("stored submissions differ from accepted chain records")
    for s in submissions or []:
        if hashlib.sha256(str(s.get("report", "")).encode("utf-8")).hexdigest() != s.get("sha256"):
            problems.append(f"stored submission {s.get('sequence')}: content hash mismatch")
    if audit_rows is not None:
        outcomes = [a for a in audit_rows if a.get("tool") == "submit_report" and "outcome" in a]
        if len(outcomes) != len(subs):
            problems.append("policy audit outcomes differ from chain submissions")
    return {"valid": not problems, "problems": problems, "submissions": len(subs), "accepted": len(accepted)}
