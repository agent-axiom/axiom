from __future__ import annotations

import json
from pathlib import Path

from .config import layout_for


def _phase_root(repo_root: Path, task_id: str, phase: str) -> Path:
    return layout_for(repo_root).shared_artifacts_root / task_id / phase


def _next_attempt_dir(phase_root: Path) -> Path:
    attempts = sorted(
        path.name for path in phase_root.iterdir() if path.is_dir() and path.name.startswith("attempt-")
    ) if phase_root.exists() else []
    next_index = len(attempts) + 1
    return phase_root / f"attempt-{next_index:03d}"


def write_phase_result(*, repo_root: Path, task_id: str, phase: str, payload: dict[str, object]) -> Path:
    phase_root = _phase_root(repo_root, task_id, phase)
    phase_root.mkdir(parents=True, exist_ok=True)
    attempt_root = _next_attempt_dir(phase_root)
    attempt_root.mkdir(parents=True, exist_ok=False)
    result_path = attempt_root / "result.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return result_path


def latest_phase_result_path(repo_root: Path, task_id: str, phase: str) -> Path | None:
    phase_root = _phase_root(repo_root, task_id, phase)
    if not phase_root.exists():
        return None
    attempts = sorted(path for path in phase_root.iterdir() if path.is_dir() and path.name.startswith("attempt-"))
    if not attempts:
        return None
    return attempts[-1] / "result.json"


def latest_phase_result(repo_root: Path, task_id: str, phase: str) -> dict[str, object]:
    result_path = latest_phase_result_path(repo_root, task_id, phase)
    if result_path is None or not result_path.exists():
        return {}
    return json.loads(result_path.read_text(encoding="utf-8"))
