from __future__ import annotations

import json
import hashlib
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import TaskDocument
from .policy import evaluate_command
from .schema import SchemaValidationError, validate_phase_payload
from .tool_broker import DEFAULT_MAX_OUTPUT_CHARS, _captured, _truncate_output


ADAPTER_PROTOCOL = "axiom.adapter.v1"


class AdapterError(RuntimeError):
    def __init__(self, message: str, *, receipt: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.receipt = receipt or {}


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
        "base_commit": task.metadata.base_commit,
        "branch": task.metadata.branch,
        "isolation_mode": task.metadata.isolation_mode,
        "sections": task.sections,
        "latest_artifacts": latest_artifacts or {},
        "diff": diff,
    }


def _adapter_candidates(argv: list[str], cwd: Path) -> list[str]:
    candidates: list[str] = []
    for item in argv:
        if "/" not in item and not item.endswith(".py"):
            continue
        path = Path(item)
        if not path.is_absolute():
            path = cwd / path
        candidates.append(str(path.resolve()))
    if argv:
        candidates.append(argv[0])
    return candidates


def _evaluate_adapter_trust(argv: list[str], cwd: Path) -> tuple[bool, str]:
    allowlist = os.environ.get("AXIOM_ADAPTER_ALLOWLIST", "")
    if allowlist:
        allowed = {str(Path(item).expanduser().resolve()) for item in allowlist.split(os.pathsep) if item}
        candidates = set(_adapter_candidates(argv, cwd))
        if not candidates.intersection(allowed):
            return False, "adapter command is not in AXIOM_ADAPTER_ALLOWLIST"

    pins = os.environ.get("AXIOM_ADAPTER_SHA256", "")
    if pins:
        for pin in pins.split(os.pathsep):
            if not pin or "=" not in pin:
                continue
            raw_path, expected_hash = pin.split("=", 1)
            path = Path(raw_path).expanduser().resolve()
            if str(path) not in _adapter_candidates(argv, cwd):
                continue
            if not path.exists():
                return False, f"adapter hash pin path does not exist: {path}"
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash.lower() != expected_hash.lower():
                return False, f"adapter hash pin mismatch for {path}"
    return True, "adapter trust policy passed"


def invoke_command_adapter(
    *,
    command: str,
    request: dict[str, object],
    cwd: Path,
    timeout_seconds: int = 300,
) -> AdapterResult:
    try:
        validate_phase_payload("adapter-request", request)
    except SchemaValidationError as exc:
        raise AdapterError(f"invalid adapter request: {exc}") from exc

    decision = evaluate_command(command)
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        receipt = {
            "command": command,
            "status": "failed",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"could not parse adapter command: {exc}",
            "policy": "deny",
            "policy_reason": "could not parse command",
        }
        raise AdapterError(f"could not parse adapter command: {exc}", receipt=receipt) from exc

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
        raise AdapterError(decision.reason, receipt=receipt)

    trusted, trust_reason = _evaluate_adapter_trust(argv, cwd)
    receipt["trust_reason"] = trust_reason
    if not trusted:
        receipt["status"] = "blocked"
        receipt["policy"] = "deny"
        receipt["policy_reason"] = trust_reason
        receipt["stderr"] = trust_reason
        raise AdapterError(trust_reason, receipt=receipt)

    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            input=json.dumps(request, sort_keys=True),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_text = f"timed out after {timeout_seconds:g}s"
        stderr = _captured(exc.stderr, DEFAULT_MAX_OUTPUT_CHARS)
        stderr = f"{stderr}\n{timeout_text}".strip() if stderr else timeout_text
        receipt.update(
            {
                "status": "failed",
                "exit_code": -1,
                "stdout": _captured(exc.stdout, DEFAULT_MAX_OUTPUT_CHARS),
                "stderr": _truncate_output(stderr, DEFAULT_MAX_OUTPUT_CHARS),
            }
        )
        raise AdapterError(timeout_text, receipt=receipt) from exc
    except FileNotFoundError as exc:
        receipt.update(
            {
                "status": "failed",
                "exit_code": 127,
                "stdout": "",
                "stderr": str(exc),
            }
        )
        raise AdapterError(str(exc), receipt=receipt) from exc

    receipt.update(
        {
            "status": "passed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "stdout": _captured(completed.stdout, DEFAULT_MAX_OUTPUT_CHARS),
            "stderr": _captured(completed.stderr, DEFAULT_MAX_OUTPUT_CHARS),
        }
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or f"adapter exited with {completed.returncode}"
        raise AdapterError(message, receipt=receipt)

    try:
        payload = _parse_adapter_payload(completed.stdout)
    except AdapterError as exc:
        receipt.update({"status": "failed", "exit_code": -1, "stderr": str(exc)})
        raise AdapterError(str(exc), receipt=receipt) from exc
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
