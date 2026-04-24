from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import TaskDocument
from .policy import evaluate_command


ADAPTER_PROTOCOL = "axiom.adapter.v1"


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdapterResult:
    payload: dict[str, object]
    receipt: dict[str, object]


def build_adapter_request(
    *,
    phase: str,
    task: TaskDocument,
    task_path: Path,
    latest_artifacts: dict[str, object] | None = None,
    diff: str = "",
) -> dict[str, object]:
    return {
        "protocol": ADAPTER_PROTOCOL,
        "phase": phase,
        "task": {
            "id": task.metadata.id,
            "title": task.metadata.title,
            "kind": task.metadata.kind,
            "status": task.metadata.status,
            "risk": task.metadata.risk,
        },
        "task_path": str(task_path),
        "repo_root": task.metadata.repo_root,
        "workspace": task.metadata.worktree,
        "base_branch": task.metadata.base_branch,
        "branch": task.metadata.branch,
        "sections": task.sections,
        "latest_artifacts": latest_artifacts or {},
        "diff": diff,
    }


def invoke_command_adapter(
    *,
    command: str,
    request: dict[str, object],
    cwd: Path,
    timeout_seconds: int = 300,
) -> AdapterResult:
    decision = evaluate_command(command)
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise AdapterError(f"could not parse adapter command: {exc}") from exc

    receipt: dict[str, object] = {
        "command": command,
        "status": "blocked" if decision.action != "allow" else "pending",
        "exit_code": -1,
        "stdout": "",
        "stderr": "",
        "policy": decision.action,
        "policy_reason": decision.reason,
    }
    if decision.action != "allow":
        receipt["stderr"] = decision.reason
        raise AdapterError(decision.reason)

    completed = subprocess.run(
        argv,
        cwd=cwd,
        input=json.dumps(request, sort_keys=True),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    receipt.update(
        {
            "status": "passed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    )
    if completed.returncode != 0:
        raise AdapterError(completed.stderr.strip() or f"adapter exited with {completed.returncode}")

    payload = _parse_adapter_payload(completed.stdout)
    return AdapterResult(payload=payload, receipt=receipt)


def _parse_adapter_payload(stdout: str) -> dict[str, object]:
    if not stdout.strip():
        return {}
    try:
        payload: Any = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"adapter stdout was not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AdapterError("adapter stdout must be a JSON object")
    return payload
