from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import layout_for


def approval_id_for(command: str) -> str:
    normalized = command.strip()
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


def find_approval(repo_root: Path, command: str) -> dict[str, object] | None:
    approval_id = approval_id_for(command)
    for item in _load_approvals(repo_root):
        if item.get("id") == approval_id and item.get("command") == command.strip():
            return item
    return None


def approve_command(repo_root: Path, command: str, *, reason: str) -> str:
    approval_id = approval_id_for(command)
    path = _approvals_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    approvals = [item for item in _load_approvals(repo_root) if item.get("id") != approval_id]
    approvals.append(
        {
            "id": approval_id,
            "command": command.strip(),
            "reason": reason,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    path.write_text(json.dumps(approvals, indent=2, sort_keys=True), encoding="utf-8")
    return approval_id
