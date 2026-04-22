from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .artifacts import latest_phase_result, write_phase_result
from .git import repo_changed_files
from .models import CommandReceipt, FinishDecision
from .state_machine import can_transition
from .task_file import load_task, repo_root_for, update_task


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


def _run_command(command: str, cwd: Path) -> CommandReceipt:
    argv = shlex.split(command)
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    return CommandReceipt(
        name=argv[0] if argv else "command",
        command=command,
        status="passed" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


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
    artifact_path = write_phase_result(repo_root=repo_root, task_id=task.metadata.id, phase="design", payload=payload)
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
    payload = {
        "summary": f"Plan ready for {task.metadata.title}.",
        "steps": [
            {"id": "step-1", "title": "Edit the target files for the task.", "write_scope": [], "checks": []},
            {"id": "step-2", "title": "Record the execution result and changed files.", "write_scope": [], "checks": []},
            {"id": "step-3", "title": "Run verification and review before finishing.", "write_scope": [], "checks": []},
        ],
        "manual_smoke": [
            {"id": "smoke-1", "instruction": "Exercise the changed behavior manually and record what you observed."}
        ],
        "stop_conditions": [
            "Stop if the task requires dependency changes.",
            "Stop if the task needs work outside the repository root.",
        ],
    }
    artifact_path = write_phase_result(repo_root=repo_root, task_id=task.metadata.id, phase="plan", payload=payload)
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
        "changed_files": repo_changed_files(repo_root),
    }
    artifact_path = write_phase_result(repo_root=repo_root, task_id=task.metadata.id, phase="execute", payload=payload)
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

    automated_checks = [_run_command(command, repo_root).__dict__ for command in commands]
    negative_checks = [_run_command(command, repo_root).__dict__ for command in negative_commands]
    manual_smoke_complete = bool(manual_smoke) or not task.metadata.manual_smoke_required
    manual_smoke_passed = all(item["status"] in {"passed", "waived"} for item in manual_smoke)
    commands_passed = all(item["status"] == "passed" for item in automated_checks + negative_checks)
    outcome = "passed" if commands_passed and manual_smoke_complete and manual_smoke_passed else "failed"

    failures: list[str] = []
    for item in automated_checks + negative_checks:
        if item["status"] != "passed":
            failures.append(item["command"])
    for item in manual_smoke:
        if item["status"] not in {"passed", "waived"}:
            failures.append(item["id"])

    payload = {
        "outcome": outcome,
        "summary": "Verification passed." if outcome == "passed" else "Verification failed.",
        "automated_checks": automated_checks,
        "negative_checks": negative_checks,
        "manual_smoke": manual_smoke,
        "failures": failures,
    }
    artifact_path = write_phase_result(repo_root=repo_root, task_id=task.metadata.id, phase="verify", payload=payload)
    update_task(
        task_path,
        status=f"verify.{outcome}",
        section_updates={"Verification": _render_verify_markdown(payload)},
        metadata_updates={"blocked_reason": "" if outcome == "passed" else "verification failed"},
    )
    return artifact_path


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
        status = "review.blocked"
    else:
        docs_text = task.sections.get("Docs Impact", "").strip()
        docs_status = task.metadata.docs_status
        if not docs_text or docs_text.lower().startswith("pending"):
            docs_text = "No documentation changes required."
            docs_status = "not_needed"
        else:
            docs_status = "updated"

        payload = {
            "outcome": "pass",
            "summary": "Review passed using persisted verification evidence.",
            "findings": [],
            "next_phase": "done",
        }
        status = "review.passed"
        update_task(
            task_path,
            status=status,
            section_updates={
                "Docs Impact": docs_text,
                "Review": _render_review_markdown(payload),
            },
            metadata_updates={"docs_status": docs_status, "blocked_reason": ""},
        )
        return write_phase_result(repo_root=repo_root, task_id=task.metadata.id, phase="review", payload=payload)

    artifact_path = write_phase_result(repo_root=repo_root, task_id=task.metadata.id, phase="review", payload=payload)
    update_task(
        task_path,
        status=status,
        section_updates={"Review": _render_review_markdown(payload)},
        metadata_updates={"blocked_reason": payload["summary"]},
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
    artifact_path = write_phase_result(repo_root=repo_root, task_id=task.metadata.id, phase="finish", payload=payload)

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
