"""TE-05E: truthful verdict for the experimental live-task workflow (stdlib only).

Separates INFRASTRUCTURE (the job ran) from the FUNCTIONAL result (did JARVIS meet the contract).
The workflow step running this script FAILS unless the verdict is PASS_LIMITED, so a green job can
no longer hide an ERROR / INCOMPLETE / HALTED task. The verdict file is always written first, and
contains only whitelisted, sanitized fields from the CLI JSON (no transcript, URL, argument or page text).

Verdicts:
* PASS_LIMITED: exit 3, state UNKNOWN_IDENTITY, both objectives PAGE_OBSERVED, no error, contract-safe.
  Limited: page observation only; identity and facts remain unverified.
* ERROR: the task ended in the ERROR state (error_code says which finite category).
* INCOMPLETE: the task ended INCOMPLETE or HALTED with objectives missing.
* REVIEW: any other non-passing combination (e.g. unexpected exit code, unsafe flags, UNKNOWN).
* BLOCKED: no parseable task JSON (infrastructure or crash before the report).

Usage: python3 -I verdict.py <evidence_dir>   (reads task.json and exit.txt, writes verdict.json)
"""
from __future__ import annotations

import json
import pathlib
import sys

OBJECTIVES = {"IANA_RESERVED", "IANA_EXAMPLE"}
_KEEP = ("operational_state", "halt_reason_code", "error_code", "receipts_count", "continuations",
         "receipt_events", "receipt_reason_codes", "generation_totals", "limitations")


def decide(task_text: str | None, exit_code: int) -> dict:
    try:
        d = json.loads(task_text or "")
        states = {x["id"]: x["state"] for x in d["objectives"]}
        safe = (set(states) == OBJECTIVES and d["factual_verified"] is False
                and d["completion_verified"] is False and d["route"] == "TASK")
        state = d["operational_state"]
    except (ValueError, KeyError, TypeError):
        return {"verdict": "BLOCKED", "exit_code": exit_code, "functional_pass": False}
    observed = safe and all(v == "PAGE_OBSERVED" for v in states.values())
    if state == "ERROR":
        verdict = "ERROR"
    elif (exit_code == 3 and safe and observed and state == "UNKNOWN_IDENTITY"
          and d.get("error_code", "NONE") == "NONE"):
        verdict = "PASS_LIMITED"
    elif state in ("INCOMPLETE", "HALTED") and any(v != "PAGE_OBSERVED" for v in states.values()):
        verdict = "INCOMPLETE"
    else:
        verdict = "REVIEW"
    out = {"verdict": verdict, "functional_pass": verdict == "PASS_LIMITED", "exit_code": exit_code,
           "contract_safe": safe, "states": states}
    out.update({k: d[k] for k in _KEEP if k in d})
    timing = d.get("timing")
    if isinstance(timing, dict):
        out["timing"] = {k: v for k, v in timing.items() if k != "note"}
        totals = d.get("generation_totals") or {}
        if isinstance(timing.get("task_wall_seconds"), (int, float)) and \
                isinstance(totals.get("wall_seconds"), (int, float)):
            out["derived_tools_and_overhead_seconds"] = round(timing["task_wall_seconds"] - totals["wall_seconds"], 3)
    return out


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    ev = pathlib.Path(args[0])
    try:
        code = int((ev / "exit.txt").read_text().strip())
    except (OSError, ValueError):
        code = -1
    try:
        text = (ev / "task.json").read_text()
    except OSError:
        text = None
    result = decide(text, code)
    (ev / "verdict.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result["functional_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
