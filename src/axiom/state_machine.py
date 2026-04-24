from __future__ import annotations


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"design.passed"},
    "design.passed": {"plan.passed"},
    "plan.passed": {"execute.passed"},
    "execute.passed": {"verify.passed", "verify.failed", "verify.blocked"},
    "verify.failed": {"execute.passed"},
    "verify.blocked": {"execute.passed"},
    "verify.passed": {"review.passed", "review.blocked", "review.changes_requested"},
    "review.blocked": {"verify.passed"},
    "review.changes_requested": {"execute.passed", "plan.passed"},
    "review.passed": {"done"},
}


def can_transition(
    *,
    current_status: str,
    next_status: str,
    verify_passed: bool = False,
    review_passed: bool = False,
    manual_smoke_complete: bool = False,
    docs_resolved: bool = False,
) -> tuple[bool, str]:
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        return False, f"cannot transition from {current_status} to {next_status}"

    if next_status == "done":
        if not verify_passed:
            return False, "finish requires verify.passed"
        if not review_passed:
            return False, "finish requires review.passed"
        if not manual_smoke_complete:
            return False, "finish requires completed manual smoke checks"
        if not docs_resolved:
            return False, "finish requires docs disposition"

    return True, ""
