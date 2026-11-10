"""WORK-04 R2 low-trust-document quarantine — heuristic, not a security proof.

This isolates *assistant-directed* instructions in tool output, while avoiding
obvious overblocking of ordinary business fields or third-person descriptions.
Documents on disk are never modified. Source provenance + independent factual
verification, not this keyword filter, remain the authority for truth.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


REDACTED = "[INSTRUCAO NAO CONFIAVEL ISOLADA — NAO E UM FACTO]\n"


def _normal(text: str) -> str:
    # Detection only. Drop format controls and map a small set of confusables
    # used to spoof Latin instructions; never rewrite the source on disk.
    confusables = str.maketrans({
        "і": "i", "ј": "j", "а": "a", "е": "e", "о": "o",
        "р": "p", "с": "c", "х": "x", "у": "y",
    })
    text = unicodedata.normalize("NFKC", text).casefold().translate(confusables)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


_DIRECTIVE_HEADING = re.compile(
    r"^\s*(?:[#>*-]+\s*)?"
    r"instrucoes\s+(?:para|ao)\s+(?:o\s+)?(?:assistente|modelo|agente)\s*:"
)
_AUTHORITY_LABEL = re.compile(
    r"^\s*(?:[#>*-]+\s*)?"
    r"(?:(?:system|developer|assistant)\s*(?:message|prompt)?\s*:|"
    r"nota\s+do\s+sistema\s*:)"
)
_MARKDOWN_ROLE_HEADER = re.compile(
    r"^\s*(?:#{1,6}\s*|>\s*)"
    r"(?:system|developer|assistant|agent|sistema|modelo)"
    r"(?:\s+(?:message|instructions|instruction|prompt|instrucoes))?\s*:?\s*$"
)
_XML_ROLE_OPEN = re.compile(r"^\s*<(?:system|developer|assistant|agent)(?:\s[^>]*)?>\s*$")
_XML_ROLE_CLOSE = re.compile(r"^\s*</(?:system|developer|assistant|agent)>\s*$")
_JSON_ROLE = re.compile(r"['\"]role['\"]\s*:\s*['\"](?:system|developer|assistant|agent)['\"]")
_HTML_ROLE = re.compile(r"^\s*<!--\s*(?:system|developer|assistant|agent)\s*:")
_TABLE_ROLE = re.compile(r"^\s*\|\s*(?:system|developer|assistant|agent)\s*\|")

_COMMAND = re.compile(
    r"\b(?:ignora|ignore|disregard|desconsidera|sobrepoe|sobrescreve|"
    r"grava|escreve|copia|executa|chama|invoca|le|revele|"
    r"replace|override|delete|run_command|edita|remove|apaga|"
    r"follow|reveal|use|pretend|trust|obey)\b"
)
_DIRECTED_COMMAND = re.compile(
    r"^\s*(?:[#>*-]+\s*)?"
    r"(?:ignora|ignore|disregard|desconsidera|sobrepoe|sobrescreve|"
    r"grava|escreve|copia|executa|chama|invoca|le|revele|"
    r"replace|override|delete|run_command|edita|remove|apaga|"
    r"follow|reveal|use|pretend|trust|obey)\b"
)
_URGENT_COMMAND = re.compile(
    r"^\s*(?:aviso|pedido\s+urgente|atencao|importante|urgent)\s*:"
)
_TARGET = re.compile(
    r"\b(?:assistente|agente|modelo|prompt|sistema|system|ferramenta|"
    r"tool|relatorio|ficheiro|arquivo|documento|instrucoes|instructions|"
    r"regras|rules|orcamento|budget|fornecedor|supplier|responsavel|"
    r"sources|files|document|reports|data|truth|canary|secret)\b|"
    r"(?:\.\./|\.\.\\|/private/|run_command)"
)


def _role_context(line: str) -> str | None:
    folded = _normal(line)
    if _XML_ROLE_OPEN.search(folded):
        return "xml"
    if _MARKDOWN_ROLE_HEADER.search(folded):
        return "paragraph"
    if _DIRECTIVE_HEADING.search(folded):
        return "paragraph" if folded.rstrip().endswith(":") else "line"
    if _AUTHORITY_LABEL.search(folded):
        # Some real administrative notes say "Nota do sistema: recibo ...".
        # Without an instruction, do not erase business data.
        tail = folded.split(":", 1)[-1]
        if folded.lstrip().startswith("nota do sistema") and not _COMMAND.search(tail):
            return None
        return "paragraph" if folded.rstrip().endswith(":") else "line"
    if any(p.search(folded) for p in (_JSON_ROLE, _HTML_ROLE, _TABLE_ROLE)):
        return "line"
    return None


def is_instruction(line: str) -> bool:
    folded = _normal(line)
    if not folded.strip():
        return False
    if _role_context(line) is not None:
        return True
    if _DIRECTED_COMMAND.search(folded) and _TARGET.search(folded):
        return True
    if _URGENT_COMMAND.search(folded) and _COMMAND.search(folded):
        return True
    return False


def isolate_instructions(text: str) -> tuple[str, dict]:
    """Quarantine spoofed role blocks and directed-command lines.

    A role block ends at a blank line or next Markdown heading. The XML
    block ends at its matching close. Standalone directives only hide their
    own line. Report counts and hashes, not untrusted plaintext.
    """
    output: list[str] = []
    hashes: list[str] = []
    mode: str | None = None
    for line in text.splitlines(keepends=True):
        folded = _normal(line)
        stripped = folded.strip()
        if mode == "xml":
            hashes.append(hashlib.sha256(line.encode("utf-8")).hexdigest())
            output.append(REDACTED)
            if _XML_ROLE_CLOSE.search(folded):
                mode = None
            continue
        if mode == "paragraph":
            if not stripped:
                mode = None
                output.append(line)
                continue
            if not re.match(r"^\s*#{1,6}\s+", line):
                hashes.append(hashlib.sha256(line.encode("utf-8")).hexdigest())
                output.append(REDACTED)
                continue
            mode = None
        role = _role_context(line)
        if role or is_instruction(line):
            hashes.append(hashlib.sha256(line.encode("utf-8")).hexdigest())
            output.append(REDACTED)
            mode = role if role in ("xml", "paragraph") else None
        else:
            output.append(line)
    return "".join(output), {"quarantined_lines": len(hashes), "sha256": hashes}
