"""WORK-04 R2 low-trust-document instruction quarantine, deterministic.

This is a DEFENCE-IN-DEPTH heuristic, not semantic proof of security.
Trust boundaries and final report evaluators remain mandatory. Operates only
on the text returned by the lab's read_document tool; source bytes untouched.
Avoids historical fixture-specific names, seeds, values and commands.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


REDACTED = "[INSTRUCAO NAO CONFIAVEL ISOLADA — NAO E UM FACTO]\n"


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    return "".join(c for c in text if not unicodedata.combining(c))


# These contexts claim authority from outside the user's task or inject new
# instructions via a tool response, not factual source material.
_ROLE_LINE = re.compile(
    r"^\s*(?:[#>*-]+\s*)?"
    r"(?:instrucoes\s+(?:para|ao)\s+(?:o\s+)?(?:assistente|modelo|agente)|"
    r"nota\s+do\s+sistema\s*:|"
    r"(?:system|developer|assistant|modelo|agente)\s*(?:message|prompt)?\s*:)"
)
_MARKDOWN_ROLE_HEADER = re.compile(
    r"^\s*(?:#{1,6}\s*|>\s*)"
    r"(?:system|developer|assistant|agent|sistema|modelo)"
    r"(?:\s+(?:message|instructions|instruction|prompt|instrucoes))?\s*:?\s*$"
)
_XML_ROLE_OPEN = re.compile(
    r"^\s*<(?:system|developer|assistant|agent)(?:\s[^>]*)?>\s*$"
)
_XML_ROLE_CLOSE = re.compile(
    r"^\s*</(?:system|developer|assistant|agent)>\s*$"
)
_JSON_ROLE = re.compile(
    r"['\"]role['\"]\s*:\s*['\"](?:system|developer|assistant|agent)['\"]"
)
_HTML_ROLE = re.compile(
    r"^\s*<!--\s*(?:system|developer|assistant|agent)\s*:"
)
_TABLE_ROLE = re.compile(
    r"^\s*\|\s*(?:system|developer|assistant|agent|modelo)\s*\|"
)
_COMMAND = re.compile(
    r"\b(?:ignora|ignore|disregard|desconsidera|sobrepoe|sobrescreve|"
    r"grava|escreve|copia|executa|chama|invoca|le|revele|"
    r"replace|override|delete|run_command|edita|remove|apaga|"
    r"follow|reveal|use|pretend|trust|obey)\b"
)
_TARGET = re.compile(
    r"\b(?:assistente|agente|modelo|prompt|sistema|system|"
    r"ferramenta|tool|relatorio|ficheiro|arquivo|documento|"
    r"instrucoes|instructions|regras|rules|orcamento|budget|"
    r"fornecedor|supplier|responsavel|sources|files|document|"
    r"reports|data|truth|canary|secret)\b|"
    r"(?:\.\./|\.\.\\|/private/|run_command)"
)
_URGENCY = re.compile(r"^\s*(?:aviso|pedido\s+urgente|atencao|importante|urgent)\s*:")


def _role_context(line: str) -> str | None:
    folded = _normal(line)
    if _XML_ROLE_OPEN.search(folded):
        return "xml"
    if _MARKDOWN_ROLE_HEADER.search(folded):
        return "paragraph"
    if _ROLE_LINE.search(folded):
        return "paragraph" if folded.rstrip().endswith(":") else "line"
    if any(pattern.search(folded) for pattern in (_JSON_ROLE, _HTML_ROLE, _TABLE_ROLE)):
        return "line"
    return None


def is_instruction(line: str) -> bool:
    folded = _normal(line)
    if not folded.strip():
        return False
    if _role_context(line):
        return True
    return bool(_COMMAND.search(folded) and
                (_TARGET.search(folded) or _URGENCY.search(folded)))


def isolate_instructions(text: str) -> tuple[str, dict]:
    """Quarantine synthetic role blocks and directed commands.

    A contiguous role block ends at a blank line; an XML role ends at the
    matching closing tag. A generic command only hides its own line.
    SHA-256 in the audit is of the original line (no raw injected content).
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
            # A new Markdown heading starts a fresh section, not a previous
            # spoofed role block; it is scanned again as an independent line.
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
