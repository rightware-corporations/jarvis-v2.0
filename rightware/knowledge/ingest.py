"""Validation and extraction of uploaded documents (PDF with extractable text, TXT, CSV). Nothing is executed; the
original file name is only a sanitised display label (never a path)."""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import re
import unicodedata

from rightware.research import documents as D

MAX_BYTES = {"pdf": 5_000_000, "txt": 2_000_000, "csv": 2_000_000}
MAX_SEGMENTS = 2000
SEG_CHARS = 1200
TXT_LINES = 40
CSV_ROWS = 25
EXT = {".pdf": "pdf", ".txt": "txt", ".csv": "csv"}


class IngestError(ValueError):
    """The upload was refused (reason is safe to show)."""


@dataclasses.dataclass
class Segment:
    seq: int
    locator: str          # "página 3", "linhas 41–80", "linhas 2–26 (cabeçalho + registos)"
    text: str


@dataclasses.dataclass
class Extracted:
    name: str
    kind: str
    sha256: str
    size: int
    units: int            # pages (PDF) or lines (TXT/CSV)
    segments: list[Segment]


def safe_name(name: str) -> str:
    """Display label only: basename, no control/odd characters, bounded. Never used to build a path."""
    base = re.split(r"[\\/]", str(name or ""))[-1]
    base = unicodedata.normalize("NFC", base)
    base = "".join(c for c in base if c.isprintable() and c not in '<>:"|?*\x00')
    base = re.sub(r"\s+", " ", base).strip(" .")
    return base[:120] or "documento"


def _decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise IngestError("o ficheiro contém dados binários; não é texto")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise IngestError("codificação de texto não reconhecida")
    ctrl = sum(1 for c in text if unicodedata.category(c) == "Cc" and c not in "\n\r\t\f")
    if text and ctrl / len(text) > 0.01:
        raise IngestError("o ficheiro contém demasiados caracteres de controlo; não é texto")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def detect(name: str, data: bytes) -> str:
    """Real format from the content, which must agree with the extension (no PDF disguised as .txt, etc.)."""
    ext = "." + safe_name(name).rsplit(".", 1)[-1].lower() if "." in safe_name(name) else ""
    kind = EXT.get(ext)
    if kind is None:
        raise IngestError("formato não suportado nesta versão (aceites: PDF, TXT, CSV)")
    is_pdf = data[:5] == b"%PDF-"
    if kind == "pdf" and not is_pdf:
        raise IngestError("a extensão diz PDF mas o conteúdo não é PDF")
    if kind != "pdf" and (is_pdf or data[:4] in (b"PK\x03\x04", b"\x7fELF") or data[:2] == b"MZ"):
        raise IngestError("o conteúdo não corresponde à extensão (ficheiro binário)")
    if len(data) == 0:
        raise IngestError("ficheiro vazio")
    if len(data) > MAX_BYTES[kind]:
        raise IngestError(f"ficheiro acima do limite ({MAX_BYTES[kind] // 1_000_000} MB para {kind.upper()})")
    return kind


def _split_long(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= SEG_CHARS:
        return [text] if text else []
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        while len(para) > SEG_CHARS:
            cut = para.rfind(" ", 0, SEG_CHARS)
            cut = cut if cut > SEG_CHARS // 2 else SEG_CHARS
            parts.append((cur + "\n" + para[:cut]).strip() if cur else para[:cut])
            cur, para = "", para[cut:].strip()
        if len(cur) + len(para) + 2 > SEG_CHARS and cur:
            parts.append(cur.strip())
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur.strip():
        parts.append(cur.strip())
    return parts


def extract(name: str, data: bytes, pdf_pages=D.pdf_pages) -> Extracted:
    kind = detect(name, data)
    sha = hashlib.sha256(data).hexdigest()
    segs: list[Segment] = []
    if kind == "pdf":
        try:
            pages = pdf_pages(data)
        except D.DocumentError as exc:
            raise IngestError(str(exc)) from None
        if not any(p.strip() for p in pages):
            raise IngestError("o PDF não tem texto extraível (provavelmente digitalizado; OCR fica para depois)")
        for i, page in enumerate(pages, 1):
            clean = "\n".join(re.sub(r"[ \t]{2,}", "  ", l).rstrip() for l in page.split("\n"))
            pieces = _split_long(clean)
            for j, piece in enumerate(pieces):
                loc = f"página {i}" + (f" (parte {j + 1})" if len(pieces) > 1 else "")
                segs.append(Segment(len(segs), loc, piece))
        units = len(pages)
    elif kind == "txt":
        lines = _decode_text(data).split("\n")
        for start in range(0, len(lines), TXT_LINES):
            block = "\n".join(lines[start:start + TXT_LINES])
            for piece in _split_long(block):
                segs.append(Segment(len(segs), f"linhas {start + 1}–{min(start + TXT_LINES, len(lines))}", piece))
        units = len(lines)
    else:
        text = _decode_text(data)
        first = text.split("\n", 1)[0]
        delim = max(",;\t", key=first.count) if any(d in first for d in ",;\t") else ","
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
        if not rows:
            raise IngestError("CSV vazio")
        header, body = rows[0], rows[1:]
        hdr = " | ".join(h.strip() for h in header)
        for start in range(0, max(1, len(body)), CSV_ROWS):
            chunk = body[start:start + CSV_ROWS]
            lines = [f"[linha {start + k + 2}] " + " | ".join(c.strip() for c in r) for k, r in enumerate(chunk)]
            segs.append(Segment(len(segs), f"linhas {start + 2}–{start + 1 + max(1, len(chunk))}",
                                f"Colunas: {hdr}\n" + "\n".join(lines)))
        units = len(rows)
    segs = [s for s in segs if s.text.strip()]
    if not segs:
        raise IngestError("o documento não tem texto")
    if len(segs) > MAX_SEGMENTS:
        raise IngestError("documento demasiado longo para esta versão")
    return Extracted(safe_name(name), kind, sha, len(data), units, segs)
