from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .models import CommandReceipt
from .policy import evaluate_command


def run_command(command: str, cwd: Path) -> CommandReceipt:
    decision = evaluate_command(command)
    try:
        argv = shlex.split(command)
    except ValueError:
        argv = []

    name = argv[0] if argv else "command"
    if decision.action != "allow":
        return CommandReceipt(
            name=name,
            command=command,
            status="blocked",
            exit_code=-1,
            stdout="",
            stderr=decision.reason,
            policy=decision.action,
            policy_reason=decision.reason,
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
    )
