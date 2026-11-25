"""Small text helpers shared by the research modules (no I/O)."""
from __future__ import annotations

import re
import unicodedata

# Portuguese/English numbers: "1 240", "1.240", "3 629,39", "63,91", "63.91", "12,2", "2026".
NUM = re.compile(r"(?<![\w])(\d{1,3}(?:[  .]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![\d])")
WORD = re.compile(r"[a-z0-9]+")
STOP = set("""
a o os as um uma uns umas de do da dos das no na nos nas em por para com sem sobre entre ate desde
que qual quais quem como onde quando porque porquê se ser foi era sao esta este estes estas isso isto
e ou mas mais menos muito pouco tambem ja ainda nao sim seu sua seus suas ao aos pela pelo pelas pelos
segundo fonte fontes dados valor valores cerca aproximadamente sendo pode podem deve devem tem teve
the of and or to in on for with from by is are was were be this that these those at as an it its
""".split())


def fold(text: str) -> str:
    """Lower-case, accents removed (comparison only)."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def number_value(token: str) -> float | None:
    s = token.replace(" ", "").replace(" ", "")
    try:
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
            return float(s.replace(".", "").replace(",", "."))
        return float(s.replace(",", "."))
    except ValueError:
        return None


def decimals(token: str) -> int:
    m = re.search(r"[.,](\d+)$", token.replace(" ", ""))
    if not m or re.fullmatch(r"\d{1,3}(?:[.]\d{3})+", token.replace(" ", "")):
        return 0
    return len(m.group(1))


SCALE = re.compile(r"\s*(mil\s+milh[oõ]es|milh[aã]o|milh[oõ]es|mil(?!h)|bili[aã]o|bili[oõ]es)\b", re.I)
SCALES = {"mil": 1e3, "milhao": 1e6, "milhoes": 1e6, "mil milhoes": 1e9, "biliao": 1e12, "bilioes": 1e12}


def numbers(text: str) -> list[tuple[str, float]]:
    """Numbers with their value; a following "mil"/"milhões"/"mil milhões" scales the value ("950 mil" = 950 000)."""
    out = []
    for m in NUM.finditer(text):
        tok = m.group(1)
        v = number_value(tok)
        if v is None:
            continue
        sc = SCALE.match(text, m.end())
        if sc:
            v *= SCALES.get(" ".join(fold(sc.group(1)).split()), 1)
        out.append((tok, v))
    return out


def content_words(text: str) -> list[str]:
    seen, out = set(), []
    codes = [c.lower() for c in re.findall(r"\b[A-Z]{3}\b", text)]      # USD, MZN, EUR, PIB, INE…
    for w in codes + WORD.findall(fold(text)):
        if len(w) == 3 and w in codes and w not in seen:
            seen.add(w)
            out.append(w)
            continue
        if len(w) >= 4 and not w.isdigit() and w not in STOP and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def stem(word: str) -> str:
    return word[:6]


def sentences(text: str) -> list[str]:
    """Split on sentence ends and line breaks; never inside decimals (63,91 / 3.629)."""
    out = []
    for line in text.split("\n"):
        for s in re.split(r"(?<=[.!?;])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9(\[\-•*\"«])", line.strip()):
            s = s.strip(" -•*\t")
            if s:
                out.append(s)
    return out
