"""WEB-01 W3.2-A: structure-preserving evidence extraction from the EXACT bytes received (generic HTML; no site- or
topic-specific rules).

A document becomes a list of blocks — ``heading``, ``paragraph``, ``list``, ``kv`` (table row with a header cell and
a value: infoboxes, fact tables) and ``row`` (other table rows) — each with the document ENTITY (title), the SECTION
path where it sits and its text. Integrity: every block's text, normalised to lower-case alphanumerics, is a
substring of the normalised visible text of the same bytes (``in_document``), so a block can always be traced back to
what was actually received. Scripts, styles, templates and other hidden content are skipped (same rule as
``rightware.agent.web.html_to_text``)."""
from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "template", "svg", "head", "iframe", "object", "math"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCK_TEXT = {"p", "li", "dd", "dt", "caption", "blockquote", "figcaption", "pre"}
MAX_BLOCK = 600


def norm(text: str) -> str:
    """Lower-case alphanumerics only (accents kept): robust to markup/whitespace/punctuation differences."""
    return "".join(c for c in unicodedata.normalize("NFC", text.lower()) if c.isalnum())


class _Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self.title = ""
        self.section: list[str] = []
        self.skip = 0
        self.in_title = False
        self.buf: list[str] | None = None        # current text block
        self.kind = ""
        self.heading_level = 0
        self.row: list[tuple[bool, str]] | None = None   # (is_header, text) cells of the current <tr>
        self.cell: list[str] | None = None
        self.cell_header = False
        self.depth_text = 0

    # -- helpers
    def _emit(self, kind: str, text: str) -> None:
        text = " ".join(text.split())
        if len(text) >= 3:
            self.blocks.append({"kind": kind, "section": " › ".join(self.section[-2:]), "text": text[:MAX_BLOCK]})

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = True
        if tag == "br" and self.cell is not None:
            self.cell.append(" ")
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell, self.cell_header = [], tag == "th"
        elif tag in HEADINGS:
            self.buf, self.kind, self.heading_level = [], "heading", int(tag[1])
        elif tag in BLOCK_TEXT and self.cell is None and self.buf is None:
            self.buf, self.kind = [], "list" if tag in ("li", "dd", "dt") else "paragraph"

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = False
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append((self.cell_header, " ".join("".join(self.cell).split())))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            cells = [(h, t) for h, t in self.row if t]
            if len(cells) == 2 and cells[0][0] and not cells[1][0]:
                self._emit("kv", f"{cells[0][1]}: {cells[1][1]}")
            elif cells:
                self._emit("row", " | ".join(t for _, t in cells))
            self.row = None
        elif tag in HEADINGS and self.buf is not None and self.kind == "heading":
            text = " ".join("".join(self.buf).split())
            if text:
                self.section = self.section[: max(0, self.heading_level - 2)] + [text]
                self._emit("heading", text)
            self.buf = None
        elif tag in BLOCK_TEXT and self.buf is not None and self.kind != "heading" and self.cell is None:
            self._emit(self.kind, "".join(self.buf))
            self.buf = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title += data
        if self.cell is not None:
            self.cell.append(data)
        elif self.buf is not None:
            self.buf.append(data)


SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ«\"(])")


def blocks(raw: bytes, url: str = "") -> tuple[str, list[dict]]:
    """(entity, blocks). Long paragraphs are split into sentence windows (≤ ~400 chars) so evidence stays focused."""
    p = _Blocks()
    p.feed(raw.decode("utf-8", errors="replace"))
    from urllib.parse import unquote
    first_heading = next((b["text"] for b in p.blocks if b["kind"] == "heading"), "")
    entity = (" ".join(p.title.split()).split(" – ")[0].split(" — ")[0]
              or unquote(url.rsplit("/", 1)[-1].split("?")[0]).replace("_", " ") or first_heading)
    out = []
    for b in p.blocks:
        if b["kind"] == "paragraph" and len(b["text"]) > 400:
            window = ""
            for s in SENT.split(b["text"]):
                if window and len(window) + len(s) > 400:
                    out.append({**b, "text": window.strip()})
                    window = ""
                window += " " + s
            if window.strip():
                out.append({**b, "text": window.strip()})
        else:
            out.append(b)
    return entity, out


def in_document(text: str, raw: bytes) -> bool:
    from rightware.agent.web import html_to_text
    t = norm(text)
    return bool(t) and t in norm(html_to_text(raw.decode("utf-8", errors="replace")))
