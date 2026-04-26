from __future__ import annotations

from pathlib import Path

from .adapters import AdapterError, build_adapter_request, invoke_command_adapter
from .artifacts import latest_phase_result, write_phase_result
from .git import is_git_repo, task_changed_files, task_diff, task_workspace
from .models import FinishDecision
from .policy_config import PolicyConfigError, load_policy_config
from .schema import SchemaValidationError, validate_phase_payload
from .state_machine import can_transition
from .task_file import load_task, repo_root_for, update_task
from .tool_broker import DEFAULT_COMMAND_TIMEOUT_SECONDS, DEFAULT_MAX_OUTPUT_CHARS, run_command


class PhaseTransitionError(RuntimeError):
    pass


def _write_validated_phase_result(
    *,
    repo_root: Path,
    task_id: str,
    phase: str,
    payload: dict[str, object],
) -> Path:
    validate_phase_payload(phase, payload)
    return write_phase_result(repo_root=repo_root, task_id=task_id, phase=phase, payload=payload)


def _write_decision(
    *,
    repo_root: Path,
    task_id: str,
    payload: dict[str, object],
) -> Path:
    return write_phase_result(repo_root=repo_root, task_id=task_id, phase="decision", payload=payload)


def _enforce_phase_transition(
    *,
    task_path: Path,
    phase: str,
    next_status: str,
    force: bool,
) -> None:
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    allowed, reason = can_transition(current_status=task.metadata.status, next_status=next_status)
    if allowed:
        return

    outcome = "forced" if force else "blocked"
    payload = {
        "outcome": outcome,
        "summary": f"{phase} transition {outcome}: {reason}",
        "phase": phase,
        "from_status": task.metadata.status,
        "to_status": next_status,
        "reason": reason,
        "force": force,
    }
    _write_decision(repo_root=repo_root, task_id=task.metadata.id, payload=payload)
    if force:
        return

    update_task(task_path, metadata_updates={"blocked_reason": payload["summary"]})
    raise PhaseTransitionError(str(payload["summary"]))


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


def _plan_write_scope(plan_result: dict[str, object]) -> list[str]:
    scope: set[str] = set()
    for step in plan_result.get("steps", []):
        if not isinstance(step, dict):
            continue
        for item in step.get("write_scope", []):
            if isinstance(item, str) and item:
                scope.add(item)
    return sorted(scope)


def _is_file_in_scope(file_name: str, write_scope: list[str]) -> bool:
    for scope in write_scope:
        normalized = scope.rstrip("/")
        if file_name == normalized or file_name.startswith(f"{normalized}/"):
            return True
    return False


def _scope_mismatches(changed_files: list[str], planned_scope: list[str]) -> list[dict[str, str]]:
    mismatches: list[dict[str, str]] = []
    for file_name in changed_files:
        if not planned_scope:
            mismatches.append({"file": file_name, "reason": "missing planned write scope"})
        elif not _is_file_in_scope(file_name, planned_scope):
            mismatches.append({"file": file_name, "reason": "outside planned write scope"})
    return mismatches


def _is_trust_config_file(file_name: str) -> bool:
    return file_name in {".axiom/policy.yaml", ".axiom/policy.yml"}


def _deterministic_plan_payload(task_title: str, scope: str, anchors: list[str], checks: list[str]) -> dict[str, object]:
    steps: list[dict[str, object]] = []
    if anchors:
        for index, anchor in enumerate(anchors, start=1):
            if anchor.startswith("test") or "/test" in anchor:
                title = f"Update verification coverage in {anchor}."
            elif anchor.lower().endswith((".md", ".rst")):
                title = f"Update documentation in {anchor}."
            else:
                title = f"Apply the task change in {anchor}."
            steps.append({"id": f"step-{index}", "title": title, "write_scope": [anchor], "checks": checks})
    else:
        steps.append(
            {
                "id": "step-1",
                "title": "Discover concrete repo anchors and write them back to the task file before editing.",
                "write_scope": [],
                "checks": checks,
            }
        )
    steps.append(
        {
            "id": f"step-{len(steps) + 1}",
            "title": "Record task-scoped execution evidence from the task worktree.",
            "write_scope": anchors,
            "checks": [],
        }
    )
    steps.append(
        {
            "id": f"step-{len(steps) + 1}",
            "title": "Run automated checks, manual smoke, and process-isolated review.",
            "write_scope": [],
            "checks": checks,
        }
    )
    return {
        "summary": f"Plan ready for {task_title}: {scope or 'scope must stay within the task file.'}",
        "steps": steps,
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


def run_design(task_path: Path, *, force: bool = False) -> Path:
    _enforce_phase_transition(task_path=task_path, phase="design", next_status="design.passed", force=force)
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
        metadata_updates={"blocked_reason": ""},
    )
    return artifact_path


