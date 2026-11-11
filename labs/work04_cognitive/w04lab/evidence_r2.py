"""WORK-04 R2: bounded, sanitised evidence of the model's FIRST answer when the
single recovery continuation is used. Synthetic tasks only; the text is kept so
a human can audit a premature completion claim, never used for scoring."""
from __future__ import annotations

import hashlib
import re

MAX_CHARS = 4000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏ -‮⁠-⁤﻿]")
# Credential-shaped strings are never expected here; redact defensively anyway.
_SECRET = re.compile(r"(?i)\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|"
                     r"AKIA[0-9A-Z]{16}|xox[abpr]-[A-Za-z0-9-]{10,}|bearer\s+[A-Za-z0-9._~+/=-]{16,})")


MAX_FEEDBACK_CHARS = 6000


def bounded_text(text: str | None, max_chars: int = MAX_CHARS) -> dict:
    """Sanitised (control/zero-width removed, credential shapes redacted), size-bounded copy
    with SHA-256 of the raw text (comparable with the trace's result_sha256) and of the copy."""
    raw = text or ""
    clean = _SECRET.sub("[REDACTED-CREDENTIAL-SHAPE]", _CONTROL.sub("", raw))
    stored = clean[:max_chars]
    return {
        "text": stored,
        "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "stored_sha256": hashlib.sha256(stored.encode("utf-8")).hexdigest(),
        "raw_chars": len(raw),
        "truncated": len(clean) > max_chars,
        "redactions": len(_SECRET.findall(raw)),
    }


def first_answer_evidence(text: str | None) -> dict:
    return bounded_text(text, MAX_CHARS)
