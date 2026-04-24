from __future__ import annotations


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"design.passed"},
    "design.passed": {"plan.passed", "plan.blocked"},
    "plan.blocked": {"plan.passed"},
    "plan.passed": {"execute.passed", "execute.failed"},
    "execute.failed": {"execute.passed"},
    "execute.passed": {"verify.passed", "verify.failed", "verify.blocked", "done"},
    "verify.failed": {"execute.passed", "verify.passed", "verify.failed", "verify.blocked"},
    "verify.blocked": {"execute.passed", "verify.passed", "verify.failed", "verify.blocked"},
    "verify.passed": {"review.passed", "review.blocked", "review.changes_requested", "done"},
    "review.blocked": {"verify.passed", "review.passed", "review.blocked", "review.changes_requested"},
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
    verification_required: bool = True,
    review_required: bool = True,
) -> tuple[bool, str]:
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        return False, f"cannot transition from {current_status} to {next_status}"

    if next_status == "done":
        expected_status = "review.passed"
        if not review_required:
            expected_status = "verify.passed"
        if not verification_required and not review_required:
            expected_status = "execute.passed"
        if current_status != expected_status:
            return False, f"finish from {current_status} requires {expected_status}"
        if verification_required and not verify_passed:
            return False, "finish requires verify.passed"
        if review_required and not review_passed:
            return False, "finish requires review.passed"
        if verification_required and not manual_smoke_complete:
            return False, "finish requires completed manual smoke checks"
        if not docs_resolved:
            return False, "finish requires docs disposition"

    return True, ""
