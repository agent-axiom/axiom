from __future__ import annotations

from pathlib import Path

from .artifacts import latest_phase_result, write_phase_result
from .git import is_git_repo, task_changed_files, task_diff, task_workspace
from .models import FinishDecision
from .schema import validate_phase_payload
from .state_machine import can_transition
from .task_file import load_task, repo_root_for, update_task
from .tool_broker import run_command


def _write_validated_phase_result(
    *,
    repo_root: Path,
    task_id: str,
    phase: str,
    payload: dict[str, object],
) -> Path:
    validate_phase_payload(phase, payload)
    return write_phase_result(repo_root=repo_root, task_id=task_id, phase=phase, payload=payload)


def _render_plan_markdown(payload: dict[str, object]) -> str:
    lines = [f"Summary: {payload['summary']}"]
    steps = payload.get("steps", [])
    if steps:
        lines.append("")
        lines.append("Steps:")
        for step in steps:
            lines.append(f"- {step['id']}: {step['title']}")
    manual_smoke = payload.get("manual_smoke", [])
    if manual_smoke:
        lines.append("")
        lines.append("Manual smoke:")
        for item in manual_smoke:
            lines.append(f"- {item['id']}: {item['instruction']}")
    return "\n".join(lines)


def _render_execution_markdown(payload: dict[str, object]) -> str:
    lines = [payload["summary"]]
    changed_files = payload.get("changed_files", [])
    if changed_files:
        lines.append("")
        lines.append("Changed files:")
        for file_name in changed_files:
            lines.append(f"- {file_name}")
    return "\n".join(lines)


def _render_verify_markdown(payload: dict[str, object]) -> str:
    lines = [f"Outcome: {payload['outcome']}", f"Summary: {payload['summary']}"]
    automated_checks = payload.get("automated_checks", [])
    if automated_checks:
        lines.append("")
        lines.append("Automated checks:")
        for check in automated_checks:
            lines.append(f"- {check['status']}: {check['command']}")
    negative_checks = payload.get("negative_checks", [])
    if negative_checks:
        lines.append("")
        lines.append("Negative checks:")
        for check in negative_checks:
            lines.append(f"- {check['status']}: {check['command']}")
    manual_smoke = payload.get("manual_smoke", [])
    if manual_smoke:
        lines.append("")
        lines.append("Manual smoke:")
        for item in manual_smoke:
            lines.append(f"- {item['status']}: {item['id']} ({item['notes']})")
    return "\n".join(lines)


def _render_review_markdown(payload: dict[str, object]) -> str:
    lines = [f"Outcome: {payload['outcome']}", f"Summary: {payload['summary']}"]
    findings = payload.get("findings", [])
    if findings:
        lines.append("")
        lines.append("Findings:")
        for finding in findings:
            lines.append(f"- {finding['severity']}: {finding['title']}")
    return "\n".join(lines)


def _anchor_paths(raw_anchors: str) -> list[str]:
    paths: list[str] = []
    for raw_line in raw_anchors.splitlines():
        line = raw_line.strip().lstrip("-*").strip().strip("`")
        if not line:
            continue
        if line.lower().startswith("add relevant files"):
            continue
        paths.append(line)
    return paths


def _detect_checks(repo_root: Path) -> list[str]:
    makefile = repo_root / "Makefile"
    if makefile.exists():
        for line in makefile.read_text(encoding="utf-8").splitlines():
            if line.strip() == "test:":
                return ["make test"]
    if (repo_root / "tests" / "unit").exists():
        return ["python3 -m unittest discover -s tests/unit -v"]
    if (repo_root / "tests").exists():
        return ["python3 -m unittest discover -s tests -v"]
    return []


def run_design(task_path: Path) -> Path:
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    design = task.sections.get("Design", "").strip()
    if not design:
        design = "Bootstrap design recorded. Keep the task file authoritative and persist phase artifacts after each step."
    anchors = task.sections.get("Repo Anchors", "").strip()
    if not anchors:
        anchors = "- Add relevant files or symbols here as the task narrows."
    payload = {
        "summary": "Design recorded for bootstrap slice.",
        "repo_anchors": anchors.splitlines(),
    }
    artifact_path = _write_validated_phase_result(
        repo_root=repo_root, task_id=task.metadata.id, phase="design", payload=payload
    )
    update_task(
        task_path,
        status="design.passed",
        section_updates={
            "Design": design,
            "Repo Anchors": anchors,
        },
    )
    return artifact_path


