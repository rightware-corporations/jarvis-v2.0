"""WORK-04 R2: evidence-based failure taxonomy.

ENGINE means the model serving API returned an error, *not* that root cause
has been established. This module is classification only, never a retry.
"""
from __future__ import annotations

import re


def classify_failure(*, error: BaseException | None, timed_out: bool,
                     security_ok: bool, trace: list[dict]) -> str | None:
    if timed_out:
        return "AMBIENTE"
    if error:
        detail = f"{type(error).__name__}: {error}"
        if re.search(r"(?:ollama\s+returned|http(?:\s+status)?|status(?:\s+code)?)\s*[:=]?\s*5\d{2}\b",
                     detail, re.IGNORECASE):
            return "ENGINE"
        if any(name in detail for name in ("Connection", "Timeout", "TimedOut")):
            return "AMBIENTE"
        return "HARNESS"
    if not security_ok:
        return "PERMISSÃO"
    if any(not t.get("success") and
           "TemporaryReadError" not in t.get("result_preview", "") and
           not t.get("result_preview", "").startswith("Recusado")
           for t in trace):
        return "FERRAMENTA"
    return "MODELO"
