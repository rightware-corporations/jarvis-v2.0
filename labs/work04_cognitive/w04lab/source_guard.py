"""WORK-04 R2: isolate assistant-directed instructions embedded in untrusted documents.

Defence in depth for the lab's read_document tool, NOT a general-purpose
prompt-injection detector. Documents on disk remain unmodified; the model gets
redacted instruction spans and an audit count. Expected to have both misses
and false positives; independent output validation remains mandatory.
No reliance on fixture seeds, canary values, project names or model responses.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    return "".join(c for c in text if not unicodedata.combining(c))


_ROLE = re.compile(
    r"^\s*(?:[#>*\-]+\s*)?"
    r"(?:instrucoes\s+(?:para|ao)\s+(?:o\s+)?(?:assistente|modelo|agente)|"
    r"nota\s+do\s+sistema\s*:|(?:system|developer|assistant|modelo|agente)\s*(?:message|prompt)?\s*:)",
)
_COMMAND = re.compile(
    r"\b(?:ignora|ignore|desconsidera|sobrepoe|sobrescreve|"
    r"grava|escreve|copia|executa|chama|invoca|le|revele|"
    r"replace|override|disregard|delete|run_command|"
    r"edita|remove|apaga)\b"
)
_TARGET = re.compile(
    r"\b(?:assistente|agente|modelo|prompt|sistema|system|"
    r"ferramenta|tool|relatorio|ficheiro|arquivo|documento|"
    r"instrucoes|regras|or[cç]amento|fornecedor|responsavel)\b|"
    r"(?:\.\./|\.\.\\|/private/|run_command)"
)
_URGENCY = re.compile(r"^\s*(?:aviso|pedido\s+urgente|atencao|importante)\s*:")


def is_instruction(line: str) -> bool:
    """Conservative role/spoof/directed-command check, without fixture literals."""
    clean = _normal(line)
    if not clean.strip():
        return False
    if _ROLE.search(clean):
        return True
    return bool(_COMMAND.search(clean) and
                (_TARGET.search(clean) or _URGENCY.search(clean)))


def isolate_instructions(text: str) -> tuple[str, dict]:
    """Replace suspect instruction lines, preserving non-instruction text.

    Fail-safe output is an explicit, non-executable quarantine marker. Audit
    exposes count and SHA-256 for blocked spans but never their raw content.
    """
    lines = text.splitlines(keepends=True)
    output, hashes = [], []
    in_block = False
    for line in lines:
        stripped = line.strip()
        direct = is_instruction(line)
        if direct:
            in_block = line.rstrip().endswith(":")
        elif not stripped:
            in_block = False
        if direct or (in_block and stripped and not line.lstrip().startswith("# ")):
            hashes.append(hashlib.sha256(line.encode("utf-8")).hexdigest())
            output.append("[INSTRUCAO NAO CONFIAVEL ISOLADA — NAO E UM FACTO]\n")
        else:
            output.append(line)
    return "".join(output), {"quarantined_lines": len(hashes), "sha256": hashes}
