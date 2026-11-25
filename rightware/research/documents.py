"""PDF → text on the host, bounded. The pinned OpenJarvis ``PDFExtractTool`` reads LOCAL files with ``pdfplumber``
(not installed); this reuses its pattern (page limit, truncation, sensitive data as untrusted) with the poppler
``pdftotext`` binary already present on the host. Fixed binary path and arguments, no shell, private temp directory,
time limit, output cap. The document's bytes come only from the audited fetcher."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

PDFTOTEXT = "/usr/bin/pdftotext"
MAX_PDF_BYTES = 5_000_000
MAX_PAGES = 20
MAX_TEXT = 20_000
TIMEOUT_S = 20


class DocumentError(ValueError):
    pass


def available() -> bool:
    return os.path.isfile(PDFTOTEXT) and os.access(PDFTOTEXT, os.X_OK)


def pdf_to_text(data: bytes, max_pages: int = MAX_PAGES) -> tuple[str, bool]:
    """Returns (text, truncated). Raises DocumentError on anything unexpected (fail closed)."""
    if not isinstance(data, (bytes, bytearray)) or not data.startswith(b"%PDF-"):
        raise DocumentError("o conteúdo não é um PDF")
    if len(data) > MAX_PDF_BYTES:
        raise DocumentError("PDF acima do limite de tamanho")
    if not available():
        raise DocumentError("conversor de PDF indisponível neste anfitrião")
    work = tempfile.mkdtemp(prefix="rw-pdf-")
    try:
        src = os.path.join(work, "doc.pdf")
        with open(src, "wb") as fh:
            fh.write(data)
        proc = subprocess.run([PDFTOTEXT, "-f", "1", "-l", str(int(max_pages)), "-enc", "UTF-8", "-nopgbrk", "-q",
                               src, "-"], capture_output=True, timeout=TIMEOUT_S, cwd=work, stdin=subprocess.DEVNULL,
                              env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, check=False)
    except subprocess.TimeoutExpired:
        raise DocumentError("a conversão do PDF excedeu o tempo limite") from None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if proc.returncode != 0:
        raise DocumentError("o PDF não pôde ser convertido")
    text = proc.stdout.decode("utf-8", errors="replace")
    truncated = len(text) > MAX_TEXT
    return text[:MAX_TEXT], truncated
