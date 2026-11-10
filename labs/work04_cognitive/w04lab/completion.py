"""WORK-04 R2: fail-closed task completion independent of the model's prose.

Only the persisted final artifact, successful tool trace and independent
evaluators can establish completion. Never infer success from a final answer,
the mere presence of a report, or a verification for an older version.
Pure Python / no model dependencies, for offline regression tests.
"""
from __future__ import annotations


def evaluate_completion(
    trace: list[dict], *, final_name: str | None, report: str,
    v2_result: str, oracle_result: str, expected_name: str | None = None,
) -> dict:
    """Return a structured, auditable verdict for the *final* report version.

    A verify call succeeds only if its tool execution succeeded and its result
    begins with the exact verifier protocol line "Verificação: PASS".
    For the final artifact we require a verification AFTER its successful write.
    A later failed verification of the same file supersedes an earlier PASS.
    This does not replace the independent V2/ORACLE recheck.
    """
    written_at = [
        i for i, call in enumerate(trace)
        if call.get("tool") == "write_report"
        and call.get("success") is True
        and call.get("args", {}).get("name") == final_name
    ] if final_name else []

    persisted = bool(final_name and report and written_at)
    verified = [
        call for i, call in enumerate(trace)
        if written_at and i > written_at[-1]
        and call.get("tool") == "verify_report"
        and call.get("args", {}).get("name") == final_name
    ]
    last = verified[-1] if verified else None
    tool_verification_pass = bool(
        last and last.get("success") is True
        and str(last.get("result_preview", "")).strip().startswith("Verificação: PASS")
    )
    evaluators_pass = v2_result == "PASS" and oracle_result == "PASS"

    approved_name = not expected_name or final_name in (expected_name, expected_name.removesuffix(".md") + "_v2.md")

    if final_name and not approved_name:
        reason = "REPORT_NAME_NOT_AUTHORIZED"
    elif not persisted:
        reason = "FINAL_REPORT_NOT_PERSISTED"
    elif not verified:
        reason = "FINAL_REPORT_NOT_VERIFIED"
    elif not tool_verification_pass:
        reason = "FINAL_REPORT_VERIFICATION_FAILED"
    elif not evaluators_pass:
        reason = "INDEPENDENT_EVALUATORS_FAILED"
    else:
        reason = "TASK_COMPLETED"

    return {
        "task_completed": reason == "TASK_COMPLETED",
        "completion_status": reason,
        "report_persisted": persisted,
        "approved_report_name": approved_name,
        "final_report_verified": bool(verified),
        "tool_verification_pass": tool_verification_pass,
        "evaluators_pass": evaluators_pass,
        "final_report_name": final_name,
        "verification_count": len(verified),
    }