def _blocked_plan_payload(message: str, receipt: dict[str, object]) -> dict[str, object]:
    return {
        "outcome": "blocked",
        "summary": "Plan adapter failed.",
        "steps": [],
        "manual_smoke": [],
        "stop_conditions": ["Fix or replace the adapter, then rerun plan."],
        "failures": [message],
        "adapter": receipt,
    }


def run_plan(task_path: Path, *, adapter_command: str | None = None, force: bool = False) -> Path:
    _enforce_phase_transition(task_path=task_path, phase="plan", next_status="plan.passed", force=force)
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    anchors = _anchor_paths(task.sections.get("Repo Anchors", ""))
    workspace = task_workspace(task)
    check_root = workspace if workspace.exists() else repo_root
    checks = _detect_checks(check_root)
    scope = task.sections.get("Scope", "").strip()

    if adapter_command:
        request = build_adapter_request(phase="plan", task=task, task_path=task_path)
        try:
            adapter_result = invoke_command_adapter(command=adapter_command, request=request, cwd=workspace)
        except AdapterError as exc:
            payload = _blocked_plan_payload(str(exc), exc.receipt)
            artifact_path = _write_validated_phase_result(
                repo_root=repo_root, task_id=task.metadata.id, phase="plan", payload=payload
            )
            update_task(
                task_path,
                status="plan.blocked",
                section_updates={"Plan": _render_plan_markdown(payload)},
                metadata_updates={"blocked_reason": str(exc)},
            )
            return artifact_path
        payload = adapter_result.payload
        payload["adapter"] = adapter_result.receipt
        try:
            validate_phase_payload("plan", payload)
        except SchemaValidationError as exc:
            payload = _blocked_plan_payload(f"adapter payload failed schema validation: {exc}", adapter_result.receipt)
            artifact_path = _write_validated_phase_result(
                repo_root=repo_root, task_id=task.metadata.id, phase="plan", payload=payload
            )
            update_task(
                task_path,
                status="plan.blocked",
                section_updates={"Plan": _render_plan_markdown(payload)},
                metadata_updates={"blocked_reason": str(exc)},
            )
            return artifact_path
    else:
        payload = _deterministic_plan_payload(task.metadata.title, scope, anchors, checks)

    artifact_path = _write_validated_phase_result(
        repo_root=repo_root, task_id=task.metadata.id, phase="plan", payload=payload
    )
    update_task(
        task_path,
        status="plan.passed",
        section_updates={"Plan": _render_plan_markdown(payload)},
        metadata_updates={"blocked_reason": ""},
    )
    return artifact_path


def run_execute(
    task_path: Path,
    *,
    note: str = "Execution recorded.",
    adapter_command: str | None = None,
    force: bool = False,
) -> Path:
    _enforce_phase_transition(task_path=task_path, phase="execute", next_status="execute.passed", force=force)
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    workspace = task_workspace(task)
    pre_changed_files = task_changed_files(task)
    adapter_receipt: dict[str, object] | None = None
    summary = note
    if adapter_command:
        request = build_adapter_request(
            phase="execute",
            task=task,
            task_path=task_path,
            latest_artifacts={"plan": latest_phase_result(repo_root, task.metadata.id, "plan")},
            diff=task_diff(task),
        )
        try:
            adapter_result = invoke_command_adapter(command=adapter_command, request=request, cwd=workspace)
        except AdapterError as exc:
            changed_files = task_changed_files(task)
            payload = {
                "outcome": "failed",
                "summary": "Execute adapter failed.",
                "changed_files": changed_files,
                "pre_changed_files": pre_changed_files,
                "new_changed_files": sorted(set(changed_files) - set(pre_changed_files)),
                "failures": [str(exc)],
                "adapter": exc.receipt,
            }
            artifact_path = _write_validated_phase_result(
                repo_root=repo_root, task_id=task.metadata.id, phase="execute", payload=payload
            )
            update_task(
                task_path,
                status="execute.failed",
                section_updates={"Execution Log": _render_execution_markdown(payload)},
                metadata_updates={"blocked_reason": str(exc)},
            )
            return artifact_path
        adapter_receipt = adapter_result.receipt
        summary = str(adapter_result.payload.get("summary") or note)
    changed_files = task_changed_files(task)
    payload = {
        "summary": summary,
        "changed_files": changed_files,
        "pre_changed_files": pre_changed_files,
        "new_changed_files": sorted(set(changed_files) - set(pre_changed_files)),
    }
    if adapter_receipt is not None:
        payload["adapter"] = adapter_receipt
    artifact_path = _write_validated_phase_result(
        repo_root=repo_root, task_id=task.metadata.id, phase="execute", payload=payload
    )
    update_task(
        task_path,
        status="execute.passed",
        section_updates={"Execution Log": _render_execution_markdown(payload)},
        metadata_updates={"blocked_reason": ""},
    )
    return artifact_path


