from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .models import CommandReceipt
from .policy import evaluate_command
from .approvals import find_approval


def run_command(
    command: str,
    cwd: Path,
    *,
    repo_root: Path | None = None,
    task_id: str = "",
    worktree: str = "",
) -> CommandReceipt:
    decision = evaluate_command(command)
    try:
        argv = shlex.split(command)
    except ValueError:
        argv = []

    name = argv[0] if argv else "command"
    approval_id = ""
    approval_reason = ""
    approval_scope: dict[str, object] = {}
    if decision.action == "escalate" and repo_root is not None:
        approval = find_approval(repo_root, command, task_id=task_id, worktree=worktree)
        if approval is not None:
            approval_id = str(approval["id"])
            approval_reason = str(approval.get("reason", ""))
            scope = approval.get("scope", {})
            approval_scope = scope if isinstance(scope, dict) else {}

    if decision.action != "allow" and not approval_id:
        return CommandReceipt(
            name=name,
            command=command,
            status="blocked",
            exit_code=-1,
            stdout="",
            stderr=decision.reason,
            policy=decision.action,
            policy_reason=decision.reason,
            approval_id="",
            approval_reason="",
            approval_scope={},
        )

    try:
        completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        return CommandReceipt(
            name=name,
            command=command,
            status="failed",
            exit_code=127,
            stdout="",
            stderr=str(exc),
            policy=decision.action,
            policy_reason=decision.reason,
            approval_id=approval_id,
            approval_reason=approval_reason,
            approval_scope=approval_scope,
        )

    return CommandReceipt(
        name=name,
        command=command,
        status="passed" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
        policy=decision.action,
        policy_reason=decision.reason,
        approval_id=approval_id,
        approval_reason=approval_reason,
        approval_scope=approval_scope,
    )