def run_plan(task_path: Path) -> Path:
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    anchors = _anchor_paths(task.sections.get("Repo Anchors", ""))
    workspace = task_workspace(task)
    check_root = workspace if workspace.exists() else repo_root
    checks = _detect_checks(check_root)
    scope = task.sections.get("Scope", "").strip()
    first_title = "Apply scoped changes within declared repo anchors."
    if not anchors:
        first_title = "Discover and record concrete repo anchors before editing."

    payload = {
        "summary": f"Plan ready for {task.metadata.title}: {scope or 'scope must stay within the task file.'}",
        "steps": [
            {"id": "step-1", "title": first_title, "write_scope": anchors, "checks": checks},
            {
                "id": "step-2",
                "title": "Record task-scoped execution evidence from the task worktree.",
                "write_scope": anchors,
                "checks": [],
            },
            {
                "id": "step-3",
                "title": "Run automated checks, manual smoke, and process-isolated review.",
                "write_scope": [],
                "checks": checks,
            },
        ],
        "manual_smoke": [
            {
                "id": "smoke-1",
                "instruction": "Exercise the changed behavior manually from the task worktree and record the observed output.",
            }
        ],
        "stop_conditions": [
            "Stop if the write scope is empty or the task requires files outside declared anchors.",
            "Stop if the task requires dependency changes.",
            "Stop if the task needs work outside the repository root.",
        ],
    }
    artifact_path = _write_validated_phase_result(
        repo_root=repo_root, task_id=task.metadata.id, phase="plan", payload=payload
    )
    update_task(
        task_path,
        status="plan.passed",
        section_updates={"Plan": _render_plan_markdown(payload)},
    )
    return artifact_path


def run_execute(task_path: Path, *, note: str = "Execution recorded.") -> Path:
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    payload = {
        "summary": note,
        "changed_files": task_changed_files(task),
    }
    artifact_path = _write_validated_phase_result(
        repo_root=repo_root, task_id=task.metadata.id, phase="execute", payload=payload
    )
    update_task(
        task_path,
        status="execute.passed",
        section_updates={"Execution Log": _render_execution_markdown(payload)},
    )
    return artifact_path


def run_verify(
    task_path: Path,
    *,
    commands: list[str],
    negative_commands: list[str],
    manual_smoke: list[dict[str, str]],
) -> Path:
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    workspace = task_workspace(task)

    automated_checks = [run_command(command, workspace).__dict__ for command in commands]
    negative_checks = [run_command(command, workspace).__dict__ for command in negative_commands]
    all_checks = automated_checks + negative_checks
    manual_smoke_complete = bool(manual_smoke) or not task.metadata.manual_smoke_required
    manual_smoke_passed = all(item["status"] in {"passed", "waived"} for item in manual_smoke)
    commands_blocked = any(item["status"] == "blocked" for item in all_checks)
    commands_passed = all(item["status"] == "passed" for item in all_checks)
    if commands_blocked:
        outcome = "blocked"
    else:
        outcome = "passed" if commands_passed and manual_smoke_complete and manual_smoke_passed else "failed"

    failures: list[str] = []
    for item in all_checks:
        if item["status"] != "passed":
            failures.append(item["command"])
    for item in manual_smoke:
        if item["status"] not in {"passed", "waived"}:
            failures.append(item["id"])

    payload = {
        "outcome": outcome,
        "summary": "Verification passed."
        if outcome == "passed"
        else "Verification blocked by policy."
        if outcome == "blocked"
        else "Verification failed.",
        "automated_checks": automated_checks,
        "negative_checks": negative_checks,
        "manual_smoke": manual_smoke,
        "failures": failures,
    }
    artifact_path = _write_validated_phase_result(
        repo_root=repo_root, task_id=task.metadata.id, phase="verify", payload=payload
    )
    update_task(
        task_path,
        status=f"verify.{outcome}",
        section_updates={"Verification": _render_verify_markdown(payload)},
        metadata_updates={"blocked_reason": "" if outcome == "passed" else payload["summary"]},
    )
    return artifact_path


def _docs_status_from_text(current_status: str, docs_text: str) -> str:
    if current_status != "pending":
        return current_status
    lowered = docs_text.lower()
    return "not_needed" if "no documentation" in lowered else "updated"