def run_verify(
    task_path: Path,
    *,
    commands: list[str],
    negative_commands: list[str],
    manual_smoke: list[dict[str, str]],
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    policy_profile: str = "standard",
    command_allowlist: list[str] | None = None,
    force: bool = False,
) -> Path:
    _enforce_phase_transition(task_path=task_path, phase="verify", next_status="verify.passed", force=force)
    task = load_task(task_path)
    repo_root = repo_root_for(task_path)
    workspace = task_workspace(task)
    effective_command_allowlist = list(command_allowlist or [])
    if policy_profile == "strict":
        try:
            effective_command_allowlist.extend(load_policy_config(repo_root).verify_strict_allow)
        except PolicyConfigError as exc:
            payload = {
                "outcome": "blocked",
                "summary": "Verification blocked by invalid policy config.",
                "automated_checks": [],
                "negative_checks": [],
                "manual_smoke": manual_smoke,
                "failures": [str(exc)],
            }
            artifact_path = _write_validated_phase_result(
                repo_root=repo_root, task_id=task.metadata.id, phase="verify", payload=payload
            )
            update_task(
                task_path,
                status="verify.blocked",
                section_updates={"Verification": _render_verify_markdown(payload)},
                metadata_updates={"blocked_reason": payload["summary"]},
            )
            return artifact_path

    automated_checks = [
        run_command(
            command,
            workspace,
            repo_root=repo_root,
            task_id=task.metadata.id,
            worktree=task.metadata.worktree,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
            policy_profile=policy_profile,
            command_allowlist=effective_command_allowlist,
        ).__dict__
        for command in commands
    ]
    negative_checks = [
        run_command(
            command,
            workspace,
            repo_root=repo_root,
            task_id=task.metadata.id,
            worktree=task.metadata.worktree,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
            policy_profile=policy_profile,
            command_allowlist=effective_command_allowlist,
        ).__dict__
        for command in negative_commands
    ]
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


def _blocked_review_adapter_payload(message: str, receipt: dict[str, object]) -> dict[str, object]:
    return {
        "outcome": "blocked",
        "summary": "Review adapter failed.",
        "findings": [
            {
                "severity": "blocker",
                "title": "Review adapter failed.",
                "evidence": message,
                "required_fix": "Fix or replace the review adapter, then rerun review.",
            }
        ],
        "next_phase": "review",
        "adapter": receipt,
    }


