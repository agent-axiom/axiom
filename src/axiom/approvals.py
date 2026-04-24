from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import layout_for


def _approval_scope(repo_root: Path, task_id: str = "", worktree: str = "") -> dict[str, str]:
    return {
        "repo_root": str(repo_root.resolve()),
        "task_id": task_id,
        "worktree": worktree,
    }


def approval_id_for(command: str, *, repo_root: Path, task_id: str = "", worktree: str = "") -> str:
    scope = _approval_scope(repo_root, task_id, worktree)
    normalized = json.dumps({"command": command.strip(), "scope": scope}, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _approvals_path(repo_root: Path) -> Path:
    return layout_for(repo_root).axiom_root / "policy" / "approvals.json"


def _load_approvals(repo_root: Path) -> list[dict[str, object]]:
    path = _approvals_path(repo_root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def list_approvals(repo_root: Path) -> list[dict[str, object]]:
    return _load_approvals(repo_root)


def _approval_matches(item: dict[str, object], command: str, scope: dict[str, str]) -> bool:
    if item.get("command") != command.strip():
        return False
    item_scope = item.get("scope")
    if not isinstance(item_scope, dict):
        return False
    if item_scope.get("repo_root") != scope["repo_root"]:
        return False
    item_task_id = str(item_scope.get("task_id", ""))
    item_worktree = str(item_scope.get("worktree", ""))
    if item_task_id and item_task_id != scope["task_id"]:
        return False
    if item_worktree and item_worktree != scope["worktree"]:
        return False
    return True


def find_approval(
    repo_root: Path,
    command: str,
    *,
    task_id: str = "",
    worktree: str = "",
) -> dict[str, object] | None:
    scope = _approval_scope(repo_root, task_id, worktree)
    for item in _load_approvals(repo_root):
        if _approval_matches(item, command, scope):
            return item
    return None


def approve_command(
    repo_root: Path,
    command: str,
    *,
    reason: str,
    task_id: str = "",
    worktree: str = "",
) -> str:
    scope = _approval_scope(repo_root, task_id, worktree)
    approval_id = approval_id_for(command, repo_root=repo_root, task_id=task_id, worktree=worktree)
    path = _approvals_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    approvals = [item for item in _load_approvals(repo_root) if item.get("id") != approval_id]
    approvals.append(
        {
            "id": approval_id,
            "command": command.strip(),
            "reason": reason,
            "scope": scope,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    path.write_text(json.dumps(approvals, indent=2, sort_keys=True), encoding="utf-8")
    return approval_id