def _diff_findings(diff_text: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for line_number, line in enumerate(diff_text.splitlines(), start=1):
        if line.startswith("+<<<<<<<") or line.startswith("+=======") or line.startswith("+>>>>>>>"):
            findings.append(
                {
                    "severity": "blocker",
                    "title": "Merge conflict marker found.",
                    "line_start": line_number,
                    "line_end": line_number,
                    "evidence": line,
                    "required_fix": "Remove conflict markers and resolve the file.",
                }
            )
        if line.startswith("+") and ("TODO" in line or "FIXME" in line):
            findings.append(
                {
                    "severity": "medium",
                    "title": "New unfinished marker found.",
                    "line_start": line_number,
                    "line_end": line_number,
                    "evidence": line,
                    "required_fix": "Replace unfinished markers with completed implementation or explicit task scope.",
                }
            )
    return findings


def run_review(task_path: Path) -> Path:
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    verify_result = latest_phase_result(repo_root, task.metadata.id, "verify")

    if verify_result.get("outcome") != "passed":
        payload = {
            "outcome": "blocked",
            "summary": "Review blocked until verification passes.",
            "findings": [
                {
                    "severity": "blocker",
                    "title": "Verification must pass before review.",
                    "evidence": "Latest verify artifact was missing or failed.",
                }
            ],
            "next_phase": "verify",
        }
        artifact_path = _write_validated_phase_result(
            repo_root=repo_root, task_id=task.metadata.id, phase="review", payload=payload
        )
        update_task(
            task_path,
            status="review.blocked",
            section_updates={"Review": _render_review_markdown(payload)},
            metadata_updates={"blocked_reason": payload["summary"]},
        )
        return artifact_path

    findings: list[dict[str, object]] = []
    docs_text = task.sections.get("Docs Impact", "").strip()
    docs_status = task.metadata.docs_status
    if not docs_text or docs_text.lower().startswith("pending"):
        findings.append(
            {
                "severity": "medium",
                "title": "Docs impact is unresolved.",
                "evidence": "Docs Impact is empty or still marked pending.",
                "required_fix": "Record whether docs were updated or explicitly not needed.",
            }
        )
    else:
        docs_status = _docs_status_from_text(docs_status, docs_text)

    workspace = task_workspace(task)
    changed_files = task_changed_files(task)
    diff_text = task_diff(task)
    if is_git_repo(workspace):
        if not changed_files or diff_text == "No task-scoped diff.":
            findings.append(
                {
                    "severity": "high",
                    "title": "No task-scoped diff found.",
                    "evidence": "Verification passed, but the task worktree has no changed files against the base branch.",
                    "required_fix": "Apply the task changes in the task worktree or explain why this is an evidence-only task.",
                }
            )
        findings.extend(_diff_findings(diff_text))

    if findings:
        payload = {
            "outcome": "changes_requested",
            "summary": "Review found issues that must be addressed before finish.",
            "findings": findings,
            "next_phase": "execute",
            "changed_files": changed_files,
        }
        status = "review.changes_requested"
        blocked_reason = payload["summary"]
    else:
        payload = {
            "outcome": "pass",
            "summary": "Review passed using task-scoped diff and persisted verification evidence.",
            "findings": [],
            "next_phase": "done",
            "changed_files": changed_files,
        }
        status = "review.passed"
        blocked_reason = ""

    artifact_path = _write_validated_phase_result(
        repo_root=repo_root, task_id=task.metadata.id, phase="review", payload=payload
    )
    update_task(
        task_path,
        status=status,
        section_updates={"Review": _render_review_markdown(payload)},
        metadata_updates={"docs_status": docs_status, "blocked_reason": blocked_reason},
    )
    return artifact_path


def finish_task(task_path: Path) -> FinishDecision:
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    verify_result = latest_phase_result(repo_root, task.metadata.id, "verify")
    review_result = latest_phase_result(repo_root, task.metadata.id, "review")
    manual_smoke = verify_result.get("manual_smoke", [])
    manual_smoke_complete = bool(manual_smoke) and all(
        item.get("status") in {"passed", "waived"} for item in manual_smoke
    )
    if not task.metadata.manual_smoke_required:
        manual_smoke_complete = True

    allowed, reason = can_transition(
        current_status=task.metadata.status,
        next_status="done",
        verify_passed=verify_result.get("outcome") == "passed",
        review_passed=review_result.get("outcome") == "pass",
        manual_smoke_complete=manual_smoke_complete,
        docs_resolved=task.metadata.docs_resolved(),
    )

    payload = {
        "outcome": "passed" if allowed else "blocked",
        "summary": "Task finished." if allowed else reason,
    }
    artifact_path = _write_validated_phase_result(
        repo_root=repo_root, task_id=task.metadata.id, phase="finish", payload=payload
    )

    if allowed:
        update_task(
            task_path,
            status="done",
            metadata_updates={"blocked_reason": ""},
        )
        return FinishDecision(allowed=True, artifact_path=artifact_path)

    update_task(
        task_path,
        metadata_updates={"blocked_reason": reason},
    )
    return FinishDecision(allowed=False, reason=reason, artifact_path=artifact_path)