def run_review(task_path: Path, *, adapter_command: str | None = None, force: bool = False) -> Path:
    _enforce_phase_transition(task_path=task_path, phase="review", next_status="review.passed", force=force)
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
    manual_smoke = verify_result.get("manual_smoke", [])
    if task.metadata.isolation_mode == "degraded" and not manual_smoke:
        findings.append(
            {
                "severity": "blocker",
                "title": "Degraded isolation requires manual evidence.",
                "evidence": "Task is running without first-class git worktree isolation and latest verify artifact has no manual smoke evidence.",
                "required_fix": "Record at least one manual smoke result or move the task into a git repo with a HEAD commit.",
            }
        )
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
    plan_result = latest_phase_result(repo_root, task.metadata.id, "plan")
    planned_scope = _plan_write_scope(plan_result)
    actual_scope = changed_files
    scope_mismatches = _scope_mismatches(actual_scope, planned_scope)
    if task.metadata.isolation_mode == "worktree" and is_git_repo(workspace):
        if not changed_files or diff_text == "No task-scoped diff.":
            findings.append(
                {
                    "severity": "high",
                    "title": "No task-scoped diff found.",
                    "evidence": "Verification passed, but the task worktree has no changed files against the immutable base commit.",
                    "required_fix": "Apply the task changes in the task worktree or explain why this is an evidence-only task.",
                }
            )
        for mismatch in scope_mismatches:
            if mismatch["reason"] == "missing planned write scope":
                findings.append(
                    {
                        "severity": "high",
                        "title": "Missing plan write scope.",
                        "file": mismatch["file"],
                        "evidence": f"{mismatch['file']} is changed but the latest plan has no write_scope contract.",
                        "required_fix": "Run or update the plan so changed files are covered by an explicit write_scope.",
                    }
                )
            else:
                findings.append(
                    {
                        "severity": "high",
                        "title": "Changed file outside plan write scope.",
                        "file": mismatch["file"],
                        "evidence": f"{mismatch['file']} is changed but is not covered by the latest plan write_scope.",
                        "required_fix": "Update the plan write_scope or move the edit back inside the declared task scope.",
                    }
                )
        findings.extend(_diff_findings(diff_text))
        for file_name in changed_files:
            if _is_trust_config_file(file_name):
                findings.append(
                    {
                        "severity": "blocker",
                        "title": "Policy trust config changed.",
                        "file": file_name,
                        "evidence": f"{file_name} changes can weaken strict verification policy for future runs.",
                        "required_fix": "Keep policy config operator-owned. Move this change to a separately reviewed operator commit before finishing the task.",
                    }
                )

    base_context = {
        "changed_files": changed_files,
        "plan_write_scope": planned_scope,
        "planned_scope": planned_scope,
        "actual_scope": actual_scope,
        "scope_mismatches": scope_mismatches,
        "isolation_mode": task.metadata.isolation_mode,
    }

    if findings:
        payload = {
            "outcome": "changes_requested",
            "summary": "Review found issues that must be addressed before finish.",
            "findings": findings,
            "next_phase": "execute",
            **base_context,
        }
        status = "review.changes_requested"
        blocked_reason = payload["summary"]
    elif adapter_command:
        request = build_adapter_request(
            phase="review",
            task=task,
            task_path=task_path,
            latest_artifacts={"plan": plan_result, "verify": verify_result},
            diff=diff_text,
        )
        try:
            adapter_result = invoke_command_adapter(command=adapter_command, request=request, cwd=workspace)
        except AdapterError as exc:
            payload = {**_blocked_review_adapter_payload(str(exc), exc.receipt), **base_context}
            artifact_path = _write_validated_phase_result(
                repo_root=repo_root, task_id=task.metadata.id, phase="review", payload=payload
            )
            update_task(
                task_path,
                status="review.blocked",
                section_updates={"Review": _render_review_markdown(payload)},
                metadata_updates={"blocked_reason": str(exc)},
            )
            return artifact_path
        payload = {**adapter_result.payload, **base_context, "adapter": adapter_result.receipt}
        try:
            validate_phase_payload("review", payload)
        except SchemaValidationError as exc:
            payload = {
                **_blocked_review_adapter_payload(
                    f"adapter payload failed schema validation: {exc}",
                    adapter_result.receipt,
                ),
                **base_context,
            }
            artifact_path = _write_validated_phase_result(
                repo_root=repo_root, task_id=task.metadata.id, phase="review", payload=payload
            )
            update_task(
                task_path,
                status="review.blocked",
                section_updates={"Review": _render_review_markdown(payload)},
                metadata_updates={"blocked_reason": str(exc)},
            )
            return artifact_path
        outcome = str(payload["outcome"])
        status = "review.passed" if outcome == "pass" else f"review.{outcome}"
        blocked_reason = "" if outcome == "pass" else str(payload["summary"])
    else:
        payload = {
            "outcome": "pass",
            "summary": "Review passed using task-scoped diff and persisted verification evidence.",
            "findings": [],
            "next_phase": "done",
            **base_context,
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
    verify_passed = verify_result.get("outcome") == "passed"
    review_passed = review_result.get("outcome") == "pass"
    if not task.metadata.verification_required:
        verify_passed = True
        manual_smoke_complete = True
    if not task.metadata.review_required:
        review_passed = True

    allowed, reason = can_transition(
        current_status=task.metadata.status,
        next_status="done",
        verify_passed=verify_passed,
        review_passed=review_passed,
        manual_smoke_complete=manual_smoke_complete,
        docs_resolved=task.metadata.docs_resolved(),
        verification_required=task.metadata.verification_required,
        review_required=task.metadata.review_required,
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
