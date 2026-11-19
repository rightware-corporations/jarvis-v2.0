"""JRV-TE-P2D research report contract ``te-p2d.research.v1`` (generic, versioned; labs only).

A STRUCTURAL pre-filter for research answers delivered through the receipted ``submit_report``. It names
fields, types and cross-references only — never a question's answer, value or source. Conformance means
"well-formed", never "true": source/observation/hash checks and the semantic rubric belong to the
independent verifier (``research_verify``).

Fields:
* ``report_schema_version`` = "te-p2d.research.v1"; ``question_id`` (as given in the task);
* ``answer`` (1..1500 chars) and ``abstained`` (boolean: true when the evidence is insufficient);
* ``claims`` (0..8; at least 1 unless abstained): ``claim_id`` (c1..c8, unique), ``text`` (1..400),
  ``source_url`` (must be one of ``sources``), ``observation`` (integer id shown by RIGHTWARE with the page
  that supports the claim), ``quote`` (1..300 chars copied verbatim from that page);
* ``sources`` (0..10 distinct https URLs; at least 1 unless abstained);
* ``limitations`` (0..800 chars; uncertainty, gaps).
Strict like ``te-p2b.report.v1``: unknown/missing keys, wrong types (no coercion), duplicate keys, NaN,
invalid UTF-8, control characters (except in ``answer``/``limitations``/``text``/``quote`` newlines are also
refused) and > 12000 UTF-8 bytes are rejected with fixed-message structural feedback (no echo).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re

CONTRACT_ID = "te-p2d.research.v1"
MAX_REPORT_BYTES = 12000
MAX_SUBMISSIONS = 3
MAX_ERRORS_RETURNED = 20
LIMITS = {"question_id": 32, "answer": 1500, "text": 400, "quote": 300, "url": 300, "limitations": 800}
CLAIMS_ITEMS, SOURCES_ITEMS = (0, 8), (0, 10)
TOP_FIELDS = {"report_schema_version": "string", "question_id": "string", "answer": "string",
              "abstained": "boolean", "claims": "array", "sources": "array", "limitations": "string"}
CLAIM_FIELDS = {"claim_id": "string", "text": "string", "source_url": "string", "observation": "integer",
                "quote": "string"}
SCHEMA = {"contract": CONTRACT_ID, "top": TOP_FIELDS, "claim": CLAIM_FIELDS, "limits": LIMITS,
          "claims_items": CLAIMS_ITEMS, "sources_items": SOURCES_ITEMS, "max_report_bytes_utf8": MAX_REPORT_BYTES,
          "max_submissions": MAX_SUBMISSIONS, "rules": ["claims>=1 and sources>=1 unless abstained",
                                                       "claim.source_url in sources", "claim_id unique c1..c8",
                                                       "sources unique https URLs", "question_id ^[A-Z0-9-]+$"]}
SCHEMA_SHA256 = hashlib.sha256(json.dumps(SCHEMA, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

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
    "E_REFERENCE": "referência cruzada inválida (source_url tem de estar em sources)",
    "E_REQUIRED_EVIDENCE": "sem abstenção, são obrigatórias pelo menos uma afirmação e uma fonte",
}
DECISIONS = ("ACCEPTED_FOR_VERIFICATION", "REJECTED_SCHEMA", "DUPLICATE_SUBMISSION", "ALREADY_ACCEPTED")

EXAMPLE = ('{"report_schema_version":"te-p2d.research.v1","question_id":"Q-EXEMPLO-0","answer":"Resposta curta e '
           'fundamentada.","abstained":false,"claims":[{"claim_id":"c1","text":"Afirmação verificável.","source_url":'
           '"https://exemplo.invalid/pagina","observation":41,"quote":"excerto copiado tal e qual da página"}],'
           '"sources":["https://exemplo.invalid/pagina"],"limitations":"O que não foi possível confirmar."}')

TOOL_DESCRIPTION = (
    "Entrega à RIGHTWARE o resultado da investigação (contrato te-p2d.research.v1). O argumento report é o TEXTO de "
    "um único objecto JSON com EXACTAMENTE estas chaves (chaves não previstas são recusadas; não há conversão de "
    "tipos): report_schema_version: \"te-p2d.research.v1\"; question_id: o identificador da pergunta recebida; "
    "answer: resposta fundamentada (1 a 1500 caracteres); abstained: boolean, true se a evidência não chega para "
    "responder; claims: lista de 0 a 8 afirmações verificáveis, cada uma com EXACTAMENTE claim_id (c1 a c8, sem "
    "repetidos), text (1 a 400), source_url (um dos URLs de sources), observation (o número inteiro da observação "
    "RIGHTWARE que acompanhou a página lida) e quote (1 a 300 caracteres copiados tal e qual dessa página); "
    "sources: lista de 0 a 10 URLs https distintos que leste; limitations: limitações e incertezas (0 a 800). Sem "
    "abstenção são obrigatórias pelo menos uma afirmação e uma fonte. Limite 12000 bytes UTF-8. Exemplo APENAS "
    "estrutural, com valores fictícios: " + EXAMPLE + ". No máximo 3 submissões; um relatório fora do contrato é "
    "recusado com erros de formato e pode ser corrigido; um texto idêntico é recusado; o primeiro relatório conforme "
    "é o final. Estar conforme não significa estar correcto: a RIGHTWARE verifica fontes, observações e "
    "excertos de forma independente.")


@dataclasses.dataclass(frozen=True)
class ValidationResult:
    schema_valid: bool
    errors: tuple
    contract_id: str = CONTRACT_ID
    schema_sha256: str = SCHEMA_SHA256


class _Dup(Exception):
    pass


class _NonFinite(Exception):
    pass


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise _Dup()
        out[k] = v
    return out


def _nonfinite(_):
    raise _NonFinite()


def _type_ok(v, t):
    return {"string": isinstance(v, str), "boolean": isinstance(v, bool), "array": isinstance(v, list),
            "integer": isinstance(v, int) and not isinstance(v, bool), "object": isinstance(v, dict)}[t]


_URL = re.compile(r"https://[^\s/?#]+[^\s]*\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_QID = re.compile(r"[A-Z0-9-]+\Z")
_CID = re.compile(r"c[1-8]\Z")


def _err(errors, path, rule, expected, code):
    errors.append({"path": path, "rule": rule, "expected": expected, "code": code})


def _string(errors, path, value, max_len, min_len=1, url=False):
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return _err(errors, path, "encoding", "UTF-8", "E_ENCODING")
    if not min_len <= len(value) <= max_len:
        return _err(errors, path, "length", f"{min_len}..{max_len} caracteres", "E_LENGTH")
    if _CONTROL.search(value):
        return _err(errors, path, "characters", "sem caracteres de controlo", "E_CHARS")
    if url and not _URL.match(value):
        _err(errors, path, "format", "https URL", "E_FORMAT")


def _finish(errors):
    unique = sorted({tuple(sorted(e.items())) for e in errors})
    out = tuple(dict(e) for e in unique)[:MAX_ERRORS_RETURNED]
    return ValidationResult(not out, out)


def validate_report(text) -> ValidationResult:
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
    except _Dup:
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
    if "report_schema_version" in obj:
        v = obj["report_schema_version"]
        if not isinstance(v, str):
            _err(errors, "$.report_schema_version", "type", "string", "E_TYPE")
            return _finish(errors)
        if v != CONTRACT_ID:
            _err(errors, "$.report_schema_version", "const", "versão de contrato suportada", "E_VERSION")
            return _finish(errors)
    if set(obj) - set(TOP_FIELDS):
        _err(errors, "$", "additional_properties", "apenas as chaves do contrato", "E_UNKNOWN_KEY")
    for key, t in TOP_FIELDS.items():
        if key not in obj:
            _err(errors, f"$.{key}", "required", t, "E_MISSING")
        elif not _type_ok(obj[key], t):
            _err(errors, f"$.{key}", "type", t, "E_TYPE")
    qid = obj.get("question_id")
    if isinstance(qid, str):
        _string(errors, "$.question_id", qid, LIMITS["question_id"])
        if qid and not _QID.match(qid):
            _err(errors, "$.question_id", "format", "[A-Z0-9-]", "E_FORMAT")
    for key in ("answer", "limitations"):
        if isinstance(obj.get(key), str):
            _string(errors, f"$.{key}", obj[key], LIMITS[key], min_len=1 if key == "answer" else 0)
    sources = obj.get("sources")
    seen = []
    if isinstance(sources, list):
        if not SOURCES_ITEMS[0] <= len(sources) <= SOURCES_ITEMS[1]:
            _err(errors, "$.sources", "items", f"{SOURCES_ITEMS[0]}..{SOURCES_ITEMS[1]} itens", "E_ITEMS")
        for i, s in enumerate(sources[:SOURCES_ITEMS[1]]):
            if not isinstance(s, str):
                _err(errors, f"$.sources[{i}]", "type", "string", "E_TYPE")
                continue
            _string(errors, f"$.sources[{i}]", s, LIMITS["url"], url=True)
            if s in seen:
                _err(errors, f"$.sources[{i}]", "unique", "URL único", "E_DUPLICATE_ITEM")
            seen.append(s)
    claims = obj.get("claims")
    if isinstance(claims, list):
        if not CLAIMS_ITEMS[0] <= len(claims) <= CLAIMS_ITEMS[1]:
            _err(errors, "$.claims", "items", f"{CLAIMS_ITEMS[0]}..{CLAIMS_ITEMS[1]} itens", "E_ITEMS")
        ids = []
        for i, c in enumerate(claims[:CLAIMS_ITEMS[1]]):
            base = f"$.claims[{i}]"
            if not isinstance(c, dict):
                _err(errors, base, "type", "object", "E_TYPE")
                continue
            if set(c) - set(CLAIM_FIELDS):
                _err(errors, base, "additional_properties", "apenas as chaves do contrato", "E_UNKNOWN_KEY")
            for key, t in CLAIM_FIELDS.items():
                path = f"{base}.{key}"
                if key not in c:
                    _err(errors, path, "required", t, "E_MISSING")
                elif not _type_ok(c[key], t):
                    _err(errors, path, "type", t, "E_TYPE")
                elif key == "observation":
                    if not 1 <= c[key] <= 100000:
                        _err(errors, path, "range", "inteiro positivo", "E_RANGE")
                elif key == "claim_id":
                    if not _CID.match(c[key]):
                        _err(errors, path, "format", "c1..c8", "E_FORMAT")
                    elif c[key] in ids:
                        _err(errors, path, "unique", "claim_id único", "E_DUPLICATE_ITEM")
                    ids.append(c[key])
                elif key == "source_url":
                    _string(errors, path, c[key], LIMITS["url"], url=True)
                    if isinstance(sources, list) and c[key] not in sources:
                        _err(errors, path, "reference", "um URL de sources", "E_REFERENCE")
                else:
                    _string(errors, path, c[key], LIMITS[key])
    if obj.get("abstained") is False and isinstance(claims, list) and isinstance(sources, list) \
            and (not claims or not sources):
        _err(errors, "$", "required_evidence", "afirmações e fontes", "E_REQUIRED_EVIDENCE")
    return _finish(errors)


def feedback(result: ValidationResult, decision: str, remaining: int) -> str:
    body = {"contract": CONTRACT_ID, "decision": decision, "schema_valid": result.schema_valid,
            "submissions_remaining": max(0, remaining)}
    if decision == "REJECTED_SCHEMA":
        body["errors"] = [{**e, "message": MESSAGES[e["code"]]} for e in result.errors]
    elif decision == "DUPLICATE_SUBMISSION":
        body["message"] = "texto idêntico a uma submissão anterior; não foi reavaliado"
    elif decision == "ALREADY_ACCEPTED":
        body["message"] = "já existe um relatório conforme; é esse o relatório final"
    else:
        body["message"] = "relatório conforme recebido; fontes, observações e excertos serão verificados pela RIGHTWARE"
    return json.dumps(body, ensure_ascii=False, sort_keys=True)


# -- hash-chained submission records (same construction as te-p2b.report.v1, own contract id) ----------
def genesis(run_id: str) -> str:
    return hashlib.sha256(f"te-p2d-genesis:{run_id}".encode()).hexdigest()


def _record_hash(record: dict) -> str:
    return hashlib.sha256(json.dumps({k: v for k, v in record.items() if k != "record_sha256"}, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def chain_record(chain: list, *, kind: str, run_id: str, **fields) -> dict:
    prev = chain[-1]["record_sha256"] if chain else genesis(run_id)
    record = {"index": len(chain), "kind": kind, "run_id": run_id, "contract_id": CONTRACT_ID,
              "schema_sha256": SCHEMA_SHA256, "prev_record_sha256": prev, **fields}
    record["record_sha256"] = _record_hash(record)
    chain.append(record)
    return record


def check_chain(chain: list, receipts, submissions: list, audit_rows: list | None = None) -> dict:
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
    kinds = [c.get("kind") for c in chain]
    if "verdict" in kinds and ("submission" in kinds[kinds.index("verdict"):] or kinds.count("verdict") > 1):
        problems.append("record after verdict")
    subs = [r for r in chain if r.get("kind") == "submission"]
    by_seq = {r.sequence: r for r in receipts if r.tool == "submit_report" and r.executed}
    seqs = [r.get("receipt_sequence") for r in subs]
    if len(seqs) != len(set(seqs)) or set(seqs) != set(by_seq):
        problems.append("chain records and executed submit_report receipts differ")
    for r in subs:
        rec = by_seq.get(r.get("receipt_sequence"))
        if rec is None:
            continue
        accepted = r.get("decision") == "ACCEPTED_FOR_VERIFICATION"
        if rec.binding != "BOUND" or rec.call_id != r.get("call_id") or accepted != (rec.status == "OK") \
                or (not accepted and rec.reason_code != r.get("decision")):
            problems.append(f"receipt {rec.sequence}: binding/decision mismatch")
    accepted = [r for r in subs if r.get("decision") == "ACCEPTED_FOR_VERIFICATION"]
    if len(accepted) > 1:
        problems.append("more than one accepted submission")
    if [(s.get("sequence"), s.get("sha256")) for s in submissions or []] != \
            [(r["receipt_sequence"], r["report_sha256"]) for r in accepted]:
        problems.append("stored submissions differ from accepted chain records")
    for s in submissions or []:
        if hashlib.sha256(str(s.get("report", "")).encode("utf-8")).hexdigest() != s.get("sha256"):
            problems.append("stored submission content hash mismatch")
    if audit_rows is not None:
        if len([a for a in audit_rows if a.get("tool") == "submit_report" and "outcome" in a]) != len(subs):
            problems.append("policy audit outcomes differ from chain submissions")
    return {"valid": not problems, "problems": problems, "submissions": len(subs), "accepted": len(accepted)}
