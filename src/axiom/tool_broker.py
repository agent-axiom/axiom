from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .models import CommandReceipt
from .policy import evaluate_command
from .approvals import find_approval

DEFAULT_COMMAND_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_OUTPUT_CHARS = 12_000


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _truncate_output(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    suffix = "\n...[truncated]"
    if max_chars <= len(suffix):
        return value[:max_chars]
    return value[: max_chars - len(suffix)] + suffix


def _captured(value: str | bytes | None, max_chars: int) -> str:
    return _truncate_output(_coerce_output(value).strip(), max_chars)


def run_command(
    command: str,
    cwd: Path,
    *,
    repo_root: Path | None = None,
    task_id: str = "",
    worktree: str = "",
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    policy_profile: str = "standard",
    command_allowlist: list[str] | None = None,
) -> CommandReceipt:
    decision = evaluate_command(command, profile=policy_profile, command_allowlist=command_allowlist or [])
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
        completed = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_text = f"timed out after {timeout_seconds:g}s"
        stderr = _captured(exc.stderr, max_output_chars)
        stderr = f"{stderr}\n{timeout_text}".strip() if stderr else timeout_text
        return CommandReceipt(
            name=name,
            command=command,
            status="failed",
            exit_code=-1,
            stdout=_captured(exc.stdout, max_output_chars),
            stderr=_truncate_output(stderr, max_output_chars),
            policy=decision.action,
            policy_reason=decision.reason,
            approval_id=approval_id,
            approval_reason=approval_reason,
            approval_scope=approval_scope,
        )
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
        stdout=_captured(completed.stdout, max_output_chars),
        stderr=_captured(completed.stderr, max_output_chars),
        policy=decision.action,
        policy_reason=decision.reason,
        approval_id=approval_id,
        approval_reason=approval_reason,
        approval_scope=approval_scope,
    )
